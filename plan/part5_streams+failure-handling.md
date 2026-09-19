# Part 5 — Streaming and Failures

Status: **Complete and verified.**

## Goal

Stream answers as they are generated, return validated citations, and handle timeouts, failed processing, and disconnected clients.

Build on Part 4’s retrieval, generation schema, and citation validation. Keep `POST /questions` working.

## Implementation order

### 1. Extract shared question-processing logic

- Share document validation, retrieval preparation, and final answer validation between both endpoints.
- Preserve authentication, ownership filtering, and existing HTTP error behavior.
- Reject explicitly selected queued, processing, or failed documents with `409`.
- Copy retrieved passages into plain data objects and release database resources before streaming begins.

**Commit:** `refactor: share question preparation and answer validation`

### 2. Implement streaming generation

- Add an asynchronous OpenAI streaming service using the existing Luna model, prompt, reasoning setting, and structured answer schema.
- Use one generation request per answer.
- Incrementally decode the JSON `answer` field and emit only newly generated answer text. Handle escaped quotes, newlines, Unicode, and incomplete JSON fragments.
- Keep citation labels and the evidence flag for final validation; never expose raw model JSON as answer text.
- After provider completion, validate the full response and resolve citations using Part 4’s logic.

Use the Responses API’s streaming events. [Official streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses)

**Commit:** `feat: stream generated answer text from OpenAI`

### 3. Add the SSE endpoint

- Add authenticated `POST /questions/stream`, accepting the existing `QuestionRequest`.
- Complete ownership checks, question embedding, and retrieval before opening the SSE response.
- Run synchronous preparation outside the event loop, with its database session confined to that operation.
- Return `Content-Type: text/event-stream`, disable caching, and request that proxies avoid buffering.
- Encode each event’s data as JSON.

| Event | Payload and behavior |
|---|---|
| `answer` | `{"delta": "..."}` containing newly generated text |
| `citations` | `{"citations": [...]}` containing validated source details |
| `done` | The complete existing `QuestionResponse`, authoritative for the final answer |
| `error` | `{"code": "...", "message": "..."}` with a safe failure explanation |

- Successful order: answer events → one citations event → one done event.
- No retrieved passages: emit the existing fallback answer, empty citations, and done without calling generation.
- Treat streamed text as provisional until done.

**Commit:** `feat: add authenticated SSE question endpoint`

### 4. Handle failures and cancellation

- Before SSE starts, return ordinary HTTP errors using existing status codes.
- After SSE starts, emit one error event and close; never emit done afterward.
- Handle provider refusal, incomplete output, invalid citations, and unexpected stream termination as failures.
- Require substantive answers to have citations; insufficient-evidence answers must have none.
- Configure a 20-second provider inactivity timeout and a 60-second total generation deadline.
- Disable automatic retries for streaming generation to avoid duplicated answer text.
- On client disconnect, cancel generation consumption and close the upstream connection in cleanup.
- Document that clients must discard provisional output after error or connection loss without done.

**Commit:** `fix: handle streaming failures timeouts and disconnects`

### 5. Document and verify the streaming flow

- Add an authenticated `curl -N` example and document event ordering and error handling.
- Explain that browser clients need streaming `fetch` for this POST endpoint.
- Add safe logs for completion, timeout, failure, and cancellation without document contents or credentials.

**Commit:** `docs: document streaming API and verification`

## Validation

Include tests alongside each change:

- SSE framing, event order, and incremental delivery before generation finishes.
- JSON escapes and Unicode split across provider chunks.
- Authentication, ownership, and failed-document rejection before generation.
- Empty retrieval and insufficient-evidence responses.
- Provider failure before and after partial output; invalid citations and truncation.
- Disconnect cleanup with a blocked upstream stream and timeout enforcement.
- Regression tests for existing non-streaming answers.
- A real Docker streaming check using `curl -N`; verify incremental delivery over a real HTTP connection, since buffered test clients can hide it.

## Boundary

No frontend, WebSockets, conversation history, stream replay, database migrations, or new Celery jobs. Keep the existing embedding and generation models.

## Verification

43 new automated tests (129 total; `docker compose exec api pytest -v`), all against real Postgres with OpenAI mocked: `test_pipeline.py` (shared prep/finalize, including the new insufficient-evidence-must-have-zero-citations rule), `test_streaming.py` (the JSON-escape decoder and `_AnswerFieldExtractor` directly with plain strings — split unicode escapes, split key patterns, escaped quotes — plus `stream_answer` against a fake async stream: happy path, timeout, inactivity timeout, provider error, cancellation, no-final-text, malformed-final-JSON), `test_sse.py` (event ordering and every error path via a fake `stream_answer`), `test_questions_stream_api.py` (pre-stream `404`/`409`/`422`/`503` via `TestClient`, full SSE body content for the fallback and success cases).

Live checks against the real OpenAI API and the real `db`/`worker` stack, run for real (not claimed without running):

- **Streaming API shape**, confirmed empirically before writing any code: `client.responses.create(..., stream=True)` on `AsyncOpenAI` yields typed events; `ResponseTextDeltaEvent.delta` carries raw incremental JSON text of the structured output, `ResponseTextDoneEvent.text` carries the complete final JSON (so no need to reconstruct it from accumulated deltas), and `AsyncStream` exposes `close()`/`aclose()`.
- **Full pipeline via real `curl -N`**, timestamped with a Python client: real incremental delivery confirmed — dozens of individual `answer` events arriving at staggered wall-clock times (not one buffered burst), correct event order (`answer`* → `citations` → `done`), correct final content matching a manual non-streaming check of the same question.
- **Real client disconnect** (`curl --max-time` cutting a real stream mid-flight, confirmed by curl exit code 28 and partial SSE output received): server logged a clean `streaming answer generation cancelled (client disconnected)` and stayed fully healthy/responsive afterward — no hung state, no unhandled traceback.
- **OpenAI SDK upgrade regression check**: re-ran the full suite plus a live embeddings call after bumping `openai` — unaffected.

## Notes — one real bug caught by live testing, not just unit tests

The disconnect-cancellation logging silently never fired on the first two live attempts. Root cause: a client disconnect makes Starlette cancel the request's `asyncio.Task`, raising **`asyncio.CancelledError`** at whatever is currently `await`-ing — not `GeneratorExit`, which only fires from an explicit `.aclose()` call. These are unrelated `BaseException` subclasses. The `finally: await stream.close()` block still ran correctly either way (a bare `finally` doesn't care which exception type triggered it), so the actual upstream cleanup was never broken — but the observability (the log line the spec asks for) was, until `except (asyncio.CancelledError, GeneratorExit)` replaced the `GeneratorExit`-only handler. Re-verified live afterward: the log line now appears immediately on a real disconnect.

A second, related fix found the same way: `generate_question_stream_events`'s plain `async for item in stream_answer(...)` does **not** call `.aclose()` on `stream_answer`'s generator when the *outer* generator (`generate_question_stream_events` itself) is the one cancelled — only Python's garbage collector would eventually reach it. Wrapped in `contextlib.aclosing(...)` instead, so the inner generator (and therefore the real OpenAI connection) closes the instant the outer one does.

Both fixes came from actually running `curl --max-time` against the live stack and checking logs, not from reasoning about the code — matching the plan's instruction to record live-check results rather than assume unrun checks passed.
