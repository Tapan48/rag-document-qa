import uuid

import pytest

from app.api import questions as questions_module
from app.retrieval import pipeline as pipeline_module
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.retrieval.generation import GenerationError, GenerationTimeoutError, GenerationUnavailableError
from app.retrieval.generation import GeneratedAnswer

REGISTER_A = {"email": "asker-a@example.com", "password": "correct-horse-battery"}
REGISTER_B = {"email": "asker-b@example.com", "password": "correct-horse-battery"}

DIM = 1536


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


def _auth_headers(client, payload) -> dict:
    client.post("/auth/register", json=payload)
    login = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_ready_document_with_chunk(db_session, owner_email: str, text: str = "hello world"):
    user = db_session.query(User).filter_by(email=owner_email).one()
    document = Document(
        owner_id=user.id,
        filename="doc.txt",
        storage_path="/data/uploads/doc.txt",
        status=DocumentStatus.READY,
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        Chunk(document_id=document.id, position=0, text=text, chunk_metadata={}, embedding=_one_hot(0))
    )
    db_session.flush()
    return document


def _stub_embed(monkeypatch, vector=None):
    monkeypatch.setattr(pipeline_module, "embed_texts", lambda texts: [vector or _one_hot(0)])


def _stub_generate(monkeypatch, result=None, exc=None):
    def fake_generate(question, context):
        if exc:
            raise exc
        return result

    monkeypatch.setattr(questions_module, "generate_answer", fake_generate)


def test_rejects_blank_question(client):
    headers = _auth_headers(client, REGISTER_A)

    response = client.post("/questions", headers=headers, json={"question": "   "})

    assert response.status_code == 422


def test_rejects_explicit_empty_document_ids(client):
    headers = _auth_headers(client, REGISTER_A)

    response = client.post("/questions", headers=headers, json={"question": "hi", "document_ids": []})

    assert response.status_code == 422


def test_returns_insufficient_evidence_when_no_ready_documents(client, monkeypatch):
    _stub_embed(monkeypatch)
    headers = _auth_headers(client, REGISTER_A)

    response = client.post("/questions", headers=headers, json={"question": "anything?"})

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []


def test_returns_grounded_answer_with_citations(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    document = _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(
        monkeypatch,
        result=GeneratedAnswer(answer="the answer", cited_labels=["S1"], insufficient_evidence=False),
    )

    response = client.post("/questions", headers=headers, json={"question": "what is this about?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "the answer"
    assert body["insufficient_evidence"] is False
    assert len(body["citations"]) == 1
    assert body["citations"][0]["document_id"] == str(document.id)


def test_document_ids_404_for_unowned_document(client, monkeypatch, db_session):
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)
    document = _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)

    response = client.post(
        "/questions", headers=headers_b, json={"question": "q", "document_ids": [str(document.id)]}
    )

    assert response.status_code == 404


def test_document_ids_404_for_missing_document(client, monkeypatch):
    headers = _auth_headers(client, REGISTER_A)
    _stub_embed(monkeypatch)

    response = client.post(
        "/questions", headers=headers, json={"question": "q", "document_ids": [str(uuid.uuid4())]}
    )

    assert response.status_code == 404


def test_document_ids_409_for_not_ready_document(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    user = db_session.query(User).filter_by(email=REGISTER_A["email"]).one()
    document = Document(
        owner_id=user.id,
        filename="pending.txt",
        storage_path="/data/uploads/pending.txt",
        status=DocumentStatus.PROCESSING,
    )
    db_session.add(document)
    db_session.flush()
    _stub_embed(monkeypatch)

    response = client.post(
        "/questions", headers=headers, json={"question": "q", "document_ids": [str(document.id)]}
    )

    assert response.status_code == 409


def test_embedding_transient_error_returns_503(client, monkeypatch):
    headers = _auth_headers(client, REGISTER_A)

    def raise_transient(texts):
        raise EmbeddingTransientError("timeout")

    monkeypatch.setattr(pipeline_module, "embed_texts", raise_transient)

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 503


def test_embedding_error_returns_502(client, monkeypatch):
    headers = _auth_headers(client, REGISTER_A)

    def raise_permanent(texts):
        raise EmbeddingError("bad")

    monkeypatch.setattr(pipeline_module, "embed_texts", raise_permanent)

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 502


def test_generation_timeout_returns_504(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(monkeypatch, exc=GenerationTimeoutError("timed out"))

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 504


def test_generation_unavailable_returns_503(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(monkeypatch, exc=GenerationUnavailableError("unavailable"))

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 503


def test_generation_error_returns_502(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(monkeypatch, exc=GenerationError("malformed"))

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 502


def test_unknown_cited_label_returns_502(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(
        monkeypatch,
        result=GeneratedAnswer(answer="the answer", cited_labels=["S99"], insufficient_evidence=False),
    )

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 502


def test_substantive_answer_without_citations_returns_502(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(
        monkeypatch,
        result=GeneratedAnswer(answer="the answer", cited_labels=[], insufficient_evidence=False),
    )

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 502


def test_insufficient_evidence_without_citations_is_allowed(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)
    _stub_generate(
        monkeypatch,
        result=GeneratedAnswer(
            answer="not enough info", cited_labels=[], insufficient_evidence=True
        ),
    )

    response = client.post("/questions", headers=headers, json={"question": "q"})

    assert response.status_code == 200
    assert response.json()["insufficient_evidence"] is True
