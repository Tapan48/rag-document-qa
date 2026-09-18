import uuid

import pytest

from app.retrieval.citations import resolve_citations
from app.retrieval.generation import GenerationError
from app.retrieval.queries import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.txt",
        text=text,
        source_metadata={"pages": [1]},
        distance=0.1,
    )


def test_resolves_labels_to_matching_chunks():
    chunks = [_chunk("first"), _chunk("second")]

    citations = resolve_citations(["S1", "S2"], chunks)

    assert [c.text for c in citations] == ["first", "second"]
    assert citations[0].chunk_id == chunks[0].chunk_id
    assert citations[0].source_metadata == {"pages": [1]}


def test_deduplicates_repeated_labels():
    chunks = [_chunk("first")]

    citations = resolve_citations(["S1", "S1"], chunks)

    assert len(citations) == 1


def test_raises_on_unknown_label():
    chunks = [_chunk("first")]

    with pytest.raises(GenerationError):
        resolve_citations(["S99"], chunks)


def test_empty_labels_returns_empty_citations():
    chunks = [_chunk("first")]

    assert resolve_citations([], chunks) == []
