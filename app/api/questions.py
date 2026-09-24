import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.retrieval.generation import (
    GenerationError,
    GenerationTimeoutError,
    GenerationUnavailableError,
    build_labeled_context,
    generate_answer,
)
from app.retrieval.pipeline import fallback_response, finalize_answer, prepare_question
from app.retrieval.schemas import QuestionRequest, QuestionResponse
from app.retrieval.citations import CITATION_ERROR_MESSAGE, CitationValidationError
from app.retrieval.sse import SSE_HEADERS, generate_question_stream_events, collect_web_answer

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", response_model=QuestionResponse)
async def ask_question(
    payload: QuestionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuestionResponse:
    prepared = await run_in_threadpool(prepare_question, db, current_user.id, payload.question, payload.document_ids, payload.web_search)

    if prepared.web_search:
        task = asyncio.create_task(collect_web_answer(prepared))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.5)
                if await request.is_disconnected():
                    raise HTTPException(499, "Client disconnected")
            return task.result()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    if not prepared.retrieved:
        return fallback_response()

    labeled_context = build_labeled_context(prepared.retrieved)

    try:
        generated = await run_in_threadpool(generate_answer, prepared.question, labeled_context)
    except GenerationTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Answer generation timed out")
    except GenerationUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Answer generation provider unavailable"
        )
    except GenerationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Answer generation failed")

    try:
        return finalize_answer(generated, prepared.retrieved)
    except CitationValidationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, CITATION_ERROR_MESSAGE)
    except GenerationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Answer generation failed")


@router.post("/stream")
def ask_question_stream(
    payload: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # Synchronous prep (ownership checks, embedding, retrieval) runs here, in
    # this plain `def` route -- FastAPI executes it in a worker thread, and
    # the `db` session is fully used and about to be torn down before the
    # async generator below (which never touches `db`) starts streaming.
    prepared = prepare_question(db, current_user.id, payload.question, payload.document_ids, payload.web_search)

    return StreamingResponse(
        generate_question_stream_events(prepared),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
