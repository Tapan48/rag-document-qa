# RAG Document Q&A Backend

Backend for a RAG (Retrieval-Augmented Generation) document Q&A app.
Part 1 set up the project skeleton; Part 2 added user registration, login,
JWT authentication, and the `users`/`documents`/`chunks` tables; Part 3 adds
document upload, text extraction, chunking, and embedding generation via a
Celery background pipeline. Retrieval and Q&A are not implemented yet —
see `plan/`.

## Stack

Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Alembic, Celery, Redis,
Docker Compose.

## Setup

```bash
cp .env.example .env
```

## Start the stack

```bash
docker compose up --build
```

This starts four services: `db` (Postgres with pgvector, host port 5433),
`redis` (host port 6380), `api` (FastAPI, host port 8010), and `worker`
(Celery worker). Host ports are non-default to avoid clashing with other
local services; containers still talk to each other over the internal
Docker network using the default ports.

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

## Run tests

```bash
docker compose exec api pytest -v
```

Tests run against the real Postgres `db` service; each test runs inside a
transaction that's rolled back afterward, so nothing persists.

## Verify

- Health check: `curl http://localhost:8010/health` should return `{"status":"ok"}`.
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

Add `-v` to also remove the `pgdata`/`uploads` volumes and start clean.
