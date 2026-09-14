# Part 2 — Authentication and Ownership

Status: **Complete and verified.**

## Goal

Let users register, log in, and authenticate with JWTs. Create the database tables needed for user-owned documents and chunks.

## Implementation order

### 1. Create database models and migrations

- **Users:** ID, email, password hash, creation timestamp.
- **Documents:** ID, owner ID, filename, storage path, processing status, creation timestamp.
- **Chunks:** ID, document ID, position, text, page/section metadata, embedding.
- Enforce unique normalized emails and foreign keys. Deleting a document cascades to its chunks.
- Match the vector dimension to the configured embedding model.

**Commit:** `feat: add user document and chunk models with migrations`

### 2. Implement registration

- Add `POST /auth/register`.
- Validate email and password; normalize emails consistently.
- Hash passwords using Argon2.
- Return public user information; never expose password hashes.
- Return `409` for duplicate emails.

**Commit:** `feat: implement user registration with password hashing`

### 3. Implement login and JWT creation

- Add `POST /auth/login` using email and password.
- Return a signed access token with a configurable expiry, defaulting to 30 minutes.
- Store the JWT signing secret in environment configuration.
- Return the same `401` response for unknown emails and incorrect passwords.

**Commit:** `feat: implement login and JWT access tokens`

### 4. Protect routes and establish ownership checks

- Add a reusable dependency that validates Bearer tokens and loads the user.
- Add `GET /auth/me` to verify authentication.
- Create owner-scoped document lookup and chunk-query helpers for later endpoints and retrieval.
- Return `404` when a requested document is missing or belongs to another user.

**Commit:** `feat: add authenticated user and ownership dependencies`

## Validation

Include tests with each corresponding commit:

- Migrations apply successfully.
- Registration stores a hash and rejects duplicate emails.
- Login succeeds with valid credentials and rejects invalid credentials.
- Protected routes reject missing, expired, or tampered tokens.
- Users cannot access another user’s documents or chunks through the ownership helpers.

## Defaults and boundary

Part 1 is complete. Use UUID identifiers and a single configured embedding model. Exclude refresh tokens, password reset, email verification, document endpoints, and actual retrieval until later parts.

## Verification

All checks confirmed against the running Docker Compose stack, plus a 14-test pytest suite run inside the `api` container against the real `db` service (each test wrapped in a transaction that's rolled back — no mocks, no leftover data):

| Check | Result |
|---|---|
| Migrations apply successfully | `alembic upgrade head` created `users`, `documents`, `chunks` with FKs, cascade deletes, unique email index, and the `vector(1536)` embedding column |
| Registration stores a hash and rejects duplicates | verified via curl and `test_auth.py` (password never equals stored hash; duplicate email → `409`) |
| Login succeeds/fails correctly | valid credentials → `200` + token; wrong password and unknown email both → `401` (no email enumeration) |
| Protected routes reject missing/expired/tampered tokens | missing → `403` (FastAPI `HTTPBearer` default), expired and tampered → `401` |
| Ownership isolation | `get_owned_document`/`get_owned_chunks` return `404` (never `403`, so existence isn't leaked) for another user's document, a missing document, and chunks under another user's document |

## Notes

- Password hashing: Argon2 via the `argon2-cffi` package directly (not passlib).
- JWT: `PyJWT`, `HS256`, default 30-minute expiry, secret from `JWT_SECRET`.
- Migration caveat: Alembic autogenerate detects `pgvector`'s `Vector` type but doesn't add its import — `import pgvector.sqlalchemy` had to be added by hand to the generated migration.
- `docker-compose.yml` gained two more bind mounts on `api` (`./alembic`, `./tests`) so Alembic-generated files and test runs persist to the host instead of living only inside the container.
