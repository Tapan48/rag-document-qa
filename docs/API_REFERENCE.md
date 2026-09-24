# API Reference

`GET /auth/config` returns `registration_mode` (`open`, `approval`, or `closed`)
and a compatibility `registration_enabled` boolean, true only for `open`.
In approval mode, `POST /auth/register` requires an `invitation_token` alongside
email/password. The token is bound to that email, expires after seven days,
and is consumed atomically with account creation. Closed mode rejects signup.
`GET /auth/me` and user responses include `is_admin`; clients cannot assign it.
Production routes have an `/api` prefix.

Access endpoints:

| Method and path | Purpose |
| --- | --- |
| `POST /auth/access-requests` | Email-only access request; generic 202; 429 on global notification limit, 503 on Redis outage |
| `POST /auth/invitations/validate` | Body `{ "token": "..." }`; returns invited email and expiry; invalid/revoked/expired/used tokens return 400 |
| `GET /admin/access-requests?offset=0&limit=20` | Admin-only paginated requests, including the five latest delivery records per request |
| `POST /admin/access-requests/{id}/approve` | Admin approves or resends; replaces previous invitation; 409 for an existing account |
| `POST /admin/access-requests/{id}/reject` | Admin rejects and revokes an unused invitation; 409 if already registered |
| `POST /admin/access-emails/{id}/retry` | Admin retries failed or stalled delivery; 409 if not retryable |

Administrator routes require the existing Bearer token and a server-assigned
administrator flag. Notification links are navigation only; decisions require
an authenticated POST. See [setup and recovery](PUBLIC_DEPLOYMENT.md).


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

The question is embedded with the same model used for ingestion, then the 5 nearest chunks (cosine distance, exact search — no vector index) owned by the caller are retrieved and sent to the configured chat model via the Responses API with structured output. With `web_search` omitted or false, the model may only answer from those passages, must cite which ones it used, and any text inside a document is treated as untrusted data, not instructions. Citations are resolved server-side against the actual retrieved chunks — the model's own claims about filenames or page numbers are never trusted directly. An unrelated question, or one with no ready documents at all, returns `insufficient_evidence: true` with no citations instead of a fabricated answer.

`document_ids` must reference documents you own and that are `ready` (`404`/`409` otherwise); passing an explicit empty list is rejected (`422`) — omit the field entirely to search everything.

## Optional web research

Both question endpoints accept `"web_search": true` (default `false`). For example:

```json
{"question":"Compare this board with Arduino Nano Every using official specifications.","web_search":true}
```

Omit `document_ids` to use all your ready documents, or research without documents when none are ready. An explicit selection still requires a nonempty list of owned, ready IDs. Ownership and readiness checks run before searching.

Research first creates a short product/specification brief without tools, then calls the web tool with `tool_choice="required"`. Only that brief reaches the search-enabled call; full retrieved passages are not passed to it. Both steps use OpenAI and count toward API usage. Brief extraction is a privacy precaution, not a guarantee that sensitive identifiers can never escape. Documents and web pages are treated as untrusted data.

Responses add `web_search_performed` and `web_citations` (empty when off). Document citations add `source_id`, such as `S2`. Web citations contain:

```json
{"source_id":"W1","title":"Manufacturer specification","url":"https://example.com/spec","researched_at":"2026-09-24T09:00:00Z"}
```

Inline `[S2]` / `[W1]` markers resolve to real retrieved passages or provider URL annotations. Unknown or inconsistent source IDs fail validation. The research timestamp records when the search ran, not when a page was published. If a search returns no usable cited findings, the answer must acknowledge the missing evidence; search failures return an error instead of silently falling back.

Defaults, configurable through environment variables:

| Setting | Default |
| --- | --- |
| `WEB_SEARCH_MODEL` | `gpt-5.6-luna` |
| `WEB_SEARCH_MAX_TOOL_CALLS` | `3` |
| `WEB_SEARCH_TIMEOUT_SECONDS` | `90` (brief and research together) |
| `WEB_SEARCH_MAX_OUTPUT_TOKENS` | `3000` (research response) |
| `ANSWER_TIMEOUT_SECONDS` | `60` (streamed generation, also used by non-streaming web mode) |

Research has no background jobs or persistence. Stop/disconnect cancels the active research or generation operation and closes its provider connection. Upstream work already performed may still be billed. These per-request limits are not an account spending cap.

When web mode includes documents, its preparatory question-embedding call has a 20-second provider timeout and no automatic retry. Provider failure returns 503 before the SSE stream opens. The research deadline begins after retrieval; it is not a total request deadline.

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
| `status` | `{"phase":"searching"}` or `{"phase":"generating"}` | Web mode progress |
| `answer` | `{"delta": "..."}` | A newly-generated fragment of the answer text |
| `citations` | `{"citations": [...], "web_citations": [...]}` | The final, resolved list of citations |
| `done` | The full `QuestionResponse` (`answer`, `citations`, `web_citations`, `web_search_performed`, `insufficient_evidence`) | Authoritative final result |
| `error` | `{"code": "...", "message": "..."}` | Something failed; no `done` follows |

In web mode, `status: searching` precedes research, and `status: generating` precedes generation; keepalive comments may arrive during research. Successful answer order is zero-or-more `answer` events, then exactly one `citations` event, then exactly one `done` event. On failure, exactly one `error` event is emitted instead and the stream ends. **Never treat text from `answer` events as final** — only the `done` event's `answer` field is authoritative (see [ARCHITECTURE.md](ARCHITECTURE.md#2-question-answering-ask--grounded-cited-answer) for why). With web search off, if no ready documents exist at all, the stream skips generation entirely and goes straight to `citations` (empty) then `done`.

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

Web research failures use `web_search_timeout`, `web_search_unavailable`, or `web_search_failed`; non-streaming requests map these to 504, 503, or 502 respectively.
