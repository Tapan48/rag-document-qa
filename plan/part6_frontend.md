# Part 6 — Frontend Implementation

## Goal and stack

Build a single workspace where users upload documents, ask questions, view streamed answers, and inspect citations.

**Stack:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, native `fetch`, and React hooks/Context.

**Layout:** Document sidebar, central Q&A area, and citation detail panel. Use a dark neutral theme, one blue accent, and responsive drawers on smaller screens.

## Implementation order

### 1. Update the main roadmap

Update `plan/PLAN_main.md`:

- Expand the goal and stack to include the React frontend.
- Add **Part 6 — Frontend** with authentication, document management, streamed Q&A, and citations.
- Move **Portfolio documentation to Part 7**, retaining its existing scope.
- Replace “backend-only” and “no frontend” defaults with a local full-stack application.
- Add browser-flow, accessibility, and frontend error-state validation.
- Keep Parts 1–5 intact.

Save this implementation plan as `plan/part6_frontend.md`.

**Commit:** `docs: add frontend as part 6 and move portfolio documentation to part 7`

### 2. Set up the frontend and API connection

- Create the application in `frontend/`, using npm with a committed lockfile.
- Configure Tailwind and shadcn components.
- Add `/login`, `/register`, and protected `/workspace` routes.
- Create typed API helpers matching existing backend schemas.
- Send browser requests to `/api`; configure Vite to proxy them to FastAPI and strip that prefix. This avoids local cross-origin requests. [Vite proxy documentation](https://vite.dev/config/server-options.html#server-proxy)
- Keep API keys and database credentials exclusively on the backend.

**Commit:** `feat: initialize React frontend and typed API client`

### 3. Implement authentication

- Connect registration and login forms to existing endpoints.
- After registration, direct users to login.
- Store the JWT in `sessionStorage`, as selected; validate restored sessions through `/auth/me`.
- Display validation errors and handle expired sessions by returning to login.
- Logout clears credentials, document state, and answers, and cancels active requests.
- Never persist passwords or document contents in browser storage.

**Commit:** `feat: add frontend registration login and session handling`

### 4. Build the document sidebar

- Support single-file upload for PDF, DOCX, and TXT, with the backend’s 20 MiB limit.
- Show uploading and processing states without inventing percentage progress.
- List documents with pagination, status badges, and processing errors.
- Poll tracked queued/processing documents every two seconds while visible; stop after ready/failed, logout, or unmount.
- Confirm deletions and update the list and selection after success.
- Provide “All ready documents” and “Selected documents” modes. Only ready documents are selectable; selected mode requires at least one selection.
- Show useful empty, loading, and request-failure states.

**Commit:** `feat: add document upload management and processing status`

### 5. Implement streamed Q&A

- Add a question input with the existing 2,000-character limit.
- Use authenticated streaming `fetch` for `POST /questions/stream`.
- Omit `document_ids` in all-documents mode; send selected IDs otherwise.
- Parse SSE incrementally, handling split network chunks, UTF-8 characters, and event boundaries.
- Display `answer` deltas provisionally; use `done` as the authoritative final response.
- On `error`, malformed events, or connection loss without `done`, discard provisional output and show a retry action.
- Add Stop through `AbortController`; cancel on logout or navigation.
- Allow one active question at a time. Show the latest question/answer pair without implying conversation memory.

**Commit:** `feat: add streamed question answering and cancellation`

### 6. Display source citations and finish interaction states

- Show citation buttons after successful completion.
- Open a panel containing filename, page/section references, and the returned supporting passage.
- Display existing metadata accurately, converting zero-based DOCX indices into human-readable numbering.
- Render answers and passages as text with preserved whitespace.
- Handle insufficient evidence explicitly.
- Add keyboard navigation, labeled controls, visible focus, accessible status messages, and mobile drawers.

**Commit:** `feat: add citation viewer and accessible workspace states`

### 7. Integrate local startup

- Add a frontend development service to Docker Compose on port `5173`, proxying to `api:8000`.
- Support standalone frontend development against `localhost:8010`.
- Add lint, type-check, test, and production-build commands.
- Document local startup and configuration now; leave the full portfolio presentation for Part 7.

**Commit:** `chore: integrate frontend with Docker Compose and development checks`

## Validation

Include relevant tests with each feature commit:

- Use Vitest and React Testing Library for authentication states, document polling, selection, and SSE parsing.
- Test expiry, logout during streaming, failed uploads, interrupted answers, and citation display.
- Run lint, type-checking, tests, and the production build.
- Verify desktop/mobile layouts and keyboard use in a real browser.
- Complete one live flow: register → login → upload → ready → streamed answer → inspect citation → delete.
- Check isolation with two users and confirm streaming remains incremental through the Vite proxy.

## Defaults and boundaries

Reuse existing backend endpoints and response schemas; no database migration or authentication redesign. Session storage is a local-demo choice and remains accessible to JavaScript. [MDN documentation](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage)

No persistent chat history, document preview/download, OCR, cloud hosting, or model changes. Part 7 remains portfolio documentation, sample documents, evaluation, and the reproducible demo.

## Status: Complete

All 7 steps implemented in `frontend/` (React 19 + TypeScript + Vite 8 + Tailwind v4 + shadcn/ui, React Router v7).

### Verification performed

- **Automated:** 45 Vitest + React Testing Library tests passing, covering SSE incremental parsing (`sse.test.ts`), the typed API client including 401 detection (`api.test.ts`), DOCX 0-based→1-based citation index formatting (`citations.test.ts`), document polling/upload/delete (`useDocuments.test.tsx`), session restore/expiry (`useAuth.test.tsx`), login form validation (`LoginPage.test.tsx`), and the end-to-end streamed question → citation → retry-on-error flow (`WorkspacePage.qa.test.tsx`, `WorkspacePage.test.tsx`).
- `npm run lint` (oxlint), `npm run typecheck` (`tsc -b --noEmit`), and `npm run build` (production Vite build) all pass with no errors.
- Backend regression suite (`docker compose exec api pytest -v`) re-run and still green — no backend changes were needed for Part 6.
- **Docker integration:** `frontend` Compose service builds and starts; `curl http://localhost:5173/` returns `200` (SPA served); `curl http://localhost:5173/api/health` returns `{"status":"ok"}`, confirming the Vite proxy correctly resolves to the `api` service by Docker Compose network name (`http://api:8000`), not `localhost`; a full `POST /api/auth/login` through that same proxy returned a real JWT, confirming the proxy forwards non-GET requests and bodies correctly, not just the health check. `npm run lint && npm run typecheck && npm test && npm run build` all run clean inside the `frontend` container.
- **Docker-specific fix:** Vitest's default parallel fork-worker pool reliably timed out starting workers inside this container (`[vitest-pool-runner]: Timeout waiting for worker to respond`) while working fine outside Docker — not a resource limit (container had 8 CPUs, <15% memory used). Fixed by setting `test.fileParallelism: false` in `vite.config.ts` so `npm test` runs test files sequentially; verified this makes `npm test` pass reliably (45/45) in both Docker and standalone environments with no extra flags.
- **Real bug found and fixed via this verification, not assumed correct from tests alone:** `QuestionPanel.tsx`'s error state nested a `role="alert"` div around shadcn's `Alert` component, which sets `role="alert"` internally — a screen reader would have double-announced every error. Caught because `findByRole('alert')` in `WorkspacePage.qa.test.tsx` matched two elements and timed out rather than erroring immediately; fixed by removing the redundant outer role, verified by re-running the test suite.

### Verification handed to the user

Per an explicit choice made during planning (no GUI browser tool is available in this environment), the plan's real-browser checks — desktop/mobile responsive layout, keyboard-only navigation, and the full live click-through (register → login → upload → ready → streamed answer → inspect citation → delete, plus two-user isolation) — are the user's own responsibility to click through against `http://localhost:5173` (Docker) or a standalone `npm run dev` server, the same way API behavior was hand-verified via curl/Swagger UI in earlier parts. These are not yet confirmed by either party as of this writing.

### Notable implementation decisions

- JWT kept in `sessionStorage` (per spec), restored via `/auth/me` on load; expired/invalid sessions redirect to `/login`.
- Document upload defers all format/size validation to the backend rather than duplicating its rules client-side, avoiding validation-logic drift between frontend and backend.
- `useQuestionStream` aborts its in-flight fetch on unmount (component teardown, navigation, logout) via an `AbortController` cleaned up in a `useEffect` return function.
- SSE parsing buffers across chunk/UTF-8/event-boundary splits rather than assuming each network chunk is a complete event — verified against the real streaming endpoint, not just synthetic single-chunk test fixtures.
