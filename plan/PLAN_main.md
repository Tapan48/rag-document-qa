# RAG Document Q&A Backend

## Goal and stack

Build a portfolio backend where users upload documents, ask questions, and receive streamed answers with source citations.

**Stack:** Python, FastAPI, PostgreSQL + pgvector, Celery, Redis, OpenAI, JWT authentication, Docker Compose.

## Implementation parts

### Part 1 — Foundation

- Set up FastAPI with separate API, database, ingestion, and retrieval modules.
- Configure SQLAlchemy, Alembic migrations, and environment variables.
- Run API, PostgreSQL, Redis, and Celery worker through Docker Compose.
- Add a health endpoint.

### Part 2 — Authentication

- Implement registration and login with hashed passwords and expiring JWTs.
- Create users, documents, and document-chunk tables.
- Restrict document access and retrieval to the authenticated owner.



### Part 3 — Document ingestion

- Add upload, list, processing-status, and delete endpoints.
- Support text-based PDF, DOCX, and TXT files up to 20 MB.
- Store files in a shared Docker volume.
- Use Celery to extract text, create overlapping chunks, generate embeddings, and save vectors.
- Preserve page or section metadata; track queued, processing, ready, and failed states.
- Make retries avoid duplicates and deletion prevent pending jobs from restoring content.



### Part 4 — Retrieval and answers

- Add `POST /questions` accepting a question and optional document IDs.
- Retrieve relevant chunks using vector similarity with ownership filtering.
- Generate answers from retrieved context, treating document instructions as untrusted.
- Return citations linked to retrieved passages; acknowledge insufficient evidence.



### Part 5 — Streaming and failures

- Add `POST /questions/stream` using SSE.
- Stream answer text, citations, completion, and error events.
- Handle provider timeouts, ingestion failures, and disconnected clients.



### Part 6 — Portfolio documentation

- Write setup instructions, API examples, an architecture diagram, and limitations.
- Prepare sample documents and a reproducible upload-to-answer demonstration.



## Validation

- Test authentication and cross-user isolation.
- Test extraction, ingestion retries, deletion during processing, and invalid uploads.
- Check citation accuracy and unsupported-question behavior.
- Test streaming success and failure.
- Mock providers in automated tests; verify one complete flow with real API calls.
- Evaluate 15 questions against expected supporting passages.



## Defaults

Backend-only, local Docker deployment, Swagger for API exploration. No OCR, frontend, agents, or cloud hosting in v1. Keep model names configurable.

**Claude handoff:** Implement each part in order, explain the changes, and verify its behavior before moving forward.