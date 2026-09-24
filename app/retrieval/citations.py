import re
from typing import Literal

from app.retrieval.generation import GenerationError
from app.retrieval.queries import RetrievedChunk
from app.retrieval.schemas import CitationOut


CitationFailureReason = Literal[
    "unknown_source", "inline_source_mismatch",
    "insufficient_evidence_with_citations", "missing_citations",
]
CITATION_ERROR_MESSAGE = "Answer could not be verified against its sources. Please retry."


class CitationValidationError(GenerationError):
    def __init__(self, reason: CitationFailureReason):
        # Only application-defined reasons belong in logs or exception messages.
        # Model-provided labels can contain arbitrary, potentially sensitive text.
        self.reason = reason
        super().__init__(reason)


_CITATION_MARKERS = re.compile(r"\[\s*([SW]\d+(?:\s*,\s*[SW]\d+)*)\s*\]")


def normalize_citation_markers(answer: str) -> str:
    """Expand comma-separated source IDs without adding/removing any IDs.

    This only normalizes syntax. Existence and metadata consistency must still
    be checked against the actual retrieved evidence before accepting an answer.
    """
    return _CITATION_MARKERS.sub(
        lambda match: " ".join(f"[{label.strip()}]" for label in match.group(1).split(",")),
        answer,
    )


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
            raise CitationValidationError("unknown_source")
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
