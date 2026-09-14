# Part 1 — Foundation

Status: **Complete and verified.**

Stack: Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Alembic, Celery, Redis, Docker Compose.

Scope: project skeleton only. Explicitly excludes authentication, application tables, document endpoints, ingestion logic, embeddings, Q&A, and streaming — those start in later parts (see `PLAN_main.md`).

## Steps

1. **Project structure and dependencies** — separate `app/api`, `app/database`-equivalent module, `app/ingestion`, `app/retrieval` packages; `requirements.txt`; `.gitignore`.
   Commit: `chore: initialize project structure and dependencies`

2. **Environment configuration** — settings loaded from environment variables; `.env.example` committed, real `.env` gitignored.
   Commit: `feat: configure environment settings`

3. **FastAPI application** — app instance + `GET /health`.
   Commit: `feat: set up FastAPI app and health endpoint`

4. **Database foundation** — SQLAlchemy engine/session config; Alembic initialized; migration enabling the `pgvector` extension.
   Commit: `feat: configure SQLAlchemy and Alembic migrations`

5. **Background worker foundation** — Celery app configured against Redis, ready for future ingestion tasks (no task logic yet).
   Commit: `feat: configure Celery app with Redis`

6. **Docker setup** — Dockerfile; `docker-compose.yml` with `api`, `db` (pgvector-enabled Postgres image), `redis`, `worker`; persistent DB volume; shared uploads volume between `api`/`worker`; README with setup/migrate/start/verify/stop instructions.
   Commit: `chore: add Dockerfile and Compose services`

## Verification

All checks confirmed against the running Docker Compose stack:

| Check | Result |
|---|---|
| All services start | `db`, `redis` healthy; `api`, `worker` running |
| `GET /health` responds | `{"status":"ok"}` |
| API connects to PostgreSQL | Alembic ran migrations against `db` successfully |
| Alembic migrations run + pgvector enabled | `vector` extension v0.8.0 installed |
| Celery worker connects to Redis | `celery inspect ping` → `pong` |

## Notes

- Host ports were remapped (API `8010`, Postgres `5433`, Redis `6380`) because the defaults were already in use by other local services/containers on this machine. Internal container-to-container communication is unaffected. See `README.md`.
- Committed as the 6 commits above and pushed to `https://github.com/Tapan48/rag-document-qa` (`main`).
