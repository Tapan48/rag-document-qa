import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.documents.queries import get_owned_document
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError, embed_texts
from app.models.document import DocumentStatus
from app.retrieval.citations import resolve_citations
from app.retrieval.generation import GeneratedAnswer, GenerationError
from app.retrieval.queries import RetrievedChunk, retrieve_chunks
from app.retrieval.schemas import QuestionResponse

FALLBACK_ANSWER = "No processed documents were found to answer this question."


@dataclass
class PreparedQuestion:
    question: str
    retrieved: list[RetrievedChunk]


def prepare_question(
    db: Session,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID] | None,
) -> PreparedQuestion:
    """Validate ownership/readiness and retrieve chunks. Raises HTTPException
    for any failure here, since this always runs before any provider call or
    (for streaming) before the SSE response has opened."""
    if document_ids:
        for document_id in document_ids:
            document = get_owned_document(db, document_id, owner_id)
            if document.status != DocumentStatus.READY:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"Document {document_id} is not ready"
                )

    try:
        question_embedding = embed_texts([question])[0]
    except EmbeddingTransientError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding provider unavailable")
    except EmbeddingError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not process question")

    retrieved = retrieve_chunks(db, owner_id, question_embedding, document_ids)
    return PreparedQuestion(question=question, retrieved=retrieved)


def fallback_response() -> QuestionResponse:
    return QuestionResponse(answer=FALLBACK_ANSWER, citations=[], insufficient_evidence=True)


def finalize_answer(
    generated: GeneratedAnswer, retrieved: list[RetrievedChunk]
) -> QuestionResponse:
    """Resolve citations and enforce answer/citation consistency: a
    substantive answer must have at least one citation, and an
    insufficient-evidence answer must have none. Raises GenerationError
    (transport-agnostic) on any inconsistency, left for the caller to map to
    an HTTP error or an SSE error event."""
    citations = resolve_citations(generated.cited_labels, retrieved)
    if generated.insufficient_evidence:
        if citations:
            raise GenerationError("Insufficient-evidence answer must not include citations")
    elif not citations:
        raise GenerationError("Substantive answer must include at least one citation")
    return QuestionResponse(
        answer=generated.answer,
        citations=citations,
        insufficient_evidence=generated.insufficient_evidence,
    )
