# RAG Document Q&A — Frontend

React + TypeScript + Vite + Tailwind CSS + shadcn/ui workspace for the RAG Document Q&A app: authentication, a document sidebar with upload/status/polling, streamed question answering, and a citation detail panel.

This is normally run via the root project's `docker compose up --build` (see the [repo README](../README.md)) — the instructions below are for running the frontend standalone, outside Docker, useful for faster local iteration.

## Prerequisites

- Node.js and npm
- The backend API running somewhere reachable (Docker Compose on `localhost:8010` by default, or your own local backend)

## Run standalone

```bash
npm install
npm run dev
```

By default this proxies `/api/*` requests to `http://localhost:8010` (Docker Compose's mapped API port), stripping the prefix so the browser only ever talks to `localhost:5173`. Point it at a different backend with:

```bash
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

The frontend never holds an OpenAI API key or a database credential — those stay backend-only; see `vite.config.ts` for the proxy configuration.

## Checks

```bash
npm run lint       # oxlint
npm run typecheck  # tsc -b --noEmit
npm test           # Vitest + React Testing Library
npm run build      # typecheck + production Vite build
```

## Notes

- JWTs are kept in `sessionStorage` (a local-demo choice, cleared on logout or tab close) — see `src/context/AuthContext.tsx`.
- SSE streaming (`POST /questions/stream`) is consumed via `fetch()` + a `ReadableStream` reader in `src/lib/sse.ts`, not `EventSource` (which can't send a POST body or custom headers).
- See the repo's [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for how this fits into the full stack.
