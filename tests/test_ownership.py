import uuid

import pytest
from fastapi import HTTPException

from app.documents.queries import get_owned_chunks, get_owned_document
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User


def _create_user(db_session, email: str) -> User:
    user = User(email=email, password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_document(db_session, owner: User, filename: str = "doc.pdf") -> Document:
    document = Document(
        owner_id=owner.id, filename=filename, storage_path=f"/data/uploads/{filename}"
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_owner_can_fetch_their_document(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner)

    result = get_owned_document(db_session, document.id, owner.id)

    assert result.id == document.id


def test_other_user_gets_404_for_someone_elses_document(db_session):
    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    document = _create_document(db_session, owner)

    with pytest.raises(HTTPException) as exc_info:
        get_owned_document(db_session, document.id, other.id)

    assert exc_info.value.status_code == 404


def test_missing_document_returns_404(db_session):
    owner = _create_user(db_session, "owner@example.com")

    with pytest.raises(HTTPException) as exc_info:
        get_owned_document(db_session, uuid.uuid4(), owner.id)

    assert exc_info.value.status_code == 404


def test_owned_chunks_returned_in_position_order(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner)
    for position, text in [(1, "second"), (0, "first")]:
        db_session.add(Chunk(document_id=document.id, position=position, text=text))
    db_session.flush()

    chunks = get_owned_chunks(db_session, document.id, owner.id)

    assert [chunk.text for chunk in chunks] == ["first", "second"]


def test_owned_chunks_404_when_document_belongs_to_another_user(db_session):
    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    document = _create_document(db_session, owner)
    db_session.add(Chunk(document_id=document.id, position=0, text="secret"))
    db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        get_owned_chunks(db_session, document.id, other.id)

    assert exc_info.value.status_code == 404
