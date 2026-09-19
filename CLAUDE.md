# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Parts 1 (Foundation), 2 (Authentication and Ownership), 3 (Document Ingestion), and 4 (Retrieval and Answers) are complete — see `plan/part1_foundation.md`, `plan/part2_authentication.md`, `plan/part3_ingestion.md`, and `plan/part4_retrieval_generation.md` for what was built and how it was verified. Streaming is not implemented yet. The full roadmap (Parts 5–6) is in `plan/PLAN_main.md` — check it before assuming a feature is missing or planning new work.

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

New migration: `docker compose run --rm api alembic revision --autogenerate -m "description"` (works now that models are registered on `Base` via `app/models/__init__.py`, imported by `alembic/env.py`).

Run tests: `docker compose exec api pytest -v`. There is no lint tooling configured yet.

**`.env` changes require a container recreate, not just a restart**: `env_file: .env` in `docker-compose.yml` is only read when a container is *created*, not bind-mounted or live-reloaded — editing `.env` and running `docker compose restart` (or relying on the `api`/`worker` `--reload`/bind-mounts) will NOT pick up the change. Run `docker compose up -d --force-recreate api worker` after editing `.env`.

## Architecture

- `app/main.py` — FastAPI entrypoint; registers routers from `app/api/`.
- `app/api/` — route modules (`health.py`, `auth.py`). Route handlers stay thin; logic lives in `app/auth/service.py` and `app/documents/queries.py`.
- `app/models/` — SQLAlchemy ORM models (`User`, `Document`, `DocumentStatus`, `Chunk`), all imported in `app/models/__init__.py` so `Base.metadata` (and Alembic autogenerate) sees them. UUID primary keys throughout; `Document`→`Chunk` cascades on delete at the DB level (`ondelete="CASCADE"`); `Chunk.embedding` is a `pgvector` `Vector` column sized from `settings.embedding_dimensions`.
- `app/auth/` — `security.py` (Argon2 password hashing, PyJWT access tokens), `schemas.py` (pydantic request/response models), `service.py` (`register_user`, `authenticate_user` — normalizes emails to lowercase/stripped before lookup/insert), `dependencies.py` (`get_current_user`, a Bearer-token FastAPI dependency).
- `app/documents/queries.py` — `get_owned_document`/`get_owned_chunks`: shared ownership-scoping helpers used by the document endpoints and (eventually) retrieval; they raise `404` (not `403`) when a document is missing or owned by someone else, so ownership is never leaked. `app/documents/schemas.py` has the `DocumentPublic`/`DocumentList` pydantic models.
- `app/api/documents.py` — `POST/GET/GET{id}/DELETE /documents`. Upload validates by file extension (not client-supplied `Content-Type`, which can't be trusted), streams to disk in chunks while enforcing `settings.max_upload_mb`, and cleans up the partial file on any failure. If enqueueing the Celery task itself fails, the document is marked `failed` and the endpoint returns `503` rather than leaving it stuck `queued`.
- `app/ingestion/` — the document processing pipeline, split into pure/testable pieces:
  - `extraction.py` — `extract_units(path, extension)` returns a list of `TextUnit(text, source)` for `.pdf`/`.docx`/`.txt`. PDF units are per-page, DOCX units are per-paragraph plus per-table-row (paragraphs and tables are NOT interleaved in original document order — a `python-docx` limitation), TXT units are per-line. Raises `ExtractionError` for corrupt/encrypted/empty/scanned-with-no-text documents.
  - `chunking.py` — `chunk_units(units, chunk_size, overlap)` token-encodes all units with `tiktoken` (`cl100k_base`), slides a window over the flattened token sequence (deterministic, works regardless of unit-vs-chunk-size mismatch), and merges each covered unit's `source` into the chunk's metadata (`{"pages": [...]}`, `{"lines": [start, end]}`, or `{"paragraphs": [...], "tables": [...]}`).
  - `embeddings.py` — `embed_texts(texts, batch_size=100)` calls OpenAI in batches and validates each returned vector's dimension against `settings.embedding_dimensions`. Raises the module's own `EmbeddingTransientError` (rate limits/timeouts/connection/server errors) vs `EmbeddingError` (everything else, incl. dimension mismatch) — callers never need to know OpenAI's exception hierarchy.
  - `tasks.py` — the Celery task `process_document` wraps `run_ingestion(db, document_id)`, which is deliberately a plain function taking a `Session` (not a bound Celery task) so tests can call it directly against the transactional test session instead of a real `SessionLocal()`. It locks the `Document` row (`with_for_update`) both before starting and again before the final write, so a concurrent `DELETE` or a duplicate task delivery can't resurrect/duplicate data — if the row is gone or already `ready` by either check, it's a no-op. Transient embedding failures retry in-process up to `MAX_EMBEDDING_ATTEMPTS` (3) with `2**attempt` backoff (not Celery-level retry/requeue — simpler to reason about and test, and avoids redoing extraction/chunking on a transient embedding hiccup).
- `app/config.py` — single `Settings` (pydantic-settings) object read from environment / `.env`; includes JWT, embedding, ingestion, and answer-generation settings (`chat_model`, `reasoning_effort`, `retrieval_top_k`, `max_output_tokens`). Add new fields here as later parts need them.
- `app/database.py` — SQLAlchemy `engine`, `SessionLocal`, declarative `Base`, and the `get_db` FastAPI dependency. All ORM models subclass this `Base`. Celery tasks use `SessionLocal()` directly (no FastAPI request to inject `get_db` into).
- `app/celery_app.py` — Celery app using the same Redis URL as both broker and result backend, with `include=["app.ingestion.tasks"]` so the worker registers `process_document` on startup.
- `alembic/env.py` is wired directly to `app.config.settings.database_url` and `app.database.Base.metadata`, and imports `app.models` so autogenerate detects model changes — it does not read `sqlalchemy.url` from `alembic.ini` (that value is intentionally left blank). Migrations run inside the `api` container so they resolve the `db` hostname on the Compose network. pgvector's `Vector` type needs an explicit `import pgvector.sqlalchemy` added by hand to autogenerated migration files — Alembic doesn't add it itself.
- `app/retrieval/` — retrieval and answer generation, kept deliberately separate so Part 5 (streaming) can reuse both halves independently:
  - `queries.py` — `retrieve_chunks(db, owner_id, query_embedding, document_ids=None, top_k=5)` returns `RetrievedChunk` (chunk id, document id, filename, text, source metadata, distance). Filters by owner + `DocumentStatus.READY` + non-null embedding **before** ranking (via SQL `WHERE`, not post-filtering), then orders by `Chunk.embedding.cosine_distance(query_embedding)` — exact/brute-force search, no vector index. Optional `document_ids` narrows the join.
  - `generation.py` — `generate_answer(question, labeled_context)` calls OpenAI's Responses API (`client.responses.create`) with `settings.chat_model` (`gpt-5.6-luna`), `reasoning={"effort": settings.reasoning_effort}`, and a strict JSON-schema `text.format` (`answer`, `cited_labels`, `insufficient_evidence`). The system prompt explicitly tells the model every passage is untrusted data, not instructions — verified against a real prompt-injection attempt during development (see `plan/part4_retrieval_generation.md`). Raises `GenerationTimeoutError`/`GenerationUnavailableError`/`GenerationError`, mirroring the `embeddings.py` exception-translation pattern so callers never touch OpenAI's exception hierarchy directly. `build_labeled_context(chunks)` numbers chunks `[S1]`, `[S2]`, ... in retrieval order.
  - `citations.py` — `resolve_citations(cited_labels, retrieved)` maps each `"S<n>"` label back to the actual `RetrievedChunk` at that position and returns real chunk id/document id/filename/metadata/text — the model's own label is only ever used as a lookup key, never trusted as content. Raises `GenerationError` on an unknown label.
  - `schemas.py` — `QuestionRequest` (rejects a blank/whitespace-only `question` and an explicit empty `document_ids` list — `None`/omitted means "search everything"), `CitationOut`, `QuestionResponse`.
- `app/api/questions.py` — `POST /questions`. Order of operations matters here: validates any given `document_ids` (ownership via `get_owned_document` → `404`; non-`READY` → `409`) **before** any provider call, then embeds the question, retrieves chunks, and — if nothing was retrieved (e.g. no ready documents at all) — returns `insufficient_evidence: true` without ever calling the chat model. After generation, it re-validates that a "substantive" answer (`insufficient_evidence: false`) actually carries at least one resolved citation, treating a citation-free substantive answer as malformed model output (`502`) rather than trusting it. Provider errors map to `503` (unavailable)/`504` (timeout)/`502` (malformed or refused) — never a raw provider error.
- `tests/conftest.py` wraps each test in a real Postgres transaction (`join_transaction_mode="create_savepoint"`) rolled back afterward, and overrides the `get_db` FastAPI dependency with that same session — tests hit the real `db` service, not a mock, and never leave data behind. It also has an autouse fixture that deletes any files a test wrote under `settings.upload_dir`, since file writes (unlike DB rows) aren't covered by the transaction rollback.
- Ingestion tests mock at the `app.ingestion.tasks` module level (`monkeypatch.setattr(tasks, "embed_texts", ...)` etc.) and call `run_ingestion` directly — never real OpenAI calls or a real Celery broker round-trip. `test_documents_api.py` similarly stubs `process_document.delay` so upload tests don't depend on (or block on) the worker actually processing anything. Retrieval/generation tests follow the same pattern: `test_retrieval_queries.py` uses real Postgres with hand-built one-hot embedding vectors (no OpenAI calls needed to test ranking/filtering), while `test_generation.py`/`test_questions_api.py` monkeypatch `_client`/`embed_texts`/`generate_answer` to fake OpenAI responses. The real end-to-end checks (real OpenAI embeddings + real Responses API call, real Celery worker) are manual smoke tests, not part of the automated suite.

### Docker Compose topology

Four services: `db` (`pgvector/pgvector:pg16`), `redis`, `api` (uvicorn with `--reload`, bind-mounts `./app`, `./alembic`, and `./tests`), `worker` (Celery). `api` and `worker` share a bind-mounted `./uploads` folder at `/data/uploads` where uploaded documents are stored (referenced by `Document.storage_path`) — a real, gitignored directory in the project root, not a Docker-managed named volume, so uploaded files are directly browsable/inspectable from the host; `db` has a persistent `pgdata` named volume.

Host port mappings are non-default (`8010→8000` for api, `5433→5432` for db, `6380→6379` for redis) because default ports were already occupied by unrelated local services when this was set up — don't assume 8000/5432/6379 are free on this machine. Container-to-container traffic is unaffected and still uses the default ports via `DATABASE_URL`/`REDIS_URL` in `.env`.

`.env` (gitignored) holds `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`/`JWT_ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES`, `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`, `OPENAI_API_KEY`/`UPLOAD_DIR`/`MAX_UPLOAD_MB`/`CHUNK_SIZE_TOKENS`/`CHUNK_OVERLAP_TOKENS`, and `CHAT_MODEL`/`REASONING_EFFORT`/`RETRIEVAL_TOP_K`/`MAX_OUTPUT_TOKENS`; `.env.example` is the committed template — keep them in sync when adding new settings. **Never read or print the real `.env` contents in a way that echoes `OPENAI_API_KEY` back into a response, log, or committed file.**

**OpenAI SDK is pinned at `3.16.2`** (upgraded from `1.51.0` in Part 4 for Responses API + structured outputs support) — this was a major-version jump (1.x→2.x→3.x) verified empirically (existing `embed_texts` re-tested, `client.responses.create` shape confirmed against the real API) rather than assumed compatible. Check `pip index versions openai` before assuming a newer/older version's API shape without similarly verifying it.
