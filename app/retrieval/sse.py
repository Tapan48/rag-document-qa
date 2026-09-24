import json
import asyncio
from contextlib import aclosing
from typing import AsyncIterator

from app.retrieval.generation import (
    GeneratedAnswer,
    GenerationError,
    GenerationTimeoutError,
    GenerationUnavailableError,
    build_labeled_context,
)
from app.retrieval.pipeline import PreparedQuestion, fallback_response, finalize_answer
from app.retrieval.streaming import AnswerDelta, stream_answer
from app.retrieval.schemas import QuestionResponse
from app.retrieval.citations import CITATION_ERROR_MESSAGE, CitationValidationError
from app.retrieval.research import research_web, ResearchError, ResearchTimeoutError, ResearchUnavailableError

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def generate_question_stream_events(prepared: PreparedQuestion) -> AsyncIterator[str]:
    """Async generator of pre-formatted SSE text chunks for POST /questions/stream.

    Successful order: zero or more `answer` events -> one `citations` event ->
    one `done` event. On any failure, emits exactly one `error` event and
    stops -- `done` is never emitted after `error`. Never touches the
    database (the caller must have already released it via prepare_question).
    """
    if not prepared.retrieved and not prepared.web_search:
        response = fallback_response()
        yield format_sse_event("citations", {"citations": []})
        yield format_sse_event("done", response.model_dump(mode="json"))
        return

    labeled_context = build_labeled_context(prepared.retrieved)

    research = None
    if prepared.web_search:
        yield format_sse_event("status", {"phase": "searching"})
        task = asyncio.create_task(research_web(prepared.question, labeled_context))
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=5)
                if not done:
                    yield ": keepalive\n\n"
            research = task.result()
        except ResearchError as exc:
            code = "web_search_timeout" if isinstance(exc, ResearchTimeoutError) else (
                "web_search_unavailable" if isinstance(exc, ResearchUnavailableError) else "web_search_failed"
            )
            yield format_sse_event("error", {"code": code, "message": str(exc)})
            return
        finally:
            if not task.done():
                task.cancel()
            # Await cancellation so the provider connection is closed on Stop/disconnect.
            await asyncio.gather(task, return_exceptions=True)
        yield format_sse_event("status", {"phase": "generating"})

    options = {"web_context": research.context} if research is not None else {}
    # `aclosing` guarantees stream_answer's generator is explicitly closed
    # (running its `finally: await stream.close()`) the instant this outer
    # generator is cancelled or garbage-collected early -- a plain
    # `async for` does NOT call `aclose()` on the inner iterator when the
    # *outer* generator is the one interrupted, which would otherwise leave
    # the upstream OpenAI connection open until GC gets to it.
    async with aclosing(stream_answer(prepared.question, labeled_context, **options)) as events:
        async for item in events:
            if isinstance(item, AnswerDelta):
                yield format_sse_event("answer", {"delta": item.text})
            elif isinstance(item, GeneratedAnswer):
                try:
                    response = finalize_answer(item, prepared.retrieved, research)
                except CitationValidationError:
                    yield format_sse_event(
                        "error", {"code": "generation_failed", "message": CITATION_ERROR_MESSAGE}
                    )
                    return
                except GenerationError:
                    yield format_sse_event(
                        "error",
                        {"code": "generation_failed", "message": "Answer generation failed"},
                    )
                    return
                yield format_sse_event(
                    "citations",
                    {"citations": [c.model_dump(mode="json") for c in response.citations],
                     "web_citations": [c.model_dump(mode="json") for c in response.web_citations]},
                )
                yield format_sse_event("done", response.model_dump(mode="json"))
                return
            elif isinstance(item, GenerationTimeoutError):
                yield format_sse_event(
                    "error", {"code": "timeout", "message": "Answer generation timed out"}
                )
                return
            elif isinstance(item, GenerationUnavailableError):
                yield format_sse_event(
                    "error",
                    {"code": "unavailable", "message": "Answer generation provider unavailable"},
                )
                return
            elif isinstance(item, GenerationError):
                yield format_sse_event(
                    "error", {"code": "generation_failed", "message": "Answer generation failed"}
                )
                return


async def collect_web_answer(prepared: PreparedQuestion) -> QuestionResponse:
    """Share research, limits and final validation with the non-streaming endpoint."""
    from fastapi import HTTPException
    async with aclosing(generate_question_stream_events(prepared)) as events:
        async for event in events:
            if event.startswith("event: done\n"):
                return QuestionResponse.model_validate_json(event.split("data: ", 1)[1].strip())
            if event.startswith("event: error\n"):
                error = json.loads(event.split("data: ", 1)[1])
                code = error["code"]
                status = 504 if "timeout" in code else 503 if "unavailable" in code else 502
                raise HTTPException(status, error["message"])
    raise HTTPException(502, "Answer generation failed")
