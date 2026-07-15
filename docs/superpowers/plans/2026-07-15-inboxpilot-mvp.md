# InboxPilot MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build InboxPilot — an AI customer-support tool where a user connects a Gmail inbox via Composio, uploads a knowledge base, and gets AI-drafted replies in a review queue (with optional guardrailed Autopilot auto-send).

**Architecture:** Monorepo: `/web` (Next.js App Router + Tailwind, NextAuth magic-link login, thin proxy to backend — NO business logic) and `/api` (FastAPI + Motor/MongoDB, all business logic: Composio Gmail webhooks + fallback sync, classify→retrieve→draft pipeline, KB parsing/embeddings with Atlas Vector Search, Stripe billing, APScheduler). The browser never calls FastAPI directly: Next.js route handlers validate the NextAuth session and forward with `X-Internal-Key` + `X-Workspace-Id` headers.

**Tech Stack:** Next.js 15 (App Router) · Tailwind CSS · next-auth v5 (beta) + @auth/mongodb-adapter + Resend provider · FastAPI (Python 3.12) · Motor (async Mongo) · Composio Python SDK (Gmail) · Anthropic API (Sonnet drafting, Haiku classification) · OpenAI `text-embedding-3-small` · MongoDB Atlas Vector Search · Stripe Checkout/Portal · APScheduler · pypdf / python-docx.

## Global Constraints

- Product name everywhere (UI copy, package names, titles): **InboxPilot**.
- Pricing: one plan, **$49/mo, 500 emails processed/month, 7-day free trial, card required** (Stripe Checkout).
- Drafts live **in-app only** (no Gmail drafts). Ignored emails get status `ignored` and are visible under the inbox "All" tab.
- Autopilot defaults **OFF**; confidence threshold default **85**, adjustable **50–99**.
- Drafting model: `claude-sonnet-4-6`. Classification model: `claude-haiku-4-5`. Embeddings: `text-embedding-3-small` (1536 dims). All three read from env with these defaults.
- Design language (all `/web` app pages): Linear-style light mode. Inter font, 13–14px base, `#FAFAFA` app background, white cards, 1px `#E5E7EB` borders, 6–8px radii, single indigo accent, status as small tinted pills, no shadow heavier than `shadow-sm`. Left sidebar 220px expanded / 56px collapsed with: Dashboard, Inbox, Knowledge, Settings.
- Confidence badge colors: green ≥85, amber 60–84, red <60.
- Every non-webhook FastAPI route requires `X-Internal-Key` (must equal env `INTERNAL_API_KEY`) and `X-Workspace-Id` headers. Webhooks authenticate via their own signature verification instead.
- FastAPI code layout: `api/app/routers/` per domain, Pydantic models for request/response, Motor for DB, httpx where an SDK is missing.
- All MongoDB writes happen in FastAPI — except NextAuth adapter collections (`users`, `accounts`, `sessions`, `verificationTokens`) and the `workspaces` insert on first login, which the Next.js side owns.
- Backend tests: `pytest` + `pytest-asyncio`, external services (Anthropic, OpenAI, Composio, Stripe, Atlas Vector Search) always mocked; DB via `mongomock-motor`. Frontend verification: `npm run build` must pass.
- Python deps pinned in `api/requirements.txt`; keep image apt-free (pypdf/python-docx only, no system deps).
- Never log or commit secrets. Both apps ship a complete `.env.example`.
- Commit after every task (conventional commits: `feat:`, `chore:`, `test:` …).

---

### Task 1: Monorepo skeleton — FastAPI core + Next.js scaffold with app shell

**Files:**
- Create: `.gitignore`, `README.md`
- Create: `api/requirements.txt`, `api/Dockerfile`, `api/fly.toml`, `api/.env.example`
- Create: `api/app/__init__.py`, `api/app/main.py`, `api/app/config.py`, `api/app/db.py`, `api/app/deps.py`
- Create: `api/app/routers/__init__.py`, `api/app/routers/health.py`
- Create: `api/tests/__init__.py`, `api/tests/conftest.py`, `api/tests/test_health.py`, `api/tests/test_deps.py`
- Create: `web/` — Next.js scaffold (package.json, `app/`, Tailwind config), `web/.env.example`
- Create: `web/app/(app)/layout.tsx` (sidebar shell), `web/components/Sidebar.tsx`, `web/lib/design.md` is NOT needed — tokens go in `web/app/globals.css`

**Interfaces:**
- Produces (backend): `app.config.Settings` (pydantic-settings) with fields `mongodb_uri`, `internal_api_key`, `composio_api_key`, `composio_webhook_secret`, `anthropic_api_key`, `openai_api_key`, `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_id`, `frontend_url`, `draft_model="claude-sonnet-4-6"`, `classify_model="claude-haiku-4-5"`, `embed_model="text-embedding-3-small"`; accessor `get_settings()` (lru_cache).
- Produces (backend): `app.db.get_db()` → Motor database (reads `MONGODB_URI`, db name `inboxpilot`); `app.db.set_db_for_testing(db)` override hook.
- Produces (backend): `app.deps.workspace_id_dep` — FastAPI dependency that (a) reads `X-Internal-Key`, 401 if missing/mismatch vs `get_settings().internal_api_key`; (b) reads `X-Workspace-Id`, 400 if missing; returns the workspace id string. Used by every later non-webhook router.
- Produces (frontend): `(app)` route-group layout with `<Sidebar/>` (links: Dashboard `/dashboard`, Inbox `/inbox`, Knowledge `/knowledge`, Settings `/settings`; collapsible 220px→56px, active state = indigo tint), page frame `max-w-6xl mx-auto px-8 py-6`, Inter via `next/font`, tokens per Global Constraints in `globals.css`.

**Steps:**

- [ ] **Step 1: Scaffold Next.js app**

Run: `npx -y create-next-app@latest web --ts --tailwind --eslint --app --src-dir=false --import-alias "@/*" --use-npm --no-turbopack` (accept defaults non-interactively). Then set `"name": "inboxpilot-web"` in `web/package.json`.

- [ ] **Step 2: Add root `.gitignore` and `README.md`**

`.gitignore`: node_modules, .next, __pycache__, .venv, .env*, !.env.example, .DS_Store, .superpowers/. README: one-paragraph product description (from spec §1), monorepo layout, how to run each side (`npm run dev` in web, `uvicorn app.main:app --reload --port 8080` in api), env var tables copied from spec §10.

- [ ] **Step 3: Write failing backend tests**

`api/tests/conftest.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app import db as db_module
from app.main import app

@pytest.fixture()
def mock_db():
    client = AsyncMongoMockClient()
    database = client["inboxpilot_test"]
    db_module.set_db_for_testing(database)
    yield database
    db_module.set_db_for_testing(None)

@pytest.fixture()
async def client(mock_db, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    from app.config import get_settings
    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

HEADERS = {"X-Internal-Key": "test-internal-key", "X-Workspace-Id": "ws1"}
```

`api/tests/test_health.py`:
```python
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

`api/tests/test_deps.py` — add a tiny protected probe route in `app/main.py` guarded by `workspace_id_dep` at `GET /internal/whoami` returning `{"workspaceId": ws_id}`; test: no headers → 401; wrong key → 401; key but no workspace header → 400; both → 200 with `{"workspaceId": "ws1"}`.

Add `api/pytest.ini` (or `pyproject` section): `asyncio_mode = auto`.

- [ ] **Step 4: Run tests, verify they fail** — `cd api && python -m pytest -q` fails (module missing).

- [ ] **Step 5: Implement `config.py`, `db.py`, `deps.py`, `main.py`, `routers/health.py`**

`requirements.txt` (pin loosely with `>=`): fastapi, uvicorn[standard], motor, pydantic, pydantic-settings, httpx, python-multipart, apscheduler, anthropic, openai, composio (or composio-core — whichever the current Composio Python SDK package is; check `pip index` / PyPI at implementation time), stripe, pypdf, python-docx, pytest, pytest-asyncio, mongomock-motor.

`main.py`: create `FastAPI(title="InboxPilot API")`, include health router, the `/internal/whoami` probe, CORS not needed (server-to-server only).

- [ ] **Step 6: Run tests, verify pass** — `python -m pytest -q` → all pass.

- [ ] **Step 7: Design tokens + app shell in `/web`**

`globals.css`: `#FAFAFA` body bg, base font-size 14px, Inter. Build `Sidebar.tsx` (client component, collapse state in localStorage, lucide-react icons — add dependency) and `(app)/layout.tsx`. Add placeholder pages `dashboard/page.tsx`, `inbox/page.tsx`, `knowledge/page.tsx`, `settings/page.tsx` each rendering the shell + an `<h1>`. Root `/` page can stay default for now (Task 13 replaces it).

- [ ] **Step 8: Verify frontend builds** — `cd web && npm run build` → succeeds.

- [ ] **Step 9: Dockerfile + fly.toml + env examples**

Dockerfile: `python:3.12-slim`, copy requirements, pip install, copy app, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]`. `fly.toml` exactly per spec §9 (app name `inboxpilot-api`, region `fra`, internal_port 8080, force_https, auto_stop_machines false, min_machines_running 1, health check `/health` every 30s). `.env.example` files list every var from Global Constraints/spec §10 with placeholder values.

- [ ] **Step 10: Commit** — `git add -A && git commit -m "feat: monorepo skeleton — FastAPI core with internal-key auth, Next.js app shell"`

---

### Task 2: Auth — NextAuth magic links, workspace bootstrap, login/signup pages

**Files:**
- Create: `web/lib/mongodb.ts` (Mongo client promise for adapter), `web/auth.ts`, `web/app/api/auth/[...nextauth]/route.ts`, `web/middleware.ts`
- Create: `web/app/login/page.tsx`, `web/app/signup/page.tsx` (both render the same `web/components/AuthCard.tsx`)
- Modify: `web/.env.example` (ensure NEXTAUTH_URL/NEXTAUTH_SECRET/RESEND_API_KEY/EMAIL_FROM/MONGODB_URI/BACKEND_URL/INTERNAL_API_KEY all present)

**Interfaces:**
- Produces: `auth()` helper (next-auth v5) returning session whose `session.user` includes `workspaceId` (string). Every later frontend task reads `session.user.workspaceId`.
- Produces: middleware redirecting unauthenticated users to `/login` for `/dashboard`, `/inbox/:path*`, `/knowledge`, `/settings`, `/onboarding`.

**Steps:**

- [ ] **Step 1: Install deps** — `npm i next-auth@beta @auth/mongodb-adapter mongodb resend` in `web/`.

- [ ] **Step 2: Implement `auth.ts`**

next-auth v5 config: `adapter: MongoDBAdapter(clientPromise)`, provider `Resend({ from: process.env.EMAIL_FROM })`, `session: { strategy: "database" }`. In the `events.createUser` callback (or `signIn` fallback if no workspace yet): insert a `workspaces` doc `{ name: "My workspace", ownerId: user.id, settings: { autopilot: false, confidenceThreshold: 85, tone: "friendly", signature: "", blockedCategories: ["refund"], customInstructions: "" }, plan: null, subscriptionStatus: "none", stripeCustomerId: null, trialEndsAt: null, usage: { emailsProcessedThisMonth: 0 }, createdAt: new Date() }` and set `workspaceId` on the user doc. In the `session` callback copy `user.workspaceId` onto `session.user.workspaceId`. Add TS module augmentation in `web/types/next-auth.d.ts`.

- [ ] **Step 3: Login/signup pages**

Minimal centered card per spec §4: email input → submit calls `signIn("resend", { email, redirect: false })` → "Check your inbox" state with **Resend link** button disabled by a 30-second countdown. `/signup` is the same card with different heading copy. After login, redirect target `/dashboard` (middleware will bounce brand-new users to `/onboarding` in Task 10 — for now `/dashboard` is fine).

- [ ] **Step 4: Middleware** — protect the app routes listed in Interfaces; allow `/`, `/login`, `/signup`, `/api/auth`.

- [ ] **Step 5: Verify** — `npm run build` passes. Manual check: `npm run dev` renders `/login` without crashing (no Mongo connection required just to render the form).

- [ ] **Step 6: Commit** — `git commit -m "feat: NextAuth magic-link auth with workspace bootstrap"`

---

### Task 3: Next.js → FastAPI proxy route

**Files:**
- Create: `web/app/api/backend/[...path]/route.ts`
- Create: `web/lib/api.ts` (typed fetch helper for client components: `apiGet`, `apiPost`, `apiPatch`, `apiDelete`, `apiUpload`)

**Interfaces:**
- Consumes: `auth()` from Task 2.
- Produces: any frontend code can call `/api/backend/<fastapi-path>`; the handler validates session, then forwards to `${BACKEND_URL}/<fastapi-path>` adding `X-Internal-Key: ${INTERNAL_API_KEY}` and `X-Workspace-Id: ${session.user.workspaceId}`, streaming the response back with original status + content-type. Supports GET/POST/PATCH/DELETE, passes query strings, JSON bodies and multipart bodies (forward `request.body` with `duplex: "half"`, drop the incoming `host`/`cookie`/`content-length` headers, keep `content-type`).

**Steps:**

- [ ] **Step 1: Implement the catch-all handler** (single `handler` fn exported as GET/POST/PATCH/DELETE). 401 JSON if no session or no workspaceId.
- [ ] **Step 2: Implement `web/lib/api.ts`** — thin wrappers hitting `/api/backend/...`, throwing on `!res.ok` with the response body message.
- [ ] **Step 3: Verify** — `npm run build` passes.
- [ ] **Step 4: Commit** — `git commit -m "feat: session-validating proxy route to FastAPI"`

---

### Task 4: Backend data layer — collections, indexes, settings endpoints

**Files:**
- Create: `api/app/models.py` (Pydantic response/request models), `api/app/collections.py` (index bootstrap + accessors), `api/app/routers/settings.py`, `api/app/events.py`
- Modify: `api/app/main.py` (startup hook creates indexes; include settings router)
- Test: `api/tests/test_settings.py`, `api/tests/test_events.py`

**Interfaces:**
- Produces: `collections.ensure_indexes(db)` — creates: `messages.gmailMessageId` unique; `threads.(workspaceId, status, lastMessageAt)`; `kb_chunks.(workspaceId, documentId)`; `events.(workspaceId, ts)`; `connections.workspaceId`.
- Produces: `events.log_event(db, workspace_id, type, meta=None)` → inserts `{workspaceId, type, meta, ts: utcnow}`.
- Produces: `GET /settings` → `{ name, settings: {autopilot, confidenceThreshold, tone, signature, blockedCategories, customInstructions}, plan, subscriptionStatus, trialEndsAt, usage, connection: {emailAddress, status} | null }` (joins the workspace's gmail connection). `PATCH /settings` accepts partial `{name?, settings?}` (settings merged field-wise; `confidenceThreshold` clamped 50–99) and returns the updated shape.
- Document collection shapes from spec §3 as Pydantic models: `Workspace`, `Connection`, `Thread`, `Message`, `Draft`, `KbDocument`, `KbChunk`, `Event` — these models are the single source of truth for field names used by every later backend task. Workspace ids are stored as strings (they originate from NextAuth ObjectIds — always compare as `str`). Thread status literals: `needs_review | auto_sent | sent | ignored | archived`. Draft status literals: `pending | approved_sent | auto_sent | edited_sent | discarded`. Message `sentBy`: `customer | ai_auto | human_approved`.

**Steps:**

- [ ] **Step 1: Write failing tests** — settings GET returns defaults for unknown workspace (create-on-read with the same default settings object as Task 2's bootstrap, so a workspace created by NextAuth or lazily here look identical); PATCH updates `settings.tone` and clamps `confidenceThreshold: 120` → 99; events helper writes a doc with `ts`.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement models, indexes, events, settings router.** All routers use `workspace_id_dep`.
- [ ] **Step 4: Run tests → pass.** `python -m pytest -q`
- [ ] **Step 5: Commit** — `git commit -m "feat: data layer, indexes, events log, settings endpoints"`

---

### Task 5: Composio Gmail — connect flow, webhook ingestion, fallback sync

**Files:**
- Create: `api/app/composio_client.py`, `api/app/routers/composio_connect.py`, `api/app/routers/webhooks_composio.py`, `api/app/ingest.py`, `api/app/scheduler.py`
- Modify: `api/app/main.py` (include routers; start APScheduler on startup, guarded by env `ENABLE_SCHEDULER=1` default on, off in tests)
- Test: `api/tests/test_ingest.py`, `api/tests/test_webhook_composio.py`

**Interfaces:**
- Consumes: `collections`, `events`, `workspace_id_dep`.
- Produces: `composio_client.py` wraps the Composio Python SDK behind a small interface so tests can monkeypatch it: `initiate_connection(workspace_id) -> {redirectUrl, connectionId}`, `get_connection_status(connection_id) -> {status, emailAddress}`, `fetch_recent_messages(connection_id, since_dt) -> list[RawGmailMessage]`, `reply_to_thread(connection_id, gmail_thread_id, body) -> {gmailMessageId}`. `RawGmailMessage` is a TypedDict: `{gmailMessageId, gmailThreadId, subject, fromEmail, fromName, toEmail, bodyText, bodyHtml, receivedAt, isOutbound}`.
- Produces: `GET /composio/connect` → initiates OAuth, upserts `connections` doc (status `pending`), returns `{redirectUrl}`. `GET /composio/status` → polls SDK, on `ACTIVE` updates connection to `{status: "active", emailAddress}`, returns `{status, emailAddress}`.
- Produces: `ingest.ingest_message(db, workspace_id, raw: RawGmailMessage) -> str | None` — the single entry point used by BOTH webhook and fallback sync. Behavior: dedupe on `gmailMessageId` (return None if seen); skip if `isOutbound` or `fromEmail` equals the workspace's connected address (return None); upsert `threads` doc keyed `(workspaceId, gmailThreadId)` (set subject/customerEmail/customerName/snippet=first 140 chars of bodyText/lastMessageAt); insert `messages` doc (direction `inbound`, sentBy `customer`); `log_event(email_received)`; return inserted message id.
- Produces: `POST /webhooks/composio` — verifies signature header (`webhook-signature` HMAC-SHA256 of raw body with `COMPOSIO_WEBHOOK_SECRET`; wrap in `verify_composio_signature(raw_body, headers) -> bool` so the exact header scheme can be adjusted against Composio docs at implementation time), resolves workspace via `connections.composioConnectionId` from the payload, persists via `ingest_message`, returns `{"ok": true}` immediately, and schedules `pipeline.process_inbound(workspace_id, message_id)` as a FastAPI BackgroundTask — Task 6/8 implement it; for now call a module-level hook `pipeline_hook(workspace_id, message_id)` defaulting to a no-op, so this task is testable standalone.
- Produces: `scheduler.py` — APScheduler `AsyncIOScheduler` with job `fallback_sync` every 10 min: for each active connection, `fetch_recent_messages(connection_id, since=45min ago)` → `ingest_message` each → run `pipeline_hook` for each newly inserted message id. Also registers the monthly usage-reset job (cron day 1 00:00 UTC: set every workspace `usage.emailsProcessedThisMonth = 0`).

**Steps:**

- [ ] **Step 1: Write failing tests for `ingest_message`** — inserts thread+message and logs event; second call with same `gmailMessageId` returns None and inserts nothing; outbound message skipped; message from the connected support address itself skipped; two messages same `gmailThreadId` produce one thread with updated `lastMessageAt`/snippet.
- [ ] **Step 2: Write failing webhook tests** — bad signature → 401; good signature (compute HMAC in test) with unknown connectionId → 200 `{"ok": true, "skipped": true}`; good signature + known connection → 200, message persisted, `pipeline_hook` spy called with the new message id.
- [ ] **Step 3: Run, verify fail.**
- [ ] **Step 4: Implement.** Scheduler must not start when `ENABLE_SCHEDULER=0` (set in test conftest).
- [ ] **Step 5: Run tests → pass.**
- [ ] **Step 6: Commit** — `git commit -m "feat: Composio Gmail connect, webhook ingestion with dedupe, fallback sync"`

---

### Task 6: Classification step (Haiku)

**Files:**
- Create: `api/app/llm.py` (anthropic + openai client accessors, monkeypatch-friendly), `api/app/classify.py`
- Test: `api/tests/test_classify.py`

**Interfaces:**
- Produces: `classify.classify_email(subject: str, body: str) -> Literal["support_request","newsletter","notification","spam","auto_reply"]`. Uses Anthropic messages API, model `get_settings().classify_model`, max_tokens 10, a system prompt asking for exactly one of the five labels, temperature 0. Unknown/garbage output falls back to `support_request` (fail open — better to draft than drop). Truncate body to 4000 chars.
- Produces: `llm.get_anthropic()` / `llm.get_openai()` returning cached SDK clients.

**Steps:**

- [ ] **Step 1: Failing tests** — monkeypatch `llm.get_anthropic` with a stub returning ` newsletter ` (whitespace) → returns `"newsletter"`; stub returning `banana` → `"support_request"`; verify the stub was called with `model == "claude-haiku-4-5"` and the subject+body in the user message.
- [ ] **Step 2: Run, fail. Step 3: Implement. Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat: Haiku email classification"`

---### Task 7: Knowledge base — upload, parse, chunk, embed, retrieve + /knowledge page

**Files:**
- Create: `api/app/kb.py` (parse/chunk/embed/retrieve), `api/app/routers/kb.py`
- Create: `web/app/(app)/knowledge/page.tsx` (replace placeholder), `web/components/UploadDropzone.tsx`, `web/components/PasteTextModal.tsx`
- Test: `api/tests/test_kb.py`
- Create: `api/scripts/create_vector_index.md` (exact Atlas index JSON + CLI command, documented for the human)

**Interfaces:**
- Consumes: `llm.get_openai()`, collections, events.
- Produces: `kb.extract_text(filename, content: bytes) -> str` (pypdf for .pdf, python-docx for .docx, utf-8 decode for .txt/.md; ValueError for anything else). `kb.chunk_text(text, chunk_tokens=600, overlap_tokens=80) -> list[str]` — approximate tokens as `len(text)//4`; sliding window over whitespace-split words (chunk≈2400 chars, overlap≈320 chars); never returns empty strings. `kb.embed_texts(texts: list[str]) -> list[list[float]]` (OpenAI embeddings, model from settings, batched ≤100). `kb.retrieve(db, workspace_id, query: str, k=8, floor=0.45) -> list[{text, score, documentName}]` — Atlas `$vectorSearch` aggregation on `kb_chunks` (index name `kb_chunks_vector`, path `embedding`, filter `workspaceId`, numCandidates 200), drop results with score < floor. Because mongomock can't run `$vectorSearch`, isolate the aggregation call in `kb._vector_search(db, ...)` and monkeypatch it in tests.
- Produces routes: `POST /kb/upload` (multipart `file` OR form field `text` + `title` for the paste box) → creates `kb_documents` doc status `processing`, parses/chunks/embeds inline, inserts `kb_chunks` (fields per spec §3 + `documentName`), updates doc `{status: "ready", chunkCount}` (or `failed` on error), logs event, returns the document. `GET /kb` → list docs. `DELETE /kb/{doc_id}` → delete doc + its chunks.
- Produces UI: `/knowledge` — table (name, type, chunks, status pill with spinner while `processing`, uploaded date, delete button), dropzone (accept .pdf/.docx/.txt/.md, posts multipart via `apiUpload`), "Paste text" button → modal (title + textarea → posts). Poll list every 3s while any doc is `processing`.

**Steps:**

- [ ] **Step 1: Failing tests** — `chunk_text`: short text → 1 chunk; 10k-char text → multiple chunks with overlap (assert consecutive chunks share text); `extract_text` on a .txt roundtrip and unsupported extension raises. Upload route (embed + vector search monkeypatched, embeddings = deterministic fake): creates doc + chunks, status `ready`, chunkCount correct; paste-text path works; delete removes chunks; `retrieve` respects the floor (mock `_vector_search` returning scores 0.9/0.3 → 1 result).
- [ ] **Step 2: Run, fail. Step 3: Implement backend. Step 4: Run, pass.**
- [ ] **Step 5: Build the `/knowledge` page** per Interfaces. `npm run build` passes.
- [ ] **Step 6: Write `api/scripts/create_vector_index.md`** — the exact index definition JSON (cosine, 1536 dims, filter field `workspaceId`) and `atlas` CLI command.
- [ ] **Step 7: Commit** — `git commit -m "feat: knowledge base upload/parse/embed with Atlas vector retrieval and knowledge page"`

---

### Task 8: Drafting pipeline — Sonnet drafts, guardrails, autopilot, usage metering

**Files:**
- Create: `api/app/draft.py`, `api/app/guardrails.py`, `api/app/pipeline.py`
- Modify: `api/app/routers/webhooks_composio.py` + `api/app/scheduler.py` (wire `pipeline_hook = pipeline.process_inbound`)
- Test: `api/tests/test_guardrails.py`, `api/tests/test_pipeline.py`, `api/tests/test_draft.py`

**Interfaces:**
- Consumes: `classify.classify_email`, `kb.retrieve`, `composio_client.reply_to_thread`, `events`, workspace settings.
- Produces: `draft.generate_draft(workspace, thread_messages: list, kb_chunks: list) -> DraftResult` — one Sonnet call. System prompt includes: company/workspace name, tone preset, signature, custom instructions, and hard rules: "Only answer from the provided context. If the context does not contain the answer, say you'll check with the team and set requires_human true." User content: thread history newest-last + numbered KB chunks with `documentName`. Request JSON only (`{"reply","confidence","category","requires_human","reasoning","sources_used"}`); parse with a tolerant extractor (strip code fences, find first `{`...last `}`); on parse failure return `DraftResult(reply=<fallback ack text>, confidence=0, category="other", requires_human=True, reasoning="model output unparseable", sources_used=[])`. `DraftResult` is a pydantic model with exactly those fields (confidence int 0–100 clamped).
- Produces: `guardrails.check(draft: DraftResult, *, settings: dict, chunks_found: bool, inbound_text: str, prior_ai_reply_in_thread: bool, sender: str, blocked_senders: list[str]) -> list[str]` — pure function returning the list of violated rule names (empty = safe): `requires_human`, `blocked_category` (category in settings.blockedCategories — includes `refund` by default), `no_kb_context` (not chunks_found), `escalation_language` (case-insensitive regex on inbound_text for: lawyer, legal, sue, lawsuit, chargeback, attorney, "report you", scam, fraud, furious, unacceptable), `loop_prevention` (prior_ai_reply_in_thread), `blocked_sender`.
- Produces: `pipeline.process_inbound(workspace_id, message_id)` (async; opens its own db handle via `get_db()`):
  1. Load workspace, message, thread. If `usage.emailsProcessedThisMonth >= 500` and plan is active (or trialing): log event `usage_limit_hit`, set thread status `needs_review`, stop before classification (email lands unprocessed, nothing lost).
  2. `classify_email` → if not `support_request`: thread status `ignored`, log event, stop.
  3. `kb.retrieve(question = subject + "\n" + bodyText)`.
  4. `generate_draft` → insert `drafts` doc (status `pending`, all DraftResult fields + `sourcesUsed`), increment `usage.emailsProcessedThisMonth`, log `draft_created`.
  5. Guardrails + autopilot: if `settings.autopilot` and `confidence >= settings.confidenceThreshold` and `guardrails.check(...) == []`: `reply_to_thread(...)`, insert outbound `messages` doc (sentBy `ai_auto`), draft status `auto_sent`, thread status `auto_sent`, log `auto_sent`. Else: thread status `needs_review`.
  6. Whole function wrapped in try/except that logs event `pipeline_error` with the exception string and sets thread `needs_review` — a pipeline bug must never lose an email silently.

**Steps:**

- [ ] **Step 1: Failing guardrail tests** — one test per rule firing, one where nothing fires; refund category blocked by default settings; loop prevention fires when `prior_ai_reply_in_thread=True`.
- [ ] **Step 2: Failing draft tests** — stub anthropic returning valid JSON in a code fence → parsed DraftResult; stub returning prose → fallback DraftResult with `requires_human=True`, confidence 0; system prompt contains tone + signature + custom instructions.
- [ ] **Step 3: Failing pipeline tests** (classify/retrieve/draft/reply all monkeypatched): (a) newsletter → thread `ignored`, no draft; (b) support + autopilot off → draft pending, thread `needs_review`, usage incremented; (c) autopilot on, confidence 90 ≥ threshold 85, no guardrail → `reply_to_thread` called, statuses `auto_sent`; (d) autopilot on but guardrail (refund category) → `needs_review`, no send; (e) usage at 500 → no classify call, thread `needs_review`, event `usage_limit_hit`; (f) draft raises → thread `needs_review`, event `pipeline_error`.
- [ ] **Step 4: Run, fail. Step 5: Implement. Step 6: Run, pass.**
- [ ] **Step 7: Commit** — `git commit -m "feat: Sonnet drafting pipeline with guardrails, autopilot and usage metering"`

---

### Task 9: Threads API + Inbox UI (list + thread view with approve/regenerate/discard)

**Files:**
- Create: `api/app/routers/threads.py`
- Create: `web/app/(app)/inbox/page.tsx` (replace placeholder), `web/app/(app)/inbox/[threadId]/page.tsx`, `web/components/ConfidenceBadge.tsx`, `web/components/CategoryPill.tsx`, `web/components/ThreadMessages.tsx`, `web/components/DraftPanel.tsx`
- Test: `api/tests/test_threads.py`

**Interfaces:**
- Consumes: `composio_client.reply_to_thread`, `draft.generate_draft`, `kb.retrieve`, events.
- Produces routes (all workspace-scoped):
  - `GET /threads?status=&page=` — status filter maps tabs: `needs_review` | `auto_sent` | `sent` | omitted=all; page size 25, sorted `lastMessageAt` desc; each row includes the latest draft's `{confidence, category}` when present; returns `{items, total, page}`.
  - `GET /threads/{id}` — thread + all messages (chronological) + latest draft (full fields incl. reasoning, sourcesUsed, editedReply).
  - `POST /threads/{id}/approve` body `{body?: string}` — uses edited body if provided else draft reply; `reply_to_thread`; insert outbound message (sentBy `human_approved`); draft status `edited_sent` if body provided else `approved_sent`, set `resolvedAt`; thread status `sent`; log `approved`. 409 if no pending draft.
  - `POST /threads/{id}/regenerate` body `{instruction?: string}` — re-run retrieve + generate_draft with the instruction appended to the system prompt ("Additional instruction for this reply: …"); replace the pending draft doc (or create one); returns the new draft. Does NOT increment usage (already counted).
  - `POST /threads/{id}/discard` — draft status `discarded`, thread status `ignored`, log event.
- Produces UI:
  - `/inbox`: tabs Needs review (default) / Auto-sent / Sent / All mapped to the status param; table rows: customer, subject + snippet (truncated), CategoryPill, ConfidenceBadge (green ≥85 / amber 60–84 / red <60), relative age. Row click → `/inbox/[threadId]`. Keyboard: ↑/↓ move selection, Enter opens, `A` approves selected row (needs_review tab only). Empty states per tab ("Inbox zero 🎉" for needs review).
  - `/inbox/[threadId]`: two-pane. Left: `ThreadMessages` — chronological bubbles, customer left/white, outbound right/indigo-tinted, sender + timestamp. Right: `DraftPanel` — meta strip (ConfidenceBadge, CategoryPill, "Sources: refund-policy.pdf ×2" expandable to chunk texts, one-line reasoning), editable textarea seeded with the draft reply, buttons: **Approve & send** (primary, optimistic → back to inbox), **Regenerate** (small input for optional instruction), **Discard**. If thread has no pending draft show read-only state.

**Steps:**

- [ ] **Step 1: Failing route tests** — seed threads/messages/drafts in mock db: list filters by status + returns draft summary; detail returns messages in order; approve with edited body → composio spy called with edited text, draft `edited_sent`, thread `sent`; approve without draft → 409; regenerate replaces draft (generate_draft stubbed); discard sets statuses.
- [ ] **Step 2: Run, fail. Step 3: Implement router. Step 4: Run, pass.**
- [ ] **Step 5: Build inbox list + thread view UI.** `npm run build` passes.
- [ ] **Step 6: Commit** — `git commit -m "feat: threads API and inbox UI with approve/regenerate/discard"`

---

### Task 10: Dashboard + onboarding wizard

**Files:**
- Create: `api/app/routers/dashboard.py` (`GET /dashboard/stats?period=today|7d|30d`)
- Create: `web/app/(app)/dashboard/page.tsx` (replace placeholder), `web/components/StatCard.tsx`, `web/components/AttentionList.tsx`
- Create: `web/app/onboarding/page.tsx`, `web/components/onboarding/*` (3 steps)
- Modify: `web/middleware.ts` or `(app)/layout.tsx` — after login, if workspace has no active gmail connection, redirect to `/onboarding` (add `GET /composio/status` passthrough check server-side in the layout)
- Test: `api/tests/test_dashboard.py`

**Interfaces:**
- Consumes: events collection (stats), threads/drafts, `/composio/connect|status`, `/kb/upload`, `PATCH /settings`.
- Produces: `GET /dashboard/stats?period=` → computed from `events` within the period window: `{needsReview: <live count of threads status=needs_review — not period-scoped>, emailsReceived, draftsCreated, autoSent, autoSentPct}` plus `attention: [10 oldest needs_review threads: {id, customerEmail, subject, category, confidence, waitingSinceIso}]`.
- Produces UI: dashboard — four StatCards with period toggle (today/7d/30d); Needs review card links to `/inbox`; AttentionList rows with inline one-click **Approve** (calls `/threads/{id}/approve`, removes row optimistically). Skip the volume chart (spec: nice-to-have).
- Produces UI: `/onboarding` — 3-step wizard, stepper header, blocking until Gmail connected: (1) Connect Gmail — button → `GET /composio/connect` → open `redirectUrl` in new tab → poll `/composio/status` every 2s until `active`, show connected address + Continue; (2) Upload knowledge — reuse UploadDropzone + paste modal, skippable with the exact hint "Drafts will be generic without this."; (3) Choose mode — two radio cards: **Draft mode (recommended)** default vs **Autopilot** with threshold slider (50–99, default 85) and inline guardrail explainer; Finish → PATCH settings → `/dashboard`.

**Steps:**

- [ ] **Step 1: Failing stats tests** — seed events across timestamps; period windows filter correctly; autoSentPct = autoSent/emailsReceived rounded (0 when none); attention list capped at 10 oldest.
- [ ] **Step 2: Run, fail. Step 3: Implement. Step 4: Run, pass.**
- [ ] **Step 5: Build dashboard + onboarding UI.** `npm run build` passes.
- [ ] **Step 6: Commit** — `git commit -m "feat: dashboard stats/attention list and onboarding wizard"`

---

### Task 11: Stripe — checkout, portal, webhooks, trial + limits

**Files:**
- Create: `api/app/routers/billing.py`, `api/app/routers/webhooks_stripe.py`
- Modify: `api/app/main.py` (include routers)
- Test: `api/tests/test_billing.py`, `api/tests/test_webhook_stripe.py`

**Interfaces:**
- Produces: `POST /billing/checkout` → creates (or reuses) Stripe customer, stores `stripeCustomerId`, creates Checkout Session (mode subscription, price `STRIPE_PRICE_ID`, `subscription_data.trial_period_days=7`, `payment_method_collection: "always"`, success/cancel URLs `${FRONTEND_URL}/settings?billing=success|cancelled`) → `{url}`. `POST /billing/portal` → Customer Portal session → `{url}` (409 if no `stripeCustomerId`).
- Produces: `POST /webhooks/stripe` — verify via `stripe.Webhook.construct_event` with `STRIPE_WEBHOOK_SECRET`. Handles: `checkout.session.completed` → set `{plan: "pro", subscriptionStatus: "trialing"|"active" (from session), trialEndsAt}`; `customer.subscription.updated` → sync `subscriptionStatus`; `customer.subscription.deleted` → `{plan: null, subscriptionStatus: "canceled"}`; `invoice.payment_failed` → `subscriptionStatus: "past_due"`. Workspace resolved by `stripeCustomerId`. Unknown event types → 200 ignored.
- Pipeline gating recap (already built in Task 8): the 500/month cap applies to active/trialing workspaces; additionally, if `subscriptionStatus` in `("none","canceled","past_due")` AND the workspace has ever had a plan, skip drafting the same way. Workspaces with `subscriptionStatus: "none"` that never checked out still work — everyone starts with a trial via Checkout, and the UI (Task 12) pushes to subscribe. Add this one gating condition to `pipeline.process_inbound` in THIS task, with a pipeline test.

**Steps:**

- [ ] **Step 1: Failing tests** — checkout: stripe SDK monkeypatched, returns url, customer created once and reused on second call; portal without customer → 409; webhook with bad signature → 400; each handled event mutates the workspace as specified (build events with `stripe.Webhook.construct_event` monkeypatched to return a dict fixture); pipeline skips drafting for `past_due` workspace with a prior plan.
- [ ] **Step 2: Run, fail. Step 3: Implement. Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat: Stripe checkout, portal and subscription webhooks"`

---

### Task 12: Settings page (full)

**Files:**
- Create: `web/app/(app)/settings/page.tsx` (replace placeholder), `web/components/settings/*` (one component per section)
- Modify: none on backend (uses Task 4 `GET/PATCH /settings`, Task 5 `/composio/connect|status`, Task 11 `/billing/*`)

**Interfaces:**
- Produces UI — single page, anchored sub-nav (Inbox · Automation · AI behavior · Billing · Account):
  - **Inbox:** connected Gmail address + status pill; Reconnect button (re-runs connect flow); Disconnect (PATCH connection status via a small new backend route `DELETE /composio/connection` — add it to `composio_connect.py` router: sets connection status `disconnected`, logs event; include a one-assertion test).
  - **Automation:** Autopilot toggle, threshold slider 50–99 with live value, blocked categories multi-select (billing/technical/shipping/account/refund/other), static loop-prevention note: "When a customer replies to an automated response, the next reply always goes to a human."
  - **AI behavior:** tone preset select (friendly/professional/concise), signature textarea, custom instructions textarea. Save button per section → PATCH /settings, saved toast.
  - **Billing:** current plan + status pill, usage this month "N / 500 emails", **Subscribe** (POST /billing/checkout → redirect) when no active plan, **Manage billing** (POST /billing/portal → redirect) otherwise.
  - **Account:** name (editable → PATCH), login email (read-only), Delete workspace button — MVP: `mailto:` support contact tooltip, no destructive endpoint.
- Autopilot banner: while usage ≥ 500, show upgrade banner at top of Inbox and Dashboard ("You've hit this month's 500-email limit — new emails are landing unprocessed."). Add a tiny `GET /settings`-driven shared hook `useWorkspace()` in `web/lib/useWorkspace.ts` (SWR-style fetch on mount) used by banner + settings.

**Steps:**

- [ ] **Step 1: Backend — add `DELETE /composio/connection` + test; run pytest → pass.**
- [ ] **Step 2: Build the settings page sections.** `npm run build` passes.
- [ ] **Step 3: Commit** — `git commit -m "feat: full settings page with billing and inbox management"`

---

### Task 13: Landing page

**Files:**
- Create: `web/app/page.tsx` (replace default), `web/components/landing/*`

**Interfaces:**
- Produces: `/` — same design tokens, marketing-clean: nav (logo wordmark "InboxPilot", Login link, "Start free trial" CTA → `/signup`); hero: headline "Answer support emails before you open your inbox", subline (one sentence: AI drafts every reply from your own docs; you approve with one click), CTA; one product "screenshot" (a styled static mock of the inbox review queue built with divs — no image asset); three feature blurbs (Connect Gmail in one click · Answers grounded in your docs · Autopilot with guardrails); pricing card ($49/mo · 500 emails/month · 7-day free trial · card required · feature checklist); footer. Fully responsive-enough (doesn't break on mobile).

**Steps:**

- [ ] **Step 1: Build it.** `npm run build` passes.
- [ ] **Step 2: Commit** — `git commit -m "feat: landing page"`

---

### Task 14: Hardening — webhook rate limiting, edge cases, error/empty states

**Files:**
- Create: `api/app/ratelimit.py` (simple in-memory sliding-window limiter: 120 req/min per IP on webhook routes → 429), `api/tests/test_ratelimit.py`
- Modify: `api/app/ingest.py` + `api/app/pipeline.py` — edge cases with tests: HTML-only email (derive bodyText via tag-strip regex fallback), empty body/attachments-only (bodyText `""` → still ingested; pipeline drafts against subject only), very long thread (cap thread history passed to Sonnet at last 20 messages), webhook replay (dedupe already covers it — add an explicit test), non-ASCII/non-English body roundtrip test.
- Modify: `web/` — error boundary `web/app/(app)/error.tsx`, loading states (`loading.tsx` for inbox/dashboard/knowledge), toast on failed mutations in DraftPanel/settings (simple inline component, no library).
- Modify: `README.md` — final "Going live" checklist: Atlas vector index creation (link the doc from Task 7), Fly secrets `fly secrets set` one-liner with all backend vars, Vercel env list, Composio trigger + webhook URL setup, Stripe product/price + webhook endpoint setup, Resend domain setup.

**Steps:**

- [ ] **Step 1: Failing tests for limiter + each edge case. Step 2: Run, fail. Step 3: Implement. Step 4: Full backend suite passes: `python -m pytest -q`.**
- [ ] **Step 5: Frontend error/loading states; `npm run build` passes.**
- [ ] **Step 6: Update README going-live checklist.**
- [ ] **Step 7: Commit** — `git commit -m "feat: hardening — rate limiting, email edge cases, error states, launch checklist"`
