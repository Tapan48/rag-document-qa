from app.retrieval.generation import GenerationError
from app.retrieval.queries import RetrievedChunk
from app.retrieval.schemas import CitationOut


def resolve_citations(
    cited_labels: list[str], retrieved: list[RetrievedChunk]
) -> list[CitationOut]:
    label_to_chunk = {f"S{i + 1}": chunk for i, chunk in enumerate(retrieved)}

    citations = []
    seen_labels: set[str] = set()
    for label in cited_labels:
        if label in seen_labels:
            continue
        chunk = label_to_chunk.get(label)
        if chunk is None:
            raise GenerationError(f"Model cited an unknown source label: {label}")
        seen_labels.add(label)
        citations.append(
            CitationOut(
                source_id=label,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                source_metadata=chunk.source_metadata,
                text=chunk.text,
            )
        )
    return citations
