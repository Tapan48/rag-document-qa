import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


def get_owned_document(db: Session, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document:
    document = db.execute(
        select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    ).scalar_one_or_none()
    if document is None:
        raise _NOT_FOUND
    return document


def get_owned_chunks(db: Session, document_id: uuid.UUID, owner_id: uuid.UUID) -> list[Chunk]:
    get_owned_document(db, document_id, owner_id)
    return list(
        db.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.position)
        ).scalars()
    )
