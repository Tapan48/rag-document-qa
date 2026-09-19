import asyncio
import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator, Union

import openai

from app.config import settings
from app.retrieval.generation import (
    GeneratedAnswer,
    GenerationError,
    GenerationTimeoutError,
    GenerationUnavailableError,
    _TRANSIENT_OPENAI_ERRORS,
    build_messages,
    parse_answer_json,
    response_format,
)

logger = logging.getLogger(__name__)

_async_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

INACTIVITY_TIMEOUT_SECONDS = 20.0
TOTAL_DEADLINE_SECONDS = 60.0

_ANSWER_KEY_PATTERN = '"answer"'
_VALUE_START_RE = re.compile(r'\s*:\s*"')
_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


@dataclass
class AnswerDelta:
    text: str


StreamOutcome = Union[GeneratedAnswer, GenerationTimeoutError, GenerationUnavailableError, GenerationError]


async def stream_answer(question: str, labeled_context: str) -> AsyncIterator[Union[AnswerDelta, StreamOutcome]]:
    """Yields AnswerDelta for each newly-decoded fragment of the answer text
    as it streams in, followed by exactly one terminal value: a
    GeneratedAnswer on success, or a Generation*Error instance describing
    the failure. Never raises -- the terminal value is how callers learn the
    outcome, so this can be consumed with a plain `async for` and no
    try/except around iteration itself.
    """
    extractor = _AnswerFieldExtractor()
    client = _async_client.with_options(max_retries=0)
    stream = None
    final_text: str | None = None

    try:
        async with asyncio.timeout(TOTAL_DEADLINE_SECONDS):
            stream = await client.responses.create(
                model=settings.chat_model,
                input=build_messages(question, labeled_context),
                reasoning={"effort": settings.reasoning_effort},
                max_output_tokens=settings.max_output_tokens,
                text=response_format(),
                stream=True,
            )

            while True:
                try:
                    event = await asyncio.wait_for(
                        stream.__anext__(), timeout=INACTIVITY_TIMEOUT_SECONDS
                    )
                except StopAsyncIteration:
                    break

                if event.type == "response.output_text.delta":
                    piece = extractor.feed(event.delta)
                    if piece:
                        yield AnswerDelta(piece)
                elif event.type == "response.output_text.done":
                    final_text = event.text
    except (asyncio.TimeoutError, openai.APITimeoutError) as exc:
        logger.warning("streaming answer generation timed out")
        yield GenerationTimeoutError(str(exc))
        return
    except _TRANSIENT_OPENAI_ERRORS as exc:
        logger.warning("streaming answer generation provider unavailable: %s", type(exc).__name__)
        yield GenerationUnavailableError(str(exc))
        return
    except openai.OpenAIError as exc:
        logger.warning("streaming answer generation failed: %s", type(exc).__name__)
        yield GenerationError(str(exc))
        return
    except (asyncio.CancelledError, GeneratorExit):
        # CancelledError: Starlette/uvicorn cancelling the request task on a
        # real client disconnect. GeneratorExit: someone calling
        # `.aclose()` on this generator directly (e.g. via `aclosing`).
        # Both must be re-raised, never swallowed.
        logger.info("streaming answer generation cancelled (client disconnected)")
        raise
    finally:
        if stream is not None:
            await stream.close()

    if final_text is None:
        logger.warning("streaming answer generation produced no output")
        yield GenerationError("Model returned no output")
        return

    try:
        result = parse_answer_json(final_text)
    except GenerationError as exc:
        logger.warning("streaming answer generation returned malformed output")
        yield exc
        return

    logger.info("streaming answer generation completed (%d chars)", len(result.answer))
    yield result


class _AnswerFieldExtractor:
    """Incrementally extracts newly-available literal text from the growing
    "answer" string field of a raw JSON object being streamed in fragments,
    without waiting for the JSON to be complete or well-formed yet.

    Known limitation: decodes any single \\uXXXX escape correctly (covers
    accented letters and non-Latin scripts), but does not recombine a
    \\uXXXX surrogate pair split across two escapes into one astral-plane
    character (rare emoji) -- not expected in practice for factual,
    document-grounded answers.
    """

    def __init__(self):
        self._buffer = ""
        self._found_value_start = False
        self._done = False

    def feed(self, chunk: str) -> str:
        if self._done or not chunk:
            return ""
        self._buffer += chunk

        if not self._found_value_start:
            idx = self._buffer.find(_ANSWER_KEY_PATTERN)
            if idx == -1:
                self._buffer = self._buffer[-len(_ANSWER_KEY_PATTERN):]
                return ""
            rest = self._buffer[idx + len(_ANSWER_KEY_PATTERN):]
            match = _VALUE_START_RE.match(rest)
            if not match:
                if len(rest) > 8:
                    self._buffer = rest
                return ""
            self._found_value_start = True
            self._buffer = rest[match.end():]

        decoded, consumed, closed = _decode_json_string_prefix(self._buffer)
        self._buffer = self._buffer[consumed:]
        if closed:
            self._done = True
        return decoded


def _decode_json_string_prefix(raw: str) -> tuple[str, int, bool]:
    out = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == '"':
            return "".join(out), i + 1, True
        if ch == "\\":
            if i + 1 >= n:
                break
            esc = raw[i + 1]
            if esc == "u":
                if i + 6 > n:
                    break
                out.append(chr(int(raw[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(_SIMPLE_ESCAPES.get(esc, esc))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out), i, False
