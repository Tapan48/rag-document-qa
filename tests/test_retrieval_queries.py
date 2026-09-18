import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.retrieval.queries import retrieve_chunks

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


def _create_document(
    db_session, owner: User, filename: str, status: DocumentStatus = DocumentStatus.READY
) -> Document:
    document = Document(
        owner_id=owner.id,
        filename=filename,
        storage_path=f"/data/uploads/{filename}",
        status=status,
    )
    db_session.add(document)
    db_session.flush()
    return document


def _add_chunk(db_session, document: Document, position: int, text: str, embedding, metadata=None):
    db_session.add(
        Chunk(
            document_id=document.id,
            position=position,
            text=text,
            chunk_metadata=metadata or {},
            embedding=embedding,
        )
    )
    db_session.flush()


def test_ranks_by_cosine_distance(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner, "doc.txt")
    _add_chunk(db_session, document, 0, "far", _one_hot(1))
    _add_chunk(db_session, document, 1, "near", _one_hot(0))

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert [r.text for r in results] == ["near", "far"]
    assert results[0].distance < results[1].distance


def test_excludes_other_owners_chunks(db_session):
    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    own_doc = _create_document(db_session, owner, "own.txt")
    other_doc = _create_document(db_session, other, "other.txt")
    _add_chunk(db_session, own_doc, 0, "mine", _one_hot(0))
    _add_chunk(db_session, other_doc, 0, "not mine", _one_hot(0))

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert [r.text for r in results] == ["mine"]


def test_excludes_documents_not_ready(db_session):
    owner = _create_user(db_session, "owner@example.com")
    ready_doc = _create_document(db_session, owner, "ready.txt", DocumentStatus.READY)
    queued_doc = _create_document(db_session, owner, "queued.txt", DocumentStatus.QUEUED)
    _add_chunk(db_session, ready_doc, 0, "ready chunk", _one_hot(0))
    _add_chunk(db_session, queued_doc, 0, "queued chunk", _one_hot(0))

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert [r.text for r in results] == ["ready chunk"]


def test_excludes_null_embeddings(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner, "doc.txt")
    _add_chunk(db_session, document, 0, "has embedding", _one_hot(0))
    _add_chunk(db_session, document, 1, "no embedding", None)

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert [r.text for r in results] == ["has embedding"]


def test_document_ids_filter_restricts_results(db_session):
    owner = _create_user(db_session, "owner@example.com")
    doc_a = _create_document(db_session, owner, "a.txt")
    doc_b = _create_document(db_session, owner, "b.txt")
    _add_chunk(db_session, doc_a, 0, "from a", _one_hot(0))
    _add_chunk(db_session, doc_b, 0, "from b", _one_hot(0))

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), document_ids=[doc_a.id], top_k=5)

    assert [r.text for r in results] == ["from a"]


def test_respects_top_k(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner, "doc.txt")
    for i in range(5):
        _add_chunk(db_session, document, i, f"chunk-{i}", _one_hot(i))

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=2)

    assert len(results) == 2


def test_includes_filename_and_metadata(db_session):
    owner = _create_user(db_session, "owner@example.com")
    document = _create_document(db_session, owner, "report.pdf")
    _add_chunk(db_session, document, 0, "text", _one_hot(0), metadata={"pages": [3]})

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert results[0].filename == "report.pdf"
    assert results[0].source_metadata == {"pages": [3]}
    assert results[0].document_id == document.id


def test_returns_empty_list_when_no_ready_documents(db_session):
    owner = _create_user(db_session, str(uuid.uuid4()) + "@example.com")

    results = retrieve_chunks(db_session, owner.id, _one_hot(0), top_k=5)

    assert results == []
