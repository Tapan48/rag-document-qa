from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.documents.queries import get_owned_document
from app.ingestion.embeddings import EmbeddingError, EmbeddingTransientError, embed_texts
from app.models.document import DocumentStatus
from app.models.user import User
from app.retrieval.citations import resolve_citations
from app.retrieval.generation import (
    GenerationError,
    GenerationTimeoutError,
    GenerationUnavailableError,
    build_labeled_context,
    generate_answer,
)
from app.retrieval.queries import retrieve_chunks
from app.retrieval.schemas import QuestionRequest, QuestionResponse

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", response_model=QuestionResponse)
def ask_question(
    payload: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuestionResponse:
    if payload.document_ids:
        for document_id in payload.document_ids:
            document = get_owned_document(db, document_id, current_user.id)
            if document.status != DocumentStatus.READY:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"Document {document_id} is not ready"
                )

    try:
        question_embedding = embed_texts([payload.question])[0]
    except EmbeddingTransientError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding provider unavailable")
    except EmbeddingError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not process question")

    retrieved = retrieve_chunks(db, current_user.id, question_embedding, payload.document_ids)

    if not retrieved:
        return QuestionResponse(
            answer="No processed documents were found to answer this question.",
            citations=[],
            insufficient_evidence=True,
        )

    labeled_context = build_labeled_context(retrieved)

    try:
        generated = generate_answer(payload.question, labeled_context)
    except GenerationTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Answer generation timed out")
    except GenerationUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Answer generation provider unavailable"
        )
    except GenerationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Answer generation failed")

    try:
        citations = resolve_citations(generated.cited_labels, retrieved)
    except GenerationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Answer generation failed")

    if not generated.insufficient_evidence and not citations:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Answer generation failed")

    return QuestionResponse(
        answer=generated.answer,
        citations=citations,
        insufficient_evidence=generated.insufficient_evidence,
    )
