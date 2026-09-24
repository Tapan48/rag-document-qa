from types import SimpleNamespace

import openai
import pytest

from app.ingestion import embeddings
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError, embed_texts


class _FakeEmbeddings:
    def __init__(self, responder):
        self._responder = responder
        self.calls: list[list[str]] = []

    def create(self, model, input):
        self.calls.append(list(input))
        return self._responder(input)


class _FakeClient:
    def __init__(self, responder):
        self.embeddings = _FakeEmbeddings(responder)


def _fake_response(dim: int = 1536):
    def responder(batch):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * dim) for _ in batch])

    return responder


def test_embed_texts_returns_empty_list_for_no_input(monkeypatch):
    assert embed_texts([]) == []


def test_embed_texts_returns_one_vector_per_text(monkeypatch):
    fake_client = _FakeClient(_fake_response())
    monkeypatch.setattr(embeddings, "_client", fake_client)

    vectors = embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert all(len(v) == 1536 for v in vectors)


def test_embed_texts_batches_requests(monkeypatch):
    fake_client = _FakeClient(_fake_response())
    monkeypatch.setattr(embeddings, "_client", fake_client)

    texts = [f"text-{i}" for i in range(250)]
    vectors = embed_texts(texts, batch_size=100)

    assert len(vectors) == 250
    assert [len(call) for call in fake_client.embeddings.calls] == [100, 100, 50]


def test_optional_question_timeout_disables_sdk_retries(monkeypatch):
    from unittest.mock import Mock

    scoped = _FakeClient(_fake_response())
    client = Mock()
    client.with_options.return_value = scoped
    monkeypatch.setattr(embeddings, "_client", client)
    assert len(embed_texts(["question"], timeout_seconds=20)) == 1
    client.with_options.assert_called_once_with(timeout=20, max_retries=0)
    assert scoped.embeddings.calls == [["question"]]


def test_embed_texts_raises_on_dimension_mismatch(monkeypatch):
    fake_client = _FakeClient(_fake_response(dim=42))
    monkeypatch.setattr(embeddings, "_client", fake_client)

    with pytest.raises(EmbeddingError):
        embed_texts(["a"])


def test_embed_texts_wraps_transient_errors(monkeypatch):
    def raise_transient(model, input):
        raise openai.APITimeoutError(request=None)

    fake_client = SimpleNamespace(embeddings=SimpleNamespace(create=raise_transient))
    monkeypatch.setattr(embeddings, "_client", fake_client)

    with pytest.raises(EmbeddingTransientError):
        embed_texts(["a"])


def test_embed_texts_wraps_permanent_errors(monkeypatch):
    def raise_permanent(model, input):
        raise openai.BadRequestError(
            message="bad request", response=SimpleNamespace(request=None, headers={}, status_code=400), body=None
        )

    fake_client = SimpleNamespace(embeddings=SimpleNamespace(create=raise_permanent))
    monkeypatch.setattr(embeddings, "_client", fake_client)

    with pytest.raises(EmbeddingError):
        embed_texts(["a"])
