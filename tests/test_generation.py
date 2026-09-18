import json
import uuid
from types import SimpleNamespace

import openai
import pytest

from app.retrieval import generation
from app.retrieval.generation import (
    GenerationError,
    GenerationTimeoutError,
    GenerationUnavailableError,
    build_labeled_context,
    generate_answer,
)
from app.retrieval.queries import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.txt",
        text=text,
        source_metadata={},
        distance=0.1,
    )


class _FakeResponses:
    def __init__(self, responder):
        self._responder = responder

    def create(self, **kwargs):
        return self._responder(kwargs)


class _FakeClient:
    def __init__(self, responder):
        self.responses = _FakeResponses(responder)


def _fixed_response(payload: dict):
    def responder(kwargs):
        return SimpleNamespace(output_text=json.dumps(payload))

    return responder


def test_build_labeled_context_numbers_chunks_from_one():
    chunks = [_chunk("first"), _chunk("second")]

    context = build_labeled_context(chunks)

    assert context == "[S1] first\n\n[S2] second"


def test_generate_answer_parses_valid_response(monkeypatch):
    monkeypatch.setattr(
        generation,
        "_client",
        _FakeClient(_fixed_response({"answer": "hi", "cited_labels": ["S1"], "insufficient_evidence": False})),
    )

    result = generate_answer("question", "[S1] context")

    assert result.answer == "hi"
    assert result.cited_labels == ["S1"]
    assert result.insufficient_evidence is False


def test_generate_answer_raises_timeout_error(monkeypatch):
    def raise_timeout(kwargs):
        raise openai.APITimeoutError(request=None)

    monkeypatch.setattr(generation, "_client", _FakeClient(raise_timeout))

    with pytest.raises(GenerationTimeoutError):
        generate_answer("q", "c")


def test_generate_answer_raises_unavailable_for_transient_errors(monkeypatch):
    def raise_rate_limit(kwargs):
        raise openai.RateLimitError(
            message="rate limited",
            response=SimpleNamespace(request=None, headers={}, status_code=429),
            body=None,
        )

    monkeypatch.setattr(generation, "_client", _FakeClient(raise_rate_limit))

    with pytest.raises(GenerationUnavailableError):
        generate_answer("q", "c")


def test_generate_answer_raises_generation_error_for_permanent_errors(monkeypatch):
    def raise_bad_request(kwargs):
        raise openai.BadRequestError(
            message="bad request",
            response=SimpleNamespace(request=None, headers={}, status_code=400),
            body=None,
        )

    monkeypatch.setattr(generation, "_client", _FakeClient(raise_bad_request))

    with pytest.raises(GenerationError):
        generate_answer("q", "c")


def test_generate_answer_raises_on_empty_output(monkeypatch):
    monkeypatch.setattr(
        generation, "_client", _FakeClient(lambda kwargs: SimpleNamespace(output_text=""))
    )

    with pytest.raises(GenerationError):
        generate_answer("q", "c")


def test_generate_answer_raises_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        generation, "_client", _FakeClient(lambda kwargs: SimpleNamespace(output_text="not json"))
    )

    with pytest.raises(GenerationError):
        generate_answer("q", "c")


def test_generate_answer_raises_on_missing_fields(monkeypatch):
    monkeypatch.setattr(
        generation, "_client", _FakeClient(_fixed_response({"answer": "hi"}))
    )

    with pytest.raises(GenerationError):
        generate_answer("q", "c")


def test_generate_answer_raises_on_wrong_field_types(monkeypatch):
    monkeypatch.setattr(
        generation,
        "_client",
        _FakeClient(_fixed_response({"answer": "hi", "cited_labels": "S1", "insufficient_evidence": False})),
    )

    with pytest.raises(GenerationError):
        generate_answer("q", "c")
