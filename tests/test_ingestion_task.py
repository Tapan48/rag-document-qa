import uuid

from app.ingestion import tasks
from app.ingestion.chunking import Chunk
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError
from app.ingestion.extraction import ExtractionError, TextUnit
from app.models.document import Document, DocumentStatus
from app.models.user import User


def _create_user_and_document(db_session, filename="doc.txt") -> Document:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()

    document = Document(
        owner_id=user.id,
        filename=filename,
        storage_path=f"/data/uploads/{uuid.uuid4()}.txt",
        status=DocumentStatus.QUEUED,
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_happy_path_marks_ready_and_saves_chunks(monkeypatch, db_session):
    document = _create_user_and_document(db_session)

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={"lines": [1, 1]})])
    monkeypatch.setattr(tasks, "embed_texts", lambda texts: [[0.1] * 1536 for _ in texts])

    tasks.run_ingestion(db_session, str(document.id))

    db_session.refresh(document)
    assert document.status == DocumentStatus.READY
    assert document.error_message is None
    assert len(document.chunks) == 1
    assert document.chunks[0].text == "hello"


def test_extraction_failure_marks_document_failed(monkeypatch, db_session):
    document = _create_user_and_document(db_session)

    def raise_extraction(path, ext):
        raise ExtractionError("corrupt file")

    monkeypatch.setattr(tasks, "extract_units", raise_extraction)

    tasks.run_ingestion(db_session, str(document.id))

    db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "corrupt file"
    assert document.chunks == []


def test_embedding_dimension_mismatch_marks_document_failed(monkeypatch, db_session):
    document = _create_user_and_document(db_session)

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={})])

    def raise_embedding_error(texts):
        raise EmbeddingError("dimension mismatch")

    monkeypatch.setattr(tasks, "embed_texts", raise_embedding_error)

    tasks.run_ingestion(db_session, str(document.id))

    db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED
    assert document.chunks == []


def test_transient_embedding_error_retries_then_fails(monkeypatch, db_session):
    document = _create_user_and_document(db_session)
    attempts = []

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={})])
    monkeypatch.setattr(tasks.time, "sleep", lambda seconds: None)

    def always_transient(texts):
        attempts.append(1)
        raise EmbeddingTransientError("timeout")

    monkeypatch.setattr(tasks, "embed_texts", always_transient)

    tasks.run_ingestion(db_session, str(document.id))

    db_session.refresh(document)
    assert len(attempts) == tasks.MAX_EMBEDDING_ATTEMPTS
    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Embedding provider unavailable after retries"


def test_transient_embedding_error_succeeds_after_retry(monkeypatch, db_session):
    document = _create_user_and_document(db_session)
    attempts = []

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={})])
    monkeypatch.setattr(tasks.time, "sleep", lambda seconds: None)

    def fail_once_then_succeed(texts):
        attempts.append(1)
        if len(attempts) < 2:
            raise EmbeddingTransientError("timeout")
        return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(tasks, "embed_texts", fail_once_then_succeed)

    tasks.run_ingestion(db_session, str(document.id))

    db_session.refresh(document)
    assert len(attempts) == 2
    assert document.status == DocumentStatus.READY


def test_missing_document_is_a_noop(db_session):
    tasks.run_ingestion(db_session, str(uuid.uuid4()))  # should not raise


def test_duplicate_delivery_does_not_duplicate_chunks(monkeypatch, db_session):
    document = _create_user_and_document(db_session)

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={})])
    monkeypatch.setattr(tasks, "embed_texts", lambda texts: [[0.1] * 1536 for _ in texts])

    tasks.run_ingestion(db_session, str(document.id))
    tasks.run_ingestion(db_session, str(document.id))  # duplicate task delivery

    db_session.refresh(document)
    assert document.status == DocumentStatus.READY
    assert len(document.chunks) == 1


def test_deletion_during_processing_prevents_chunk_write(monkeypatch, db_session):
    document = _create_user_and_document(db_session)
    document_id = document.id

    monkeypatch.setattr(tasks, "extract_units", lambda path, ext: [TextUnit(text="hello", source={"kind": "line", "line": 1})])
    monkeypatch.setattr(tasks, "chunk_units", lambda units: [Chunk(position=0, text="hello", metadata={})])

    def embed_and_delete_concurrently(texts):
        # simulate a concurrent DELETE /documents/{id} completing while embeddings were in flight
        db_session.delete(db_session.get(Document, document_id))
        db_session.commit()
        return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(tasks, "embed_texts", embed_and_delete_concurrently)

    tasks.run_ingestion(db_session, str(document_id))  # should not raise or resurrect the document

    assert db_session.get(Document, document_id) is None
