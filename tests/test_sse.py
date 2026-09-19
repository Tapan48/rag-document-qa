import asyncio
import json
import uuid

from app.retrieval import sse as sse_module
from app.retrieval.generation import GeneratedAnswer, GenerationError, GenerationTimeoutError, GenerationUnavailableError
from app.retrieval.pipeline import PreparedQuestion
from app.retrieval.queries import RetrievedChunk
from app.retrieval.sse import format_sse_event, generate_question_stream_events
from app.retrieval.streaming import AnswerDelta


def _chunk(text: str = "hello") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.txt",
        text=text,
        source_metadata={},
        distance=0.1,
    )


def _parse_events(raw_chunks: list[str]) -> list[tuple[str, dict]]:
    events = []
    for chunk in raw_chunks:
        lines = chunk.strip("\n").split("\n")
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append((event_line[len("event: "):], json.loads(data_line[len("data: "):])))
    return events


async def _collect(prepared: PreparedQuestion) -> list[str]:
    return [chunk async for chunk in generate_question_stream_events(prepared)]


def test_format_sse_event_framing():
    text = format_sse_event("answer", {"delta": "hi"})

    assert text == 'event: answer\ndata: {"delta": "hi"}\n\n'


def test_no_retrieved_chunks_skips_generation_entirely(monkeypatch):
    called = False

    async def fake_stream_answer(question, context):
        nonlocal called
        called = True
        yield  # pragma: no cover

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[])

    raw = asyncio.run(_collect(prepared))
    events = _parse_events(raw)

    assert called is False
    assert [e for e, _ in events] == ["citations", "done"]
    assert events[0][1] == {"citations": []}
    assert events[1][1]["insufficient_evidence"] is True


def test_successful_stream_emits_answer_citations_done_in_order(monkeypatch):
    chunk = _chunk()

    async def fake_stream_answer(question, context):
        yield AnswerDelta("hel")
        yield AnswerDelta("lo")
        yield GeneratedAnswer(answer="hello", cited_labels=["S1"], insufficient_evidence=False)

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[chunk])

    raw = asyncio.run(_collect(prepared))
    events = _parse_events(raw)

    assert [e for e, _ in events] == ["answer", "answer", "citations", "done"]
    assert events[0][1] == {"delta": "hel"}
    assert events[1][1] == {"delta": "lo"}
    assert len(events[2][1]["citations"]) == 1
    assert events[3][1]["answer"] == "hello"


def test_timeout_emits_error_and_stops(monkeypatch):
    async def fake_stream_answer(question, context):
        yield AnswerDelta("partial")
        yield GenerationTimeoutError("timed out")

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[_chunk()])

    raw = asyncio.run(_collect(prepared))
    events = _parse_events(raw)

    assert [e for e, _ in events] == ["answer", "error"]
    assert events[1][1]["code"] == "timeout"


def test_unavailable_emits_error_with_unavailable_code(monkeypatch):
    async def fake_stream_answer(question, context):
        yield GenerationUnavailableError("down")

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[_chunk()])

    events = _parse_events(asyncio.run(_collect(prepared)))

    assert events == [("error", {"code": "unavailable", "message": "Answer generation provider unavailable"})]


def test_generic_generation_error_emits_error_with_generation_failed_code(monkeypatch):
    async def fake_stream_answer(question, context):
        yield GenerationError("malformed")

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[_chunk()])

    events = _parse_events(asyncio.run(_collect(prepared)))

    assert events == [("error", {"code": "generation_failed", "message": "Answer generation failed"})]


def test_unknown_citation_label_emits_error_not_done(monkeypatch):
    async def fake_stream_answer(question, context):
        yield GeneratedAnswer(answer="hi", cited_labels=["S99"], insufficient_evidence=False)

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[_chunk()])

    events = _parse_events(asyncio.run(_collect(prepared)))

    assert [e for e, _ in events] == ["error"]
    assert events[0][1]["code"] == "generation_failed"


def test_insufficient_evidence_with_citations_emits_error_not_done(monkeypatch):
    async def fake_stream_answer(question, context):
        yield GeneratedAnswer(answer="hi", cited_labels=["S1"], insufficient_evidence=True)

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)
    prepared = PreparedQuestion(question="q", retrieved=[_chunk()])

    events = _parse_events(asyncio.run(_collect(prepared)))

    assert [e for e, _ in events] == ["error"]
