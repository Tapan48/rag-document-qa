# RAG Document Q&A

A full-stack RAG (Retrieval-Augmented Generation) document Q&A app.
Part 1 set up the project skeleton; Part 2 added user registration, login,
JWT authentication, and the `users`/`documents`/`chunks` tables; Part 3 added
document upload, text extraction, chunking, and embedding generation via a
Celery background pipeline; Part 4 added owner-scoped vector retrieval and
grounded, cited question answering; Part 5 added a streaming version of
question answering over Server-Sent Events; Part 6 added a React frontend
(document sidebar, streamed Q&A, citation panel). See `plan/`.

## Stack

**Backend:** Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Alembic,
Celery, Redis.
**Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui.
**Infra:** Docker Compose.

## Setup

```bash
cp .env.example .env
```

## Start the stack

```bash
docker compose up --build
```

This starts five services: `db` (Postgres with pgvector, host port 5433),
`redis` (host port 6380), `api` (FastAPI, host port 8010), `worker`
(Celery worker), and `frontend` (Vite dev server, host port 5173). Host
ports are non-default to avoid clashing with other local services;
containers still talk to each other over the internal Docker network using
the default ports.

## Run migrations

In a separate terminal, once `db` is healthy:

```bash
docker compose run --rm api alembic upgrade head
```

This enables the `pgvector` extension and creates the `users`, `documents`,
and `chunks` tables (plus, after Part 3, `documents.error_message` and a
uniqueness constraint on `(document_id, position)`).

Set `OPENAI_API_KEY` in `.env` before uploading documents — ingestion calls
OpenAI's embeddings API. Without a key (or with one lacking credits),
uploads still queue and process, but end in `status: "failed"` with a safe
error message.

## Auth

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

## Documents

```bash
# Upload (PDF, DOCX, or TXT, up to 20MB) -> 202 Accepted, status "queued"
curl -X POST http://localhost:8010/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/document.txt;type=text/plain"

# List your documents (paginated)
curl "http://localhost:8010/documents?limit=20&offset=0" -H "Authorization: Bearer <access_token>"

# Check processing status (queued -> processing -> ready/failed)
curl http://localhost:8010/documents/<document_id> -H "Authorization: Bearer <access_token>"

# Delete (removes DB row, chunks, and the stored file)
curl -X DELETE http://localhost:8010/documents/<document_id> -H "Authorization: Bearer <access_token>"
```

A background Celery task extracts text, splits it into ~500-token chunks
(100-token overlap), embeds each chunk via OpenAI, and stores the vectors
in `chunks.embedding`. Transient embedding failures (timeouts, rate limits)
retry up to 3 times with exponential backoff before the document is marked
`failed`.

## Questions

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

The question is embedded with the same model used for ingestion, then the 5
nearest chunks (cosine distance, exact search — no vector index yet) owned by
the caller are retrieved and sent to `gpt-5.6-luna` via the Responses API with
structured output. The model may only answer from those passages, must cite
which ones it used, and any text inside a document is treated as untrusted
data, not instructions. Citations are resolved server-side against the
actual retrieved chunks — the model's own claims about filenames or page
numbers are never trusted directly. An unrelated question, or one with no
ready documents at all, returns `insufficient_evidence: true` with no
citations instead of a fabricated answer.

`document_ids` must reference documents you own and that are `ready`
(`404`/`409` otherwise); passing an explicit empty list is rejected (`422`) —
omit the field entirely to search everything. Provider failures map to
`503` (unavailable), `504` (timeout), or `502` (malformed/refused output) —
never a raw provider error.

## Streaming questions

```bash
curl -N -X POST http://localhost:8010/questions/stream \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is this document about?"}'
```

`-N` (`--no-buffer`) is required for curl to print each line as it arrives
instead of waiting for the connection to close. Same request body and the
same validation as `POST /questions` (ownership/readiness checks, blank
question, empty `document_ids` — all rejected with ordinary HTTP errors
*before* the stream opens, exactly like the non-streaming endpoint). Once
the stream opens (`Content-Type: text/event-stream`), it emits a sequence
of SSE events:

| Event | Payload | Meaning |
|---|---|---|
| `answer` | `{"delta": "..."}` | A newly-generated fragment of the answer text |
| `citations` | `{"citations": [...]}` | The final, resolved list of citations |
| `done` | The full `QuestionResponse` (`answer`, `citations`, `insufficient_evidence`) | Authoritative final result |
| `error` | `{"code": "...", "message": "..."}` | Something failed; no `done` follows |

Successful order is zero-or-more `answer` events, then exactly one
`citations` event, then exactly one `done` event. On failure, exactly one
`error` event is emitted instead and the stream ends — **never** treat text
from `answer` events as final; only the `done` event's `answer` field is
authoritative. If no ready documents exist at all, the stream skips
generation entirely and goes straight to `citations` (empty) then `done`
(the same fallback response as the non-streaming endpoint).

`error.code` is one of `timeout` (exceeded the 60s total generation
deadline or 20s provider-inactivity timeout), `unavailable` (provider rate
limit/connection/server error), or `generation_failed` (malformed/refused
model output, or an internal citation-consistency check failed).

Browser clients: `EventSource` cannot send a `POST` body or custom headers,
so this endpoint isn't consumable via plain `new EventSource(url)`. Use
`fetch()` with a `ReadableStream` reader (or a library like
`@microsoft/fetch-event-source`) to read the SSE body from a `POST`
response instead.

## Frontend

Open `http://localhost:5173` once `docker compose up --build` is running.
Register, log in, upload a PDF/DOCX/TXT file, wait for it to reach `ready`,
then ask a question — the answer streams in and citation buttons open a
panel with the source passage.

The dev server proxies any request to `/api/...` to the FastAPI backend and
strips the prefix, so the browser only ever talks to `localhost:5173` (no
CORS, no exposed backend port, no API keys in the browser). In Compose,
that proxy target is `http://api:8000` (the `VITE_API_PROXY_TARGET` env var
on the `frontend` service); running the frontend standalone (outside
Compose) instead targets `http://localhost:8010` by default.

Run the frontend outside Docker:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies to localhost:8010
```

Frontend checks:

```bash
cd frontend
npm run lint         # oxlint
npm run typecheck    # tsc -b --noEmit
npm test             # Vitest + React Testing Library
npm run build         # typecheck + production Vite build
```

JWTs are kept in `sessionStorage` (a local-demo choice, cleared on logout
or tab close); the frontend never has access to `OPENAI_API_KEY` or the
database — those stay backend-only.

## Run tests

```bash
docker compose exec api pytest -v
```

Tests run against the real Postgres `db` service; each test runs inside a
transaction that's rolled back afterward, so nothing persists.

## Verify

- Health check: `curl http://localhost:8010/health` should return `{"status":"ok"}`.
- Frontend serving and proxying to the backend:
  ```bash
  curl -o /dev/null -w "%{http_code}\n" http://localhost:5173/       # -> 200
  curl http://localhost:5173/api/health                              # -> {"status":"ok"}
  ```
- pgvector enabled:
  ```bash
  docker compose exec db psql -U rag -d rag -c "\dx vector"
  ```
- Celery worker connected to Redis: check the `worker` container logs for
  `celery@... ready`, or run:
  ```bash
  docker compose exec worker celery -A app.celery_app inspect ping
  ```

## Stop the stack

```bash
docker compose down
```

Add `-v` to also remove the `pgdata` volume and start clean. Uploaded files
live in the `uploads/` folder in the project root (a real, gitignored
directory, not a Docker volume) — delete it manually if you want to clear
those too.
