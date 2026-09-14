# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Part 1 (Foundation) is complete — see `plan/part1_foundation.md` for what was built and how it was verified. No auth, tables, document ingestion, embeddings, or Q&A logic exist yet. The full roadmap (Parts 2–6: authentication, document ingestion, retrieval/answers, streaming, documentation) is in `plan/PLAN_main.md` — check it before assuming a feature is missing or planning new work.

## Commands

```bash
cp .env.example .env                                    # one-time setup
docker compose up --build                                # start db, redis, api, worker
docker compose run --rm api alembic upgrade head          # apply migrations (run once db is healthy)
docker compose down                                       # stop (add -v to also drop volumes)
```

Verify the stack:
```bash
curl http://localhost:8010/health                                          # -> {"status":"ok"}
docker compose exec db psql -U rag -d rag -c "\dx vector"                  # confirm pgvector enabled
docker compose exec worker celery -A app.celery_app inspect ping           # confirm worker <-> redis
```

New migration: `docker compose run --rm api alembic revision -m "description"` (autogenerate isn't reliable until models are defined on `Base`).

There is no lint or test tooling configured yet.

## Architecture

- `app/main.py` — FastAPI entrypoint; registers routers from `app/api/`.
- `app/api/` — route modules (currently just `health.py`).
- `app/ingestion/` and `app/retrieval/` — empty packages reserved for Part 3 (document ingestion/Celery tasks) and Part 4 (vector retrieval + answer generation).
- `app/config.py` — single `Settings` (pydantic-settings) object read from environment / `.env`; add new config fields here as later parts need them (e.g. JWT secret, OpenAI key).
- `app/database.py` — SQLAlchemy `engine`, `SessionLocal`, declarative `Base`, and the `get_db` FastAPI dependency. Future ORM models should subclass this `Base`.
- `app/celery_app.py` — Celery app using the same Redis URL as both broker and result backend. No tasks are registered yet; when ingestion tasks are added, wire them via `include=[...]` here.
- `alembic/env.py` is wired directly to `app.config.settings.database_url` and `app.database.Base.metadata` — it does not read `sqlalchemy.url` from `alembic.ini` (that value is intentionally left blank). Migrations run inside the `api` container so they resolve the `db` hostname on the Compose network.

### Docker Compose topology

Four services: `db` (`pgvector/pgvector:pg16`), `redis`, `api` (uvicorn with `--reload`, bind-mounts `./app`), `worker` (Celery). `api` and `worker` share a named `uploads` volume at `/data/uploads` for future document storage; `db` has a persistent `pgdata` volume.

Host port mappings are non-default (`8010→8000` for api, `5433→5432` for db, `6380→6379` for redis) because default ports were already occupied by unrelated local services when this was set up — don't assume 8000/5432/6379 are free on this machine. Container-to-container traffic is unaffected and still uses the default ports via `DATABASE_URL`/`REDIS_URL` in `.env`.

`.env` (gitignored) holds `DATABASE_URL` and `REDIS_URL`; `.env.example` is the committed template — keep them in sync when adding new settings.
