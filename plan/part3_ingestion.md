# Part 3 — Document Ingestion

Status: **Complete and verified.**

## Goal

Let authenticated users upload documents and have Celery convert them into searchable chunks and embeddings.

Build on the existing authentication, models, ownership helpers, and shared `/data/uploads` volume.

## Implementation order

### 1. Add ingestion configuration and schema updates

- Configure the upload directory, 20 MB limit, OpenAI API key, and chunk settings.
- Keep the existing embedding model and 1,536-dimensional vector configuration.
- Add a nullable document error message and a unique constraint on chunk document ID plus position through Alembic.

**Commit:** `feat: add ingestion settings and schema constraints`

### 2. Implement document management

- `POST /documents`: accept one file, save it under a generated filename, and return its document ID and processing status.
- `GET /documents`: list the authenticated user’s documents with pagination.
- `GET /documents/{id}`: return metadata, processing status, and a safe error message when processing fails.
- `DELETE /documents/{id}`: delete the document, associated chunks, and stored file.
- Reuse ownership checks; return `404` for inaccessible documents.
- Accept PDF, DOCX, and TXT. Enforce the size limit while reading uploads and clean up incomplete files.

**Commit:** `feat: add authenticated document management endpoints`

### 3. Implement text extraction and chunking

- Extract text from text-based PDFs, DOCX paragraphs/tables, and UTF-8 TXT files.
- Reject corrupt, encrypted, or empty documents; scanned PDFs require OCR and remain unsupported.
- Start with configurable 500-token chunks and 100-token overlap.
- Preserve PDF page numbers, DOCX paragraph/table references, or TXT line ranges.
- Keep chunk positions deterministic for repeatable processing.

**Commit:** `feat: implement document extraction and overlapping chunks`

### 4. Generate and store embeddings

- Add an embedding service using the configured OpenAI model.
- Batch embedding requests and validate returned vector dimensions.
- Store each chunk’s text, position, source metadata, and vector.
- Mark a document ready only when all its chunks and embeddings are saved successfully.

**Commit:** `feat: generate and persist document embeddings`

### 5. Connect Celery and handle retries

- Register the ingestion task and enqueue it only after the uploaded file and document record are saved.
- Return `202 Accepted` after successful queue submission.
- Process `queued → processing → ready`; use `failed` with a safe error message for terminal failures.
- Retry transient provider/network failures up to three times with exponential backoff.
- If queue submission fails, mark the document failed and return `503`.
- Save chunks and the ready status in one transaction. Lock and recheck the document before saving; skip deleted or already-ready documents.
- Serialize final writes with deletion so duplicate jobs cannot duplicate chunks or restore deleted content.

**Commit:** `feat: add background ingestion with safe retries and deletion`

## Validation

Include relevant tests with each commit:

- Supported formats, oversized files, invalid content, and empty extraction.
- Cross-user isolation for list, status, and delete.
- Chunk overlap, ordering, and source metadata.
- Embedding dimension checks and provider failures.
- Duplicate task delivery, retry exhaustion, and deletion during processing.
- One real Docker flow: upload → queued → processing → ready → stored vectors.

Use mocked embeddings in automated tests; keep the real provider check separate.

## Boundary

No retrieval, question answering, streaming, OCR, or frontend in Part 3. Update setup instructions for the new configuration and endpoints.

## Verification

50 automated tests pass (`docker compose exec api pytest -v`), all against the real Postgres `db` service with mocked OpenAI calls — extraction (PDF/DOCX/TXT, corrupt/encrypted/empty/scanned rejection), chunking (overlap, determinism, metadata merging), embeddings (batching, dimension validation, transient vs. permanent error classification), the ingestion state machine (happy path, extraction/embedding failures, retry exhaustion, duplicate task delivery, deletion during processing), and the document API (upload/list/get/delete, size/type limits, cross-user isolation, queue-failure → `503`).

Plus one real end-to-end Docker flow with a live OpenAI key: uploaded a `.txt` file via `POST /documents`, polled `GET /documents/{id}` through `queued` → `processing` → `ready`, then confirmed in Postgres that a chunk was stored with correct line-range metadata (`{"lines": [1, 4]}`) and a real 1536-dimension `text-embedding-3-small` vector (`vector_dims(embedding) = 1536`).

## Notes

- **Chunking** works by token-encoding all extracted units with `tiktoken` (`cl100k_base`), then sliding a fixed-size window over the flattened token sequence — this stays correct and deterministic even when a single unit (e.g. one PDF page) is larger or smaller than one chunk.
- **Retry design deviates from the original wording**: instead of Celery-level `self.retry()` (which would re-run extraction and chunking on every retry), transient embedding failures retry in-process inside `_embed_with_retry` (3 attempts, `2**attempt` backoff) — simpler to reason about, cheaper (doesn't redo unrelated work), and directly unit-testable without a running broker.
- **Concurrency safety** (duplicate delivery, delete-during-processing) is implemented via Postgres row locking (`SELECT ... FOR UPDATE`) on the `Document` row, taken once before processing starts and again immediately before the final chunk/status write — not a distributed lock. Sufficient at this scale; tested directly (not via real thread/process concurrency).
- **Known limitation**: `python-docx` doesn't expose paragraphs and tables in original document order, so DOCX chunk metadata may not reflect true document flow when tables are interleaved with paragraphs (table rows are extracted after all paragraphs). Documented in `CLAUDE.md`.
- **Environment gotcha hit during verification**: editing `.env` does not affect an already-running container — `docker compose up -d --force-recreate <service>` is required to pick up new environment variable values (`env_file` is only read at container creation, not bind-mounted or live-reloaded).
