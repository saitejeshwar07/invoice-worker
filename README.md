# Autonomous AI Task Worker (CentrAlign intern assignment)

An AI worker that takes a plain-English task such as **"Process the latest invoice from AWS"** and completes it by
actually operating a real browser against two mock company apps, then **independently verifies** the result.

```
User task -> Planner (LLM) -> [ Act -> Observe -> Adapt ]* -> Verifier (separate LLM agent, read-only) -> Result + evidence
                                  |  browser / files / memory / ask_human
                                  +-- Policy guard (human approval for large amounts)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env                                   # Windows: copy .env.example .env
# edit .env: set OPENAI_API_KEY  (or GEMINI_API_KEY)
python scripts/smoke_test.py                           # optional: checks the mock environment (no key needed)
python run.py                                          # starts portal :8001, finance :8002, dashboard :8000
```
Open **http://127.0.0.1:8000**, pick an example task, press **Run task**. Set `HEADLESS=0` in `.env` to watch the browser.

## Demo scenarios (each exercises a different capability)
| Task | What happens |
|---|---|
| `Process the latest invoice from AWS.` | Logs in, picks AWS-1023 by *invoice date* (list is unsorted), reads the PDF, fills the form, hits a **503** (retry) and possibly a **422** (amount formatting), recovers, then the verifier re-checks the saved record. |
| `Process the latest invoice from Google Cloud.` | GCP-3012 already exists -> **409 duplicate**. Agent must not duplicate; it inspects the existing record, compares to the PDF and reports. |
| `Process the latest invoice from Microsoft.` | MS-2093 is INR 85,00,000 -> the runtime **pauses for human approval** (Approve/Reject in the UI). Reject => agent stops as *blocked*. |
| `Process the latest invoice.` | No vendor named -> agent **asks you** for clarification. |

Use **Reset environment** between runs (resets the finance DB). Every run is saved in `runs/<id>/` (`log.json`, screenshots, downloaded PDFs) as an audit trail.

## Architecture
- `portal/` - mock Vendor Invoice Portal (FastAPI): login, searchable list, 12 generated PDF invoices (unsorted).
- `finance/` - mock Finance System (FastAPI + SQLite) with deliberate failures: 422 validation, 409 duplicate, 503 flaky submit.
- `agent/runner.py` - the loop. LLM plans, then each turn emits `{thought, tool, args}`; the runtime executes it, feeds back the observation + working memory, and the LLM adapts. `finish` triggers verification.
- `agent/tools.py` - **generic** tools only: `browser_goto/read_page/click/fill`, `download_file`, `read_pdf`, `remember`, `ask_human`, `update_plan`, `finish`. No `submit_invoice()` anywhere.
- `agent/company_context.md` - company knowledge (systems, credentials, procedures, policy) kept as data, not code.
- `agent/llm.py` - provider-agnostic JSON chat (OpenAI or Gemini).
- `dashboard/` - live activity timeline, plan, memory, screenshots, approval box, final evidence.

## Key design decisions
1. **Generic tools + company context as data** -> to support a new workflow you edit `company_context.md`, not the loop (the Generalization criterion).
2. **Independent verifier**: a second LLM agent with a fresh browser page and a read-only toolbox (POST forms blocked) re-reads the destination system and compares each field with source data. "Button clicked" is never treated as success; if the verifier rejects, the worker is sent back to fix it.
3. **Policy enforced in the runtime, not the prompt**: before any form submit, the runtime inspects the form's amount/total fields; above `APPROVAL_THRESHOLD` it blocks and asks a human. The LLM cannot bypass it.
4. **Recovery by observation**: tool errors *and* page-level HTTP errors (4xx/5xx) are surfaced as events and fed back; the LLM decides retry vs. alternative. A hard cap on consecutive failures and total steps prevents infinite loops.
5. **JSON-action protocol instead of native function-calling** so the same loop works identically on OpenAI and Gemini.
6. **Old observations are truncated** in the context window; durable facts live in explicit working memory.

## Models / services / components
OpenAI (default `gpt-4o-mini`) **or** Gemini (default `gemini-2.5-flash`) via `openai` / `google-genai` SDKs; Playwright (Chromium); FastAPI + Uvicorn; SQLite; reportlab (generate PDFs); pypdf (read PDFs). No real credentials or third-party systems are used; everything is a local mock.

## Assumptions
- "Latest" = most recent *invoice date*. The PDF is the source of truth. Currency is INR, GST-inclusive total.
- Credentials for the mock portal are provided to the agent via company context (stand-in for a secrets vault).
- Approval threshold is INR 10,00,000 (configurable).

## Known limitations
- Text/DOM-based browsing (no vision); canvas-heavy or heavily dynamic sites would need screenshot-based computer use.
- Text-extractable PDFs only (no OCR for scans).
- One task at a time; in-memory state; no auth on the dashboard.
- Verifier is itself an LLM, so it is an independent check, not a formal guarantee. Small models can be less reliable at long tasks - use `gpt-4o` / `gemini-2.5-pro` if a run stalls.
- Only a limited number of failure modes are injected; real-world UIs will surface more.

## What I'd build next
Persistent company memory + learning from past runs and human feedback; vision-based fallback when selectors fail; task queue/scheduler with background execution; secrets vault and per-action permission scopes; a programmatic eval suite (task x failure-mode matrix with success metrics); OCR for scanned invoices; connectors (email/ERP APIs) so the agent prefers APIs over UI when available.
