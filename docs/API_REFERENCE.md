# API Reference

`GET /auth/config` is unauthenticated and returns only
`{"registration_enabled": true}` or `false`. When disabled,
`POST /auth/register` returns **403** for valid registration requests.
Existing users can still log in. Public HTTPS deployment forces registration
off; operators create reviewer accounts using the server CLI described in
[Public deployment](PUBLIC_DEPLOYMENT.md). Production routes have an `/api` prefix.

All examples assume the stack is running via `docker compose up --build` (see [README.md](../README.md)) and use the default port `8010`. Interactive, always-current docs are also available at **http://localhost:8010/docs** (Swagger UI, auto-generated from the FastAPI app).

## Authentication

```bash
curl -X POST http://localhost:8010/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"correct-horse-battery"}'

curl -X POST http://localhost:8010/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"correct-horse-battery"}'
# -> {"access_token": "...", "token_type": "bearer"}

curl http://localhost:8010/auth/me -H "Authorization: Bearer <access_token>"
```

JWTs expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60; see `.env.example`). Every other endpoint below requires `Authorization: Bearer <access_token>`.

## Documents

```bash
# Upload (PDF, DOCX, or TXT, up to 20MB) -> 202 Accepted, status "queued"
curl -X POST http://localhost:8010/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/document.txt;type=text/plain"

# List your documents (paginated, 20 per page by default)
curl "http://localhost:8010/documents?limit=20&offset=0" -H "Authorization: Bearer <access_token>"

# Check processing status (queued -> processing -> ready/failed)
curl http://localhost:8010/documents/<document_id> -H "Authorization: Bearer <access_token>"

# Delete (removes the DB row, its chunks, and the stored file)
curl -X DELETE http://localhost:8010/documents/<document_id> -H "Authorization: Bearer <access_token>"
```

A background Celery task extracts text, splits it into ~500-token chunks (100-token overlap), embeds each chunk via OpenAI, and stores the vectors in `chunks.embedding`. Transient embedding failures (timeouts, rate limits) retry up to 3 times with exponential backoff before the document is marked `failed`. See [ARCHITECTURE.md](ARCHITECTURE.md#1-ingestion-upload--searchable) for the full ingestion sequence.

**Ownership**: a document belonging to another user returns `404`, never `403` — existence and ownership are never distinguishable to a caller who doesn't own it.

## Questions (non-streaming)

```bash
curl -X POST http://localhost:8010/questions \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is this document about?"}'
# -> {"answer": "...", "citations": [...], "insufficient_evidence": false}

# Restrict to specific documents (omit document_ids to search all your ready documents)
curl -X POST http://localhost:8010/questions \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"...", "document_ids":["<document_id>"]}'
```

The question is embedded with the same model used for ingestion, then the 5 nearest chunks (cosine distance, exact search — no vector index) owned by the caller are retrieved and sent to the configured chat model via the Responses API with structured output. The model may only answer from those passages, must cite which ones it used, and any text inside a document is treated as untrusted data, not instructions. Citations are resolved server-side against the actual retrieved chunks — the model's own claims about filenames or page numbers are never trusted directly. An unrelated question, or one with no ready documents at all, returns `insufficient_evidence: true` with no citations instead of a fabricated answer.

`document_ids` must reference documents you own and that are `ready` (`404`/`409` otherwise); passing an explicit empty list is rejected (`422`) — omit the field entirely to search everything.

## Questions (streaming)

```bash
curl -N -X POST http://localhost:8010/questions/stream \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is this document about?"}'
```

`-N` (`--no-buffer`) is required for curl to print each line as it arrives instead of waiting for the connection to close. Same request body and validation as `POST /questions` — all rejected with ordinary HTTP errors *before* the stream opens. Once the stream opens (`Content-Type: text/event-stream`), it emits a sequence of SSE events:

| Event | Payload | Meaning |
|---|---|---|
| `answer` | `{"delta": "..."}` | A newly-generated fragment of the answer text |
| `citations` | `{"citations": [...]}` | The final, resolved list of citations |
| `done` | The full `QuestionResponse` (`answer`, `citations`, `insufficient_evidence`) | Authoritative final result |
| `error` | `{"code": "...", "message": "..."}` | Something failed; no `done` follows |

Successful order is zero-or-more `answer` events, then exactly one `citations` event, then exactly one `done` event. On failure, exactly one `error` event is emitted instead and the stream ends. **Never treat text from `answer` events as final** — only the `done` event's `answer` field is authoritative (see [ARCHITECTURE.md](ARCHITECTURE.md#2-question-answering-ask--grounded-cited-answer) for why). If no ready documents exist at all, the stream skips generation entirely and goes straight to `citations` (empty) then `done`.

Browser clients: `EventSource` cannot send a `POST` body or custom headers, so this endpoint isn't consumable via plain `new EventSource(url)`. The frontend uses `fetch()` with a `ReadableStream` reader instead (`frontend/src/lib/sse.ts`).

## Error reference

| Status | When |
|---|---|
| `400` | Malformed request body |
| `401` | Missing/invalid/expired token |
| `404` | Resource doesn't exist, or exists but belongs to another user |
| `409` | Referenced document isn't `ready` yet |
| `413` | Upload exceeds 20MB |
| `415` | Upload isn't PDF/DOCX/TXT |
| `422` | Validation error (e.g. blank question, explicit empty `document_ids`) |
| `502` | Provider returned malformed/refused output, or an internal citation-consistency check failed |
| `503` | Provider unavailable (rate limit/connection/server error), or the ingestion task itself failed to enqueue |
| `504` | Provider request timed out |

Streaming failures use the equivalent SSE `error.code`: `timeout`, `unavailable`, or `generation_failed` (see the streaming table above).
