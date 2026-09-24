import uuid
import re
import logging
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.documents.queries import get_owned_document
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError, embed_texts
from app.models.document import Document, DocumentStatus
from app.retrieval.citations import CitationValidationError, normalize_citation_markers, resolve_citations
from app.retrieval.generation import GeneratedAnswer
from app.retrieval.queries import RetrievedChunk, retrieve_chunks
from app.retrieval.schemas import QuestionResponse
from app.retrieval.research import ResearchResult

FALLBACK_ANSWER = "No processed documents were found to answer this question."
logger = logging.getLogger(__name__)


@dataclass
class PreparedQuestion:
    question: str
    retrieved: list[RetrievedChunk]
    web_search: bool = False


def prepare_question(
    db: Session,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID] | None,
    web_search: bool = False,
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

    if web_search and db.scalar(select(Document.id).where(
        Document.owner_id == owner_id, Document.status == DocumentStatus.READY
    ).limit(1)) is None:
        return PreparedQuestion(question=question, retrieved=[], web_search=True)

    try:
        # Web research has its own deadline after retrieval. Bound preparation
        # too, without changing the ingestion worker's batching/retry behavior.
        options = {"timeout_seconds": 20.0} if web_search else {}
        question_embedding = embed_texts([question], **options)[0]
    except EmbeddingTransientError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding provider unavailable")
    except EmbeddingError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not process question")

    retrieved = retrieve_chunks(db, owner_id, question_embedding, document_ids)
    return PreparedQuestion(question=question, retrieved=retrieved, web_search=web_search)


def fallback_response() -> QuestionResponse:
    return QuestionResponse(answer=FALLBACK_ANSWER, citations=[], insufficient_evidence=True)


def finalize_answer(
    generated: GeneratedAnswer, retrieved: list[RetrievedChunk], research: ResearchResult | None = None
) -> QuestionResponse:
    try:
        return _finalize_answer(generated, retrieved, research)
    except CitationValidationError as exc:
        logger.warning("answer citation validation failed: reason=%s", exc.reason)
        raise


def _finalize_answer(
    generated: GeneratedAnswer, retrieved: list[RetrievedChunk], research: ResearchResult | None
) -> QuestionResponse:
    answer = normalize_citation_markers(generated.answer)
    web_sources = {s.source_id: s for s in research.sources} if research is not None else {}
    document_labels = []
    web_citations = []
    for label in dict.fromkeys(generated.cited_labels):
        if label in web_sources:
            web_citations.append(web_sources[label])
        else:
            document_labels.append(label)  # resolve_citations rejects unknown S/W labels
    citations = resolve_citations(document_labels, retrieved)
    if research is not None:
        inline = set(re.findall(r"\[([SW]\d+)\]", answer))
        if inline != set(generated.cited_labels):
            raise CitationValidationError("inline_source_mismatch")
    if generated.insufficient_evidence:
        if citations or web_citations:
            raise CitationValidationError("insufficient_evidence_with_citations")
    elif not citations and not web_citations:
        raise CitationValidationError("missing_citations")
    return QuestionResponse(
        answer=answer, citations=citations, web_citations=web_citations,
        insufficient_evidence=generated.insufficient_evidence,
        web_search_performed=research is not None,
    )
