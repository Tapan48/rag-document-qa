import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.retrieval import research, sse, pipeline, streaming
from app.retrieval.generation import GeneratedAnswer, GenerationError
from app.retrieval.pipeline import PreparedQuestion, finalize_answer
from app.retrieval.research import ResearchError, ResearchResult, ResearchTimeoutError
from app.retrieval.schemas import WebCitationOut
from app.retrieval.streaming import AnswerDelta
from tests.test_sse import _chunk
from tests.test_questions_api import _auth_headers, _create_ready_document_with_chunk, _one_hot, REGISTER_A, REGISTER_B


def result():
    return ResearchResult('Sources W1: A public specification.', [WebCitationOut(
        source_id='W1', title='Manufacturer', url='https://example.com/spec', researched_at=datetime.now(timezone.utc)
    )])


def provider_response(url='https://example.com/spec'):
    text='Output is 24 volts. [citation]'
    data={'status':'completed', 'output':[
        {'type':'web_search_call','status':'completed','action':{'type':'search'}},
        {'type':'message','content':[{'type':'output_text','text':text,'annotations':[
            {'type':'url_citation','start_index':20,'end_index':len(text),'url':url,'title':'Manufacturer'}
        ]}]}
    ]}
    return SimpleNamespace(model_dump=lambda:data)


def test_research_uses_only_annotated_findings():
    parsed=research.parse_research(provider_response())
    assert parsed.sources[0].source_id=='W1'
    assert parsed.sources[0].researched_at.tzinfo is not None
    assert parsed.context=='Sources W1: Output is 24 volts.'


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,hi','https://user:pass@example.com','https://bad host.com'])
def test_search_rejects_unsafe_source_urls(url):
    with pytest.raises(ResearchError): research.parse_research(provider_response(url))


def test_missing_actual_search_is_rejected():
    response=provider_response(); response.model_dump()['output'].pop(0)
    with pytest.raises(ResearchError): research.parse_research(response)


def test_no_citations_produces_no_web_evidence():
    response=provider_response(); response.model_dump()['output'][1]['content'][0]['annotations']=[]
    parsed=research.parse_research(response)
    assert parsed.context=='' and parsed.sources==[]


def test_invalid_offsets_and_incomplete_response_are_rejected():
    response=provider_response(); response.model_dump()['output'][1]['content'][0]['annotations'][0]['end_index']=999
    with pytest.raises(ResearchError): research.parse_research(response)
    response=provider_response(); response.model_dump()['status']='incomplete'
    with pytest.raises(ResearchError): research.parse_research(response)


def test_search_call_budget_is_checked():
    response=provider_response(); data=response.model_dump()
    data['output'] += [data['output'][0]] * settings.web_search_max_tool_calls
    with pytest.raises(ResearchError): research.parse_research(response)


def test_real_tool_required_and_only_brief_reaches_search(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries']==0
            self.responses=SimpleNamespace(create=AsyncMock(side_effect=[
                SimpleNamespace(status='completed',output_text='Compare public 24V power supplies'),provider_response()
            ]))
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
    client=Client(max_retries=0)
    monkeypatch.setattr(research.openai,'AsyncOpenAI',lambda **kwargs:client)
    parsed=asyncio.run(research.research_web('compare','PRIVATE_DOCUMENT_PASSAGE'))
    call=client.responses.create.call_args_list[1].kwargs
    assert call['tool_choice']=='required' and call['max_tool_calls']==3
    assert 'PRIVATE_DOCUMENT_PASSAGE' not in str(call)
    assert call['store'] is False and parsed.sources and client.closed


def test_research_deadline_closes_provider(monkeypatch):
    class Client:
        closed=False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
        async def create(self,**kwargs): await asyncio.sleep(10)
        @property
        def responses(self):return self
    client=Client()
    monkeypatch.setattr(research.openai,'AsyncOpenAI',lambda **kwargs:client)
    monkeypatch.setattr(settings,'web_search_timeout_seconds',0.01)
    with pytest.raises(ResearchTimeoutError):asyncio.run(research.research_web('q','c'))
    assert client.closed


def test_combined_citations_keep_original_source_ids():
    chunks=[_chunk('a'),_chunk('b')]
    output=finalize_answer(GeneratedAnswer('Document [S2]; market [W1].',['S2','W1'],False),chunks,result())
    assert output.citations[0].source_id=='S2'
    assert output.citations[0].chunk_id==chunks[1].chunk_id
    assert output.web_citations[0].url=='https://example.com/spec'
    assert output.web_search_performed


@pytest.mark.parametrize('answer,labels',[
    ('Invented [W9]',['W9']),('Missing inline marker',['W1']),('Mismatched [W1]',['S1']),
])
def test_unknown_or_inconsistent_citations_rejected(answer,labels):
    with pytest.raises(GenerationError):finalize_answer(GeneratedAnswer(answer,labels,False),[_chunk()],result())


def test_web_insufficient_evidence():
    response=finalize_answer(GeneratedAnswer('No supported prices found.',[],True),[],ResearchResult('',[]))
    assert response.insufficient_evidence and response.web_search_performed
    assert response.web_citations==[]


def stub_research_and_answer(monkeypatch):
    search=AsyncMock(return_value=result())
    monkeypatch.setattr(sse,'research_web',search)
    async def answer(q,c,**kwargs):
        assert kwargs['web_context']==result().context
        yield AnswerDelta('Market result ')
        yield GeneratedAnswer('Market result [W1].',['W1'],False)
    monkeypatch.setattr(sse,'stream_answer',answer)
    return search


@pytest.mark.parametrize('endpoint',['/questions','/questions/stream'])
def test_web_works_without_documents_or_embeddings(client,monkeypatch,endpoint):
    search=stub_research_and_answer(monkeypatch)
    monkeypatch.setattr(pipeline,'embed_texts',lambda *a:pytest.fail('No documents need embedding'))
    headers=_auth_headers(client,REGISTER_A)
    response=client.post(endpoint,headers=headers,json={'question':'market?','web_search':True})
    assert response.status_code==200
    assert 'https://example.com/spec' in response.text and 'W1' in response.text
    assert search.await_count==1
    if endpoint.endswith('stream'):
        assert response.text.index('searching')<response.text.index('generating')<response.text.index('event: answer')


@pytest.mark.parametrize('endpoint',['/questions','/questions/stream'])
def test_web_ownership_and_readiness_before_search(client,monkeypatch,db_session,endpoint):
    search=stub_research_and_answer(monkeypatch)
    headers_a=_auth_headers(client,REGISTER_A); headers_b=_auth_headers(client,REGISTER_B)
    document=_create_ready_document_with_chunk(db_session,REGISTER_A['email'])
    payload={'question':'q','web_search':True,'document_ids':[str(document.id)]}
    assert client.post(endpoint,headers=headers_b,json=payload).status_code==404
    from app.models.document import DocumentStatus
    document.status=DocumentStatus.PROCESSING;db_session.flush()
    assert client.post(endpoint,headers=headers_a,json=payload).status_code==409
    search.assert_not_awaited()


@pytest.mark.parametrize('endpoint',['/questions','/questions/stream'])
def test_toggle_off_never_searches(client,monkeypatch,endpoint):
    search=AsyncMock(side_effect=AssertionError('Must not search'))
    monkeypatch.setattr(sse,'research_web',search)
    monkeypatch.setattr(pipeline,'embed_texts',lambda *a:[_one_hot(0)])
    response=client.post(endpoint,headers=_auth_headers(client,REGISTER_A),json={'question':'q','web_search':False})
    assert response.status_code==200
    search.assert_not_awaited()


@pytest.mark.parametrize('endpoint',['/questions','/questions/stream'])
def test_search_failure_never_falls_back(client,monkeypatch,endpoint):
    monkeypatch.setattr(sse,'research_web',AsyncMock(side_effect=ResearchTimeoutError('Web search timed out')))
    response=client.post(endpoint,headers=_auth_headers(client,REGISTER_A),json={'question':'q','web_search':True})
    assert 'Web search timed out' in response.text
    assert response.status_code==(200 if endpoint.endswith('stream') else 504)
    if endpoint.endswith('stream'):assert 'event: done' not in response.text


def test_stream_cancellation_stops_research(monkeypatch):
    async def scenario():
        started=asyncio.Event(); cancelled=asyncio.Event()
        async def waiting(*args):
            started.set()
            try:await asyncio.sleep(10)
            finally:cancelled.set()
        monkeypatch.setattr(sse,'research_web',waiting)
        gen=sse.generate_question_stream_events(PreparedQuestion('q',[],True))
        assert 'searching' in await anext(gen)
        next_event=asyncio.create_task(anext(gen))
        await started.wait();next_event.cancel()
        with pytest.raises(asyncio.CancelledError):await next_event
        assert cancelled.is_set()
        await gen.aclose()
    asyncio.run(scenario())


def test_combined_stream_and_generation_cancellation(monkeypatch):
    async def scenario():
        closed=False
        async def answer(*a,**kw):
            nonlocal closed
            try:
                yield AnswerDelta('partial')
                await asyncio.sleep(10)
            finally:closed=True
        monkeypatch.setattr(sse,'research_web',AsyncMock(return_value=result()))
        monkeypatch.setattr(sse,'stream_answer',answer)
        async with aclosing(sse.generate_question_stream_events(PreparedQuestion('q',[_chunk()],True))) as gen:
            assert 'searching' in await anext(gen)
            assert 'generating' in await anext(gen)
            assert 'partial' in await anext(gen)
        assert closed
    asyncio.run(scenario())


def test_web_generation_cancellation_closes_provider_client(monkeypatch):
    async def scenario():
        started = asyncio.Event()
        closed = asyncio.Event()

        class Client:
            @property
            def responses(self):
                return self

            async def create(self, **kwargs):
                started.set()
                await asyncio.sleep(10)

            async def close(self):
                closed.set()

        monkeypatch.setattr(streaming.openai, 'AsyncOpenAI', lambda **kwargs: Client())
        gen = streaming.stream_answer('question', '', web_context='Sources W1: evidence')
        task = asyncio.create_task(anext(gen))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        await gen.aclose()

    asyncio.run(scenario())
