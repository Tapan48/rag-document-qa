import uuid

from app.retrieval import pipeline as pipeline_module
from app.retrieval import sse as sse_module
from app.retrieval.generation import GeneratedAnswer
from app.retrieval.streaming import AnswerDelta
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.user import User

REGISTER_A = {"email": "streamer-a@example.com", "password": "correct-horse-battery"}
REGISTER_B = {"email": "streamer-b@example.com", "password": "correct-horse-battery"}

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


def _create_ready_document_with_chunk(db_session, owner_email: str):
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
        Chunk(document_id=document.id, position=0, text="hello", chunk_metadata={}, embedding=_one_hot(0))
    )
    db_session.flush()
    return document


def _stub_embed(monkeypatch):
    monkeypatch.setattr(pipeline_module, "embed_texts", lambda texts: [_one_hot(0)])


def test_stream_rejects_blank_question(client):
    headers = _auth_headers(client, REGISTER_A)

    response = client.post("/questions/stream", headers=headers, json={"question": "   "})

    assert response.status_code == 422


def test_stream_document_ids_404_for_unowned_document(client, monkeypatch, db_session):
    headers_a = _auth_headers(client, REGISTER_A)
    headers_b = _auth_headers(client, REGISTER_B)
    document = _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)

    response = client.post(
        "/questions/stream",
        headers=headers_b,
        json={"question": "q", "document_ids": [str(document.id)]},
    )

    assert response.status_code == 404


def test_stream_document_ids_409_for_not_ready_document(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    user = db_session.query(User).filter_by(email=REGISTER_A["email"]).one()
    document = Document(
        owner_id=user.id,
        filename="pending.txt",
        storage_path="/data/uploads/pending.txt",
        status=DocumentStatus.QUEUED,
    )
    db_session.add(document)
    db_session.flush()
    _stub_embed(monkeypatch)

    response = client.post(
        "/questions/stream",
        headers=headers,
        json={"question": "q", "document_ids": [str(document.id)]},
    )

    assert response.status_code == 409


def test_stream_embedding_failure_returns_ordinary_503_not_sse(client, monkeypatch):
    from app.ingestion.embeddings import EmbeddingTransientError

    headers = _auth_headers(client, REGISTER_A)

    def raise_transient(texts):
        raise EmbeddingTransientError("timeout")

    monkeypatch.setattr(pipeline_module, "embed_texts", raise_transient)

    response = client.post("/questions/stream", headers=headers, json={"question": "q"})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")


def test_stream_no_ready_documents_returns_sse_with_fallback(client, monkeypatch):
    headers = _auth_headers(client, REGISTER_A)
    _stub_embed(monkeypatch)

    response = client.post("/questions/stream", headers=headers, json={"question": "q"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: citations" in body
    assert "event: done" in body
    assert '"insufficient_evidence": true' in body


def test_stream_successful_generation_full_body_contains_all_events(client, monkeypatch, db_session):
    headers = _auth_headers(client, REGISTER_A)
    _create_ready_document_with_chunk(db_session, REGISTER_A["email"])
    _stub_embed(monkeypatch)

    async def fake_stream_answer(question, context):
        yield AnswerDelta("hel")
        yield AnswerDelta("lo")
        yield GeneratedAnswer(answer="hello", cited_labels=["S1"], insufficient_evidence=False)

    monkeypatch.setattr(sse_module, "stream_answer", fake_stream_answer)

    response = client.post("/questions/stream", headers=headers, json={"question": "q"})

    assert response.status_code == 200
    body = response.text
    assert body.count("event: answer") == 2
    assert "event: citations" in body
    assert "event: done" in body
    assert body.index("event: answer") < body.index("event: citations") < body.index("event: done")
