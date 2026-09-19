import json
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
    if not prepared.retrieved:
        response = fallback_response()
        yield format_sse_event("citations", {"citations": []})
        yield format_sse_event("done", response.model_dump(mode="json"))
        return

    labeled_context = build_labeled_context(prepared.retrieved)

    # `aclosing` guarantees stream_answer's generator is explicitly closed
    # (running its `finally: await stream.close()`) the instant this outer
    # generator is cancelled or garbage-collected early -- a plain
    # `async for` does NOT call `aclose()` on the inner iterator when the
    # *outer* generator is the one interrupted, which would otherwise leave
    # the upstream OpenAI connection open until GC gets to it.
    async with aclosing(stream_answer(prepared.question, labeled_context)) as events:
        async for item in events:
            if isinstance(item, AnswerDelta):
                yield format_sse_event("answer", {"delta": item.text})
            elif isinstance(item, GeneratedAnswer):
                try:
                    response = finalize_answer(item, prepared.retrieved)
                except GenerationError:
                    yield format_sse_event(
                        "error",
                        {"code": "generation_failed", "message": "Answer generation failed"},
                    )
                    return
                yield format_sse_event(
                    "citations",
                    {"citations": [c.model_dump(mode="json") for c in response.citations]},
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
