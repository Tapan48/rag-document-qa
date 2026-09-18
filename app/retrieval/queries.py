import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    text: str
    source_metadata: dict
    distance: float


def retrieve_chunks(
    db: Session,
    owner_id: uuid.UUID,
    query_embedding: list[float],
    document_ids: list[uuid.UUID] | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    top_k = top_k if top_k is not None else settings.retrieval_top_k
    distance = Chunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(Chunk, Document.filename, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.owner_id == owner_id,
            Document.status == DocumentStatus.READY,
            Chunk.embedding.is_not(None),
        )
    )
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))

    stmt = stmt.order_by(distance).limit(top_k)

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            text=chunk.text,
            source_metadata=chunk.chunk_metadata or {},
            distance=distance_value,
        )
        for chunk, filename, distance_value in db.execute(stmt).all()
    ]
