import uuid

import pytest
from fastapi import HTTPException

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.retrieval import pipeline as pipeline_module
from app.retrieval.generation import GeneratedAnswer, GenerationError
from app.retrieval.pipeline import fallback_response, finalize_answer, prepare_question

DIM = 1536


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


def _create_user(db_session, email: str) -> User:
    user = User(email=email, password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_ready_document_with_chunk(db_session, owner: User):
    document = Document(
        owner_id=owner.id,
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


def test_prepare_question_retrieves_chunks(monkeypatch, db_session):
    owner = _create_user(db_session, "owner@example.com")
    _create_ready_document_with_chunk(db_session, owner)
    monkeypatch.setattr(pipeline_module, "embed_texts", lambda texts: [_one_hot(0)])

    prepared = prepare_question(db_session, owner.id, "what is this?", None)

    assert prepared.question == "what is this?"
    assert len(prepared.retrieved) == 1


def test_prepare_question_404_for_missing_document(monkeypatch, db_session):
    owner = _create_user(db_session, "owner@example.com")
    monkeypatch.setattr(pipeline_module, "embed_texts", lambda texts: [_one_hot(0)])

    with pytest.raises(HTTPException) as exc_info:
        prepare_question(db_session, owner.id, "q", [uuid.uuid4()])

    assert exc_info.value.status_code == 404


def test_prepare_question_409_for_not_ready_document(monkeypatch, db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = Document(
        owner_id=owner.id,
        filename="pending.txt",
        storage_path="/data/uploads/pending.txt",
        status=DocumentStatus.QUEUED,
    )
    db_session.add(document)
    db_session.flush()
    monkeypatch.setattr(pipeline_module, "embed_texts", lambda texts: [_one_hot(0)])

    with pytest.raises(HTTPException) as exc_info:
        prepare_question(db_session, owner.id, "q", [document.id])

    assert exc_info.value.status_code == 409


def test_fallback_response_is_insufficient_evidence_with_no_citations():
    response = fallback_response()

    assert response.insufficient_evidence is True
    assert response.citations == []
    assert response.answer


def test_finalize_answer_resolves_citations(db_session):
    owner = _create_user(db_session, "owner@example.com")
    _create_ready_document_with_chunk(db_session, owner)
    from app.retrieval.queries import retrieve_chunks

    retrieved = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)
    generated = GeneratedAnswer(answer="the answer", cited_labels=["S1"], insufficient_evidence=False)

    response = finalize_answer(generated, retrieved)

    assert response.answer == "the answer"
    assert len(response.citations) == 1


def test_finalize_answer_raises_on_substantive_answer_without_citations(db_session):
    generated = GeneratedAnswer(answer="the answer", cited_labels=[], insufficient_evidence=False)

    with pytest.raises(GenerationError):
        finalize_answer(generated, [])


def test_finalize_answer_allows_insufficient_evidence_without_citations(db_session):
    generated = GeneratedAnswer(answer="not enough info", cited_labels=[], insufficient_evidence=True)

    response = finalize_answer(generated, [])

    assert response.insufficient_evidence is True
    assert response.citations == []


def test_finalize_answer_raises_on_insufficient_evidence_with_citations(db_session):
    owner = _create_user(db_session, "owner@example.com")
    _create_ready_document_with_chunk(db_session, owner)
    from app.retrieval.queries import retrieve_chunks

    retrieved = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)
    generated = GeneratedAnswer(
        answer="not enough info", cited_labels=["S1"], insufficient_evidence=True
    )

    with pytest.raises(GenerationError):
        finalize_answer(generated, retrieved)
