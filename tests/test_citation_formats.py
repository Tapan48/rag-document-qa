import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api import questions
from app.retrieval import sse
from app.retrieval.citations import CITATION_ERROR_MESSAGE, CitationValidationError
from app.retrieval.generation import GeneratedAnswer
from app.retrieval.pipeline import PreparedQuestion, finalize_answer
from app.retrieval.research import ResearchResult
from app.retrieval.schemas import WebCitationOut
from app.retrieval.streaming import AnswerDelta
from tests.test_questions_api import _auth_headers, REGISTER_A
from tests.test_sse import _chunk


def research_result():
    return ResearchResult('Cited specifications', [
        WebCitationOut(source_id=label, title='Manufacturer', url=f'https://example.com/{label}',
                       researched_at=datetime.now(timezone.utc))
        for label in ('W1', 'W2')
    ])


@pytest.mark.parametrize('answer, labels, normalized', [
    ('Evidence [W1, W2].', ['W1', 'W2'], 'Evidence [W1] [W2].'),
    ('Evidence [S1, W1, W2].', ['S1', 'W1', 'W2'], 'Evidence [S1] [W1] [W2].'),
    ('Evidence [ W1 ,\n W2 ].', ['W1', 'W2'], 'Evidence [W1] [W2].'),
    ('Evidence [S1] [W1].', ['S1', 'W1'], 'Evidence [S1] [W1].'),
    ('Evidence [W1,W1,W2].', ['W1', 'W2'], 'Evidence [W1] [W1] [W2].'),
])
def test_valid_citation_formats_preserve_source_ids(answer, labels, normalized):
    chunk = _chunk()
    response = finalize_answer(GeneratedAnswer(answer, labels, False), [chunk], research_result())
    assert response.answer == normalized
    assert [c.source_id for c in response.web_citations] == [label for label in labels if label.startswith('W')]
    if 'S1' in labels:
        assert response.citations[0].chunk_id == chunk.chunk_id


@pytest.mark.parametrize('answer, labels, insufficient, reason', [
    ('Evidence [W1, W99].', ['W1', 'W99'], False, 'unknown_source'),
    ('Evidence [W1, W99].', ['W1'], False, 'inline_source_mismatch'),
    ('Evidence [W1, W2].', ['W1'], False, 'inline_source_mismatch'),
    ('Evidence [W1].', ['W1', 'W2'], False, 'inline_source_mismatch'),
    ('Evidence [W1, arbitrary-text].', ['W1'], False, 'inline_source_mismatch'),
    ('Evidence [W1, W2].', ['W1, W2'], False, 'unknown_source'),
    ('No evidence [W1, W2].', ['W1', 'W2'], True, 'insufficient_evidence_with_citations'),
    ('Uncited answer.', [], False, 'missing_citations'),
])
def test_normalization_does_not_weaken_validation(answer, labels, insufficient, reason, caplog):
    with caplog.at_level(logging.WARNING, logger='app.retrieval.pipeline'):
        with pytest.raises(CitationValidationError) as exc:
            finalize_answer(GeneratedAnswer(answer, labels, insufficient), [_chunk()], research_result())
    assert exc.value.reason == reason
    assert f'reason={reason}' in caplog.text
    assert answer not in caplog.text


def test_unknown_model_label_is_never_logged(caplog):
    sensitive_label = 'PRIVATE_MODEL_SUPPLIED_VALUE'
    with caplog.at_level(logging.WARNING, logger='app.retrieval.pipeline'):
        with pytest.raises(CitationValidationError) as exc:
            finalize_answer(GeneratedAnswer('PRIVATE_DOCUMENT_TEXT', [sensitive_label], False), [], research_result())
    assert 'unknown_source' in caplog.text
    assert sensitive_label not in caplog.text + str(exc.value)
    assert 'PRIVATE_DOCUMENT_TEXT' not in caplog.text


def test_document_only_groups_are_normalized_without_requiring_inline_markers():
    chunks = [_chunk(), _chunk()]
    response = finalize_answer(GeneratedAnswer('Evidence [S1, S2].', ['S1', 'S2'], False), chunks)
    assert response.answer == 'Evidence [S1] [S2].'
    legacy = finalize_answer(GeneratedAnswer('Evidence.', ['S1'], False), chunks)
    assert legacy.answer == 'Evidence.'


@pytest.mark.parametrize('endpoint', ['/questions', '/questions/stream'])
@pytest.mark.parametrize('valid', [True, False])
def test_both_endpoints_normalize_or_return_clear_citation_errors(client, monkeypatch, endpoint, valid):
    headers = _auth_headers(client, REGISTER_A)
    monkeypatch.setattr(questions, 'prepare_question', lambda *args: PreparedQuestion('q', [_chunk()], True))
    monkeypatch.setattr(sse, 'research_web', AsyncMock(return_value=research_result()))

    async def answer(*args, **kwargs):
        text = 'Comparison [S1, W1, W2].'
        yield AnswerDelta(text)
        yield GeneratedAnswer(text, ['S1', 'W1', 'W2'] if valid else ['S1'], False)

    monkeypatch.setattr(sse, 'stream_answer', answer)
    response = client.post(endpoint, headers=headers, json={'question': 'q', 'web_search': True})
    if valid:
        assert response.status_code == 200
        assert 'Comparison [S1] [W1] [W2].' in response.text
    else:
        assert CITATION_ERROR_MESSAGE in response.text
        assert response.status_code == (200 if endpoint.endswith('stream') else 502)
        assert 'event: done' not in response.text


def test_document_only_endpoint_has_clear_validation_error(client, monkeypatch):
    headers = _auth_headers(client, REGISTER_A)
    monkeypatch.setattr(questions, 'prepare_question', lambda *args: PreparedQuestion('q', [_chunk()]))
    monkeypatch.setattr(questions, 'generate_answer', lambda *args: GeneratedAnswer('Uncited answer', [], False))
    response = client.post('/questions', headers=headers, json={'question': 'q'})
    assert response.status_code == 502
    assert response.json()['detail'] == CITATION_ERROR_MESSAGE
