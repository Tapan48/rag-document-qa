# Evaluation

15 document-only questions (Web search off) run against the real, running app (`POST /questions`, real OpenAI calls — no mocking) using the fictional sample documents in [`samples/`](../samples/): `product_guide.pdf`, `support_policy.docx`, `troubleshooting_guide.txt` (a fictional "Solstice Home Hub" smart-home device).

**Run date:** 2026-09-22
**Model settings:** `EMBEDDING_MODEL=text-embedding-3-small` (1536 dims), `CHAT_MODEL=gpt-5.6-luna`, `REASONING_EFFORT=none`, `RETRIEVAL_TOP_K=5`, `CHUNK_SIZE_TOKENS=500` / `CHUNK_OVERLAP_TOKENS=100` (all defaults from `app/config.py`)

Grading is by **fact correctness and citation support**, not exact wording — this pipeline uses a live LLM, so the same question can be phrased differently across runs while still being correct.

## Supported questions (10)

| # | Question | Expected facts | Source | Result |
|---|---|---|---|---|
| 1 | What wireless protocols does the Solstice Home Hub support? | Wi-Fi 6, Bluetooth 5.2, Zigbee 3.0, Thread; not HomeKit | product_guide.pdf | ✅ Correct, cited |
| 2 | How many smart devices can the hub support at once? | 150 | product_guide.pdf | ✅ Correct, cited |
| 3 | What is included in the box? | Hub, USB-C cable, 9W adapter, quick start guide, mounting bracket | product_guide.pdf | ✅ Correct, cited |
| 4 | What do the LED colors mean? | Solid blue=ready, blinking blue=pairing, solid green=connected/updated, blinking red=connectivity error, solid red=firmware update failed | product_guide.pdf | ✅ Correct, cited (all 5 states) |
| 5 | What is the warranty period on the hub, and what does it exclude? | 12 months; excludes water/physical damage and unauthorized modification | support_policy.docx | ✅ Correct, cited |
| 6 | How long is the return window and who pays return shipping? | 30 days; buyer pays unless defective | support_policy.docx | ✅ Correct, cited |
| 7 | What is Priority Care and what does it include? | $4.99/mo; phone support, 2-year extended warranty, priority firmware | support_policy.docx | ✅ Correct, cited |
| 8 | What are the support contact channels and response times? | Email (24-48h), live chat (weekdays 9-6 PT), phone (Priority Care only) | support_policy.docx | ✅ Correct, cited (all 3 channels) |
| 9 | What should I do if the hub won't power on? | Check cable/adapter, try different outlet, hold reset 10s | troubleshooting_guide.txt | ✅ Correct, cited |
| 10 | What are the steps to factory reset the hub? | Hold reset 15s until LED flashes white, re-pair in app | troubleshooting_guide.txt | ✅ Correct, cited |

**10/10 correct**, each with an accurate citation to the source document.

## Unsupported questions (3)

| # | Question | Why unsupported | Result |
|---|---|---|---|
| 11 | What is the retail price of the Solstice Home Hub? | Price is never mentioned in any document | ✅ `insufficient_evidence: true`, no citations |
| 12 | What color options is the hub available in? | Never mentioned | ✅ `insufficient_evidence: true`, no citations |
| 13 | Is there a student discount available for the Solstice Home app? | Never mentioned | ✅ `insufficient_evidence: true`, no citations |

**3/3 correct** — no fabricated answers.

Two other genuinely-tried "unsupported" candidates were dropped from this set after live testing revealed they don't actually test insufficient-evidence handling: *"Does the hub support Apple HomeKit?"* and *"What is the hub's battery life?"* both have **explicit negating facts** in `product_guide.pdf` ("does not support Apple HomeKit"; "has no internal battery"), so the model correctly answered from real content instead of returning insufficient evidence. That's correct behavior on the model's part — the flaw was in the original question design, not the app — but it means those two don't belong in the "no evidence exists" category.

## Multi-passage questions (2)

| # | Question | Requires combining | Result |
|---|---|---|---|
| 14 | If my hub's LED won't stop blinking red even after a factory reset and my warranty expired 3 months ago, what should I do and how much will it cost? | troubleshooting_guide.txt (persistent-fault → hardware issue) + support_policy.docx (out-of-warranty $39.99 flat fee) | ✅ Correct, cited both documents |
| 15 | Can I connect 160 smart devices to the hub, and if I have connectivity issues from having too many devices, what should I do? | product_guide.pdf (150-device max) + troubleshooting_guide.txt (reduce mesh congestion advice) | ✅ Correct, cited both documents |

**2/2 correct** — both correctly synthesized facts from two separate documents into one answer, with both sources cited.

## Summary

**15/15 correct** (10 supported, 3 correctly flagged insufficient-evidence, 2 correctly multi-document). Cross-user isolation was also verified live: a second account asking about the hub with no documents uploaded got `insufficient_evidence: true` and an empty document list (see [DEMO.md](DEMO.md#6-verify-isolation-using-a-second-user)).

## Web-search verification (2026-09-24)

This is a separate live comparison, **not an expansion of the 15-question document-only benchmark**. It ran against the current local Docker app with real OpenAI embeddings, web research, and streamed generation. A disposable non-admin account uploaded `public-board-specs.txt` and waited for `ready` before submitting the question in the browser with **Web search on** and **All ready documents** selected.

**Public sample:**

> Arduino Nano (classic) uses ATmega328P, operates at 5V, and has 2KB SRAM. No prices or stock availability are listed.

**Submitted question:**

> Compare this classic Arduino Nano with Nano Every: processor, voltage and SRAM. Use official sources, cite both source types, and flag unknown prices or availability.

### Observed live results

| Check | Observed result |
| --- | --- |
| Combined answer | A table reported ATmega328P / ATmega4809, 5 V / 5 V, and 2 KB / 6 KB SRAM for classic Nano / Nano Every, respectively. |
| Document evidence | S1 resolved to `public-board-specs.txt`; its cited classic-Nano specifications matched the uploaded passage. |
| Web evidence | The answer included W1–W3 inline links and three separate Arduino web-source entries with research timestamps. |
| Missing information | The answer explicitly said that prices and availability were unknown from the supplied evidence; it did not invent either. |
| Desktop | At 1440 × 1000, the completed answer displayed a comparison table and both citation types. |
| Mobile | At 430 × 1000, the page stayed within the viewport and the table scrolled horizontally within the answer panel. |
| Source display | Document and web sources appeared in separate lists; web entries included clickable URLs and research timestamps. |

Web sources returned in this run:

- **W1:** [Arduino Nano — Arduino Official Store](https://store.arduino.cc/arduino-nano?utm_source=openai).
- **W2:** [Nano Every hardware documentation — Arduino](https://docs.arduino.cc/hardware/nano-every?utm_source=openai).
- **W3:** [Arduino Nano Every with Headers — Arduino Official Store](https://store.arduino.cc/collections/most-popular/products/nano-every-with-headers?_fid=8d7dce536&_pos=8&_ss=c&utm_source=openai).

Evidence: [desktop comparison](screenshots/web-search-desktop.png), [mobile comparison](screenshots/web-search-mobile.png), and [source lists](screenshots/web-search-sources.png). The [walkthrough](DEMO.md#web-comparison-demonstration) embeds all three captures. The disposable account, uploaded file, document, and chunks were removed afterward.

### Separate automated coverage

Provider-mocked tests in [`tests/test_web_research.py`](../tests/test_web_research.py) cover required search calls, toggle-off behavior, no-document searches, ownership/readiness checks, citation validation, missing evidence, failures, deadlines, and cancellation. Frontend tests in [`WebSearch.test.tsx`](../frontend/src/pages/WebSearch.test.tsx) cover the toggle, retry-mode preservation, Stop, selection requirements, and safe Markdown/link rendering. These tests passed during feature verification; the screenshots are evidence of the live comparison and layout, not proof that every failure path was exercised live in this run.

One successful comparison is a smoke test, not a web-research accuracy benchmark. Source-ID validation checks provenance and consistency; it does not establish that every generated claim is correct. Prices and search results can change, listed prices do not guarantee stock, and these board specifications alone do not establish compatibility.

## Limitations

- **No OCR.** Scanned PDFs with no extractable text layer are rejected at ingestion (`ExtractionError`), not processed.
- **No conversation history.** Each question is answered independently; the UI shows only the latest question/answer pair and does not carry context between questions.
- **Exact (brute-force) vector search, no ANN index.** `retrieve_chunks` ranks by cosine distance with no `ivfflat`/`hnsw` index — correct at this dataset's scale, but would need an index (and an accuracy/speed tradeoff) at real production volume.
- **DOCX extraction ordering.** `python-docx` does not expose paragraphs and tables in their original interleaved document order — the current extraction emits all paragraphs, then all tables, which can separate a table from the paragraph that introduces it (see `app/ingestion/extraction.py`).
- **`sessionStorage` JWT storage.** A deliberate local-demo choice; it's accessible to any JavaScript running on the page and is cleared on tab close, not designed for production auth hardening.
- **External API cost and availability.** Every ingestion and every question makes real, billed OpenAI API calls; the app has no offline/mocked mode, and provider outages or rate limits surface as `failed` documents or `503`/`504` responses.
- **No guarantee of complete correctness.** Citations are resolved server-side and validated for internal consistency (a substantive answer always has ≥1 real citation), which rules out *fabricated* citations — but it does not mean the model's prose is always a perfect paraphrase of the source, and this evaluation (15 questions on ~1,100 words of fictional text) is not a statistically rigorous benchmark.
- **No claim of complete prompt-injection protection.** The system prompt instructs the model to treat document content as untrusted data, and this was verified against one real injection attempt during Part 4 development — that is evidence of resistance to that specific attempt, not a guarantee against all possible prompt-injection techniques.
