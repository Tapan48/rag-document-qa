# RAG Document Q&A Backend

Foundation for a RAG (Retrieval-Augmented Generation) document Q&A backend.
This stage sets up the project skeleton only — no auth, tables, ingestion, or
Q&A logic yet.

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

This enables the `pgvector` extension in Postgres.

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
