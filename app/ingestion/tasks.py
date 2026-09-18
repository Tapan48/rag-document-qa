import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.ingestion.chunking import chunk_units
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError, embed_texts
from app.ingestion.extraction import ExtractionError, extract_units
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus

MAX_EMBEDDING_ATTEMPTS = 3


@celery_app.task(name="app.ingestion.tasks.process_document")
def process_document(document_id: str) -> None:
    db = SessionLocal()
    try:
        run_ingestion(db, document_id)
    finally:
        db.close()


def run_ingestion(db: Session, document_id: str) -> None:
    document = _lock_document(db, document_id)
    if document is None or document.status == DocumentStatus.READY:
        return

    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    db.commit()

    try:
        extension = Path(document.storage_path).suffix
        units = extract_units(Path(document.storage_path), extension)
        chunks = chunk_units(units)
        if not chunks:
            raise ExtractionError("No content extracted from document")
        vectors = _embed_with_retry([chunk.text for chunk in chunks])
    except ExtractionError as exc:
        _mark_failed(db, document, str(exc))
        return
    except EmbeddingTransientError:
        _mark_failed(db, document, "Embedding provider unavailable after retries")
        return
    except EmbeddingError:
        _mark_failed(db, document, "Embedding generation failed")
        return
    except Exception:
        _mark_failed(db, document, "Unexpected processing error")
        return

    document = _lock_document(db, document_id)
    if document is None or document.status == DocumentStatus.READY:
        return

    for chunk, vector in zip(chunks, vectors):
        db.add(
            Chunk(
                document_id=document.id,
                position=chunk.position,
                text=chunk.text,
                chunk_metadata=chunk.metadata,
                embedding=vector,
            )
        )
    document.status = DocumentStatus.READY
    document.error_message = None
    db.commit()


def _embed_with_retry(texts: list[str]) -> list[list[float]]:
    last_exc: EmbeddingTransientError | None = None
    for attempt in range(MAX_EMBEDDING_ATTEMPTS):
        try:
            return embed_texts(texts)
        except EmbeddingTransientError as exc:
            last_exc = exc
            if attempt < MAX_EMBEDDING_ATTEMPTS - 1:
                time.sleep(2**attempt)
    raise last_exc


def _lock_document(db: Session, document_id: str) -> Document | None:
    return db.execute(
        select(Document).where(Document.id == uuid.UUID(document_id)).with_for_update()
    ).scalar_one_or_none()


def _mark_failed(db: Session, document: Document, message: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error_message = message
    db.commit()
