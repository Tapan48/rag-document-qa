# Demo Walkthrough

This walkthrough uses the fictional sample documents in [`samples/`](../samples/) — a fake smart-home hub's product guide, support policy, and troubleshooting guide (see `samples/generate_samples.py` for the source content). No personal or real-world data is used anywhere in this walkthrough or its screenshots.

**Status: verified.** Every step below was run against the real, running Docker stack — real registration, real uploads, real OpenAI calls, real streaming — using an automated browser (Playwright) driving the actual app at `http://localhost:5173`, on 2026-09-22. Screenshots are real captures from that run, not mockups.

## Prerequisites

- The stack running via `docker compose up --build` (see [README.md](../README.md))
- A funded `OPENAI_API_KEY` in `.env`

## Steps

### 1. Register and log in

Open `http://localhost:5173`, register a new account, then log in.

| Register | Log in |
|---|---|
| ![Register](screenshots/desktop-01-register.png) | ![Login](screenshots/desktop-02-login.png) |

### 2. Upload the samples and wait for processing

Upload all three files from `samples/`: `product_guide.pdf`, `support_policy.docx`, `troubleshooting_guide.txt`. Each shows `queued` → `processing` → `ready` (polled automatically every 2 seconds).

| Empty workspace | Uploading | All ready |
|---|---|---|
| ![Empty](screenshots/desktop-03-workspace-empty.png) | ![Uploading](screenshots/desktop-04-uploading.png) | ![Ready](screenshots/desktop-05-documents-ready.png) |

**Expected time:** a few seconds per document for text this short. **If a document gets stuck in `processing`** for more than a minute, check `docker compose logs worker` — most often this means `OPENAI_API_KEY` is missing or has no credit, in which case the document will instead land in `failed` with a specific error message rather than hanging.

### 3. Ask a supported question

With all three documents ready (in "All ready documents" mode — no selection needed), ask:

> What is the warranty period on the hub, and what does it exclude?

### 4. Observe streaming and inspect the cited passage

The answer appears progressively while generating, then the final answer appears with a `[S1] support_policy.docx` citation button. Click it to open the citation panel with the exact supporting passage.

| Streaming | Final answer + citation | Citation panel |
|---|---|---|
| ![Streaming](screenshots/desktop-06-streaming.png) | ![Answer](screenshots/desktop-07-answer-with-citation.png) | ![Citation panel](screenshots/desktop-08-citation-panel.png) |

### 5. Ask an unsupported question

> What is the retail price of the Solstice Home Hub?

None of the three documents mention a price, so this correctly returns `insufficient_evidence: true` with no fabricated answer and no citations.

![Insufficient evidence](screenshots/desktop-09-insufficient-evidence.png)

### 6. Verify isolation using a second user

Log out, register a second account, and ask the same question about the hub *without* uploading anything. Verified result: `insufficient_evidence: true`, and `GET /documents` for the second account returns an empty list — the first account's documents are never visible.

### 7. Delete the demo documents

Delete all three uploaded documents from the sidebar (confirmation dialog required for each). Verified result: the document list returns to empty, and `GET /documents` confirms `total: 0`.

## Mobile / responsive layout

At a 390px-wide viewport (iPhone-sized), the document sidebar collapses into a drawer opened via the hamburger icon in the header, and the Q&A area remains fully usable.

| Mobile workspace | Sidebar drawer | Mobile answer |
|---|---|---|
| ![Mobile workspace](screenshots/mobile-01-workspace.png) | ![Mobile drawer](screenshots/mobile-02-sidebar-drawer.png) | ![Mobile answer](screenshots/mobile-03-answer.png) |

## Keyboard navigation

Verified with an automated keyboard-only pass (no mouse), confirming every item Part 6 had left unconfirmed:

- Tab order on the login form: email → password → submit, form submits on Enter
- Tab order in the Q&A panel: question textarea → Clear → Ask
- The Ask button activates via Enter/Space when focused (not just click)
- The citation button is reachable by Tab and opens the citation panel via Enter
- `Escape` closes the citation panel
- The focused element always has a visible focus indicator (outline or box-shadow)
- The answer region has `aria-live="polite"` for screen-reader announcements
- No duplicate/nested `role="alert"` elements (the bug found and fixed during Part 6)

## Troubleshooting reference

| Symptom | Likely cause | What to check |
|---|---|---|
| Upload stuck in `processing` | Missing/invalid/rate-limited `OPENAI_API_KEY` | `docker compose logs worker` |
| Document lands in `failed` | Corrupt, encrypted, empty, or scanned-with-no-text file | The document's `error_message` field |
| Streaming answer never completes, no `error` shown | Client network interruption without a clean disconnect | Retry — the frontend discards provisional text and offers a Retry button on any stream failure |
| `insufficient_evidence: true` unexpectedly | No `ready` documents in scope, or the question truly isn't covered | Confirm document status is `ready`, and that the right selection mode/documents are chosen |
| Frontend can't reach the API | `frontend` container's `VITE_API_PROXY_TARGET` misconfigured | `curl http://localhost:5173/api/health` should return `{"status":"ok"}` |
