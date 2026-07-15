AI Customer Support Tool — MVP Spec
Stack: Next.js (App Router) + Tailwind — frontend · FastAPI (Python) on Fly.io — backend · MongoDB Atlas (incl. Vector Search) · Composio (Gmail, Python SDK) · Anthropic API (Sonnet) · OpenAI embeddings · NextAuth · Stripe Goal: Launchable MVP in 7 days. One Gmail inbox per workspace, draft-first with optional auto-send.

1. Product in one paragraph
A user signs up, connects their support Gmail inbox via Composio, and uploads their docs (FAQs, policies, product docs). From that point, every incoming support email is classified, matched against their knowledge base, and gets an AI-drafted reply waiting in a review queue. By default a human approves each draft with one click. If they flip on Autopilot, replies above a confidence threshold are sent automatically and everything else falls back to the review queue.

2. Core architecture
2.0 Frontend/backend split
Next.js (Vercel): UI, NextAuth login, and thin proxy routes. No business logic.
FastAPI on Fly.io: everything else — Composio webhooks, the classify/retrieve/draft pipeline, KB parsing + embeddings, Stripe webhooks, sending, the fallback sync job. All MongoDB writes happen here.
Auth bridge (recommended: proxy pattern). The browser never calls Fly directly. Next.js route handlers under /api/* validate the NextAuth session server-side, then forward the request to FastAPI with two headers: X-Internal-Key: <shared secret> and X-Workspace-Id: <from session>. FastAPI trusts requests only with a valid internal key. Alternative is JWT verification in Python (NextAuth JWT strategy + verify in FastAPI) — cleaner long-term, but NextAuth's default tokens are encrypted JWE, and decrypting them in Python is fiddly interop work you don't want in week one. The proxy costs one extra hop and buys you zero auth code in Python. Take the proxy.
Webhooks (Composio, Stripe) hit FastAPI directly at https://<app>.fly.dev/... — they authenticate via their own signature verification, not the internal key.
2.1 Login vs. inbox connection (don't conflate these)
App login (NextAuth): email magic links only — NextAuth Email provider with the MongoDB adapter (the adapter stores verification tokens, so it's required anyway). Use Resend for delivery: 5-minute setup, generous free tier, and you'll want it later for product notifications anyway. No Google OAuth at login, which also means no Google app verification review for your login flow at all.
Inbox connection (Composio): the only Google OAuth in the entire product. Initiated from onboarding/settings, connecting the support inbox (e.g. support@company.com). Composio manages tokens and refresh.
One magic-link caveat to design around: users will log in from the email address they sign up with, which is often not the support inbox they connect. That's fine and expected — just don't key anything off "login email == inbox email" anywhere in the code.
2.2 Email ingestion pipeline
Composio Gmail trigger (new message)
  → POST https://<app>.fly.dev/webhooks/composio   (FastAPI)
  → dedupe (gmailMessageId unique index)
  → skip if outbound / sent by us
  → CLASSIFY (Haiku, cheap): support request? | newsletter | notification | spam | auto-reply
  → if support request:
      → embed the question, retrieve top-k chunks from Atlas Vector Search
      → DRAFT (Sonnet, structured JSON): reply, confidence 0–100, category, escalation flags
      → guardrail check (see 2.4)
      → if Autopilot ON and confidence ≥ threshold and no guardrail hit:
          → send via Composio reply-to-thread → mark auto_sent
        else:
          → status = needs_review, appears in queue

Also run a fallback sync job (every 10–15 min, APScheduler running inside the FastAPI process) that pulls recent messages via Composio's Gmail fetch action, in case a webhook is missed. Webhooks for speed, polling for correctness.
Replies must go on the original thread using Composio's reply-to-thread action (proper In-Reply-To/References headers), never as a new email.
2.3 Drafting call (Sonnet)
Model: claude-sonnet-4-6. One call per email with:
System prompt: company name, tone settings, signature, "only answer from provided context, escalate if unsure" rules.
Thread history (all messages in the thread, newest last).
Top 5–8 retrieved KB chunks with source doc names.
Instruction to return JSON only:
{
  "reply": "…",
  "confidence": 87,
  "category": "billing | technical | shipping | account | refund | other",
  "requires_human": false,
  "reasoning": "one sentence",
  "sources_used": ["refund-policy.pdf"]
}

Confidence is self-reported, which is imperfect — that's why guardrails exist as a hard layer on top. Show reasoning and sources_used in the review UI; it builds trust and makes bad drafts easy to catch.
2.4 Auto-send guardrails (hard rules, independent of confidence)
Never auto-send when:
requires_human: true or category is refund (or user-configured blocked categories)
Zero relevant KB chunks retrieved (similarity below floor) — the model is guessing
Detected anger/escalation, legal threats, or mention of chargebacks/lawyers
The thread already contains a prior AI auto-reply and the customer wrote back (loop prevention — second touch always goes to a human)
Sender is in the user's block/VIP list
Default: Autopilot OFF, threshold 85 when enabled, adjustable 50–99 via slider in settings.
2.5 Knowledge base / RAG
Uploads: PDF, DOCX, TXT, MD (plus a plain-text paste box — cheapest way for users to get FAQs in fast).
Parse in FastAPI (pypdf / python-docx; both pure-Python, no system deps in the Docker image), chunk ~600 tokens with ~80 overlap, embed with OpenAI text-embedding-3-small (1536 dims — cheap, plenty for this).
Store chunks + vectors in a kb_chunks collection with an Atlas Vector Search index (cosine). No separate vector DB — one database, one bill, one thing to break. Note: create the vector index in Atlas UI/CLI; works on M0+ (dedicated tier recommended before real scale).
Re-upload = delete old chunks for that doc, re-embed.
2.6 Background work
This is where Fly beats serverless: the FastAPI machine is a persistent process, so there are no execution timeouts to design around.
Per-email pipeline: the webhook handler validates + persists the raw message, returns 200 immediately, and runs classify → retrieve → draft as a FastAPI BackgroundTask (or asyncio.create_task). Webhook stays fast, pipeline can take 15s without anyone caring.
Fallback sync + monthly usage reset: APScheduler in-process. No external cron service.
Consequence: set min_machines_running = 1 in fly.toml. If Fly scales you to zero, webhooks eat a cold start and the scheduler doesn't run. One always-on shared-cpu-1x machine is a few dollars/month — non-negotiable for this architecture.
A real queue (Redis + arq/Celery) only becomes necessary if you later need retries with backoff or multi-machine workers. Not week one.

3. Data model (MongoDB collections)
users — NextAuth-managed (adapter) + workspaceId.
workspaces — name, ownerId, settings: { autopilot: bool, confidenceThreshold: number, tone: string, signature: string, blockedCategories: [] }, stripeCustomerId, plan, subscriptionStatus, trialEndsAt, usage: { emailsProcessedThisMonth }.
connections — workspaceId, provider: 'gmail', composioConnectionId, emailAddress, status, connectedAt.
threads — workspaceId, gmailThreadId, subject, customerEmail, customerName, status: 'needs_review' | 'auto_sent' | 'sent' | 'ignored' | 'archived', category, lastMessageAt, snippet.
messages — threadId, gmailMessageId (unique index), direction: 'inbound' | 'outbound', from, to, bodyText, bodyHtml, sentBy: 'customer' | 'ai_auto' | 'human_approved', receivedAt.
drafts — threadId, messageId (the inbound msg it answers), reply, confidence, category, requiresHuman, reasoning, sourcesUsed, status: 'pending' | 'approved_sent' | 'auto_sent' | 'edited_sent' | 'discarded', editedReply, createdAt, resolvedAt, resolvedBy.
kb_documents — workspaceId, filename, type, sizeBytes, chunkCount, status: 'processing' | 'ready' | 'failed'.
kb_chunks — workspaceId, documentId, text, embedding: [1536], order. Vector index on embedding, filter on workspaceId.
events — lightweight audit log: workspaceId, type (email_received, draft_created, auto_sent, approved, etc.), meta, ts. Powers dashboard stats and debugging.

4. Pages & UI
Design language: Linear-style light mode. Inter, 13–14px base, #FAFAFA app background, white cards, 1px #E5E7EB borders, 6–8px radii, restrained color (one accent, e.g. indigo), status as small tinted pills, generous whitespace, no shadows heavier than shadow-sm. Left sidebar (56px collapsed / 220px expanded): Dashboard, Inbox, Knowledge, Settings.
/ — Landing
One hero, one screenshot, three feature blurbs, pricing card, CTA → signup. Half a day max; it's a launch requirement, not a product.
/login /signup
NextAuth email magic link only. Minimal centered card: email input → "Check your inbox" state → link logs them in. Add a "resend link" button with a 30s cooldown — magic-link-only flows live and die on this screen.
/onboarding (wizard, 3 steps, blocking until Gmail is connected)
Connect Gmail — Composio OAuth button, success state shows connected address.
Upload knowledge — dropzone + paste box, skippable but discouraged ("drafts will be generic without this").
Choose mode — Draft mode (recommended, default) vs Autopilot with threshold slider. Explain the guardrails inline.
/dashboard
Top row, four stat cards (period toggle: today / 7d / 30d):
Needs review (clickable → inbox filtered)
Emails received
Drafts created
Auto-sent (with % of total)
Below: "Needs your attention" list — the 10 oldest pending reviews inline (sender, subject, category pill, confidence, time waiting) with one-click Approve directly from the dashboard. This is the page's real job: get to zero.
A small bar/line chart of email volume per day is nice-to-have; skip if time is tight.
/inbox
Tabs: Needs review (default) · Auto-sent · Sent · All. Table rows: customer, subject + snippet, category pill, confidence badge (green ≥85 / amber 60–84 / red <60), age. Row click → thread view. Keyboard: ↑/↓ navigate, Enter open, A approve — cheap to add, makes it feel like Linear.
/inbox/[threadId] — Thread view (the core screen)
Two-pane:
Left: full email thread, chronological, customer vs. outbound visually distinct.
Right: draft panel — editable textarea with the AI reply, above it a compact meta strip (confidence, category, "Sources: refund-policy.pdf ×2" expandable to show chunks, one-line reasoning). Buttons: Approve & send (primary), Regenerate (optional instruction input: "offer a 10% discount"), Discard / mark handled.
Sending: optimistic UI, Composio reply-to-thread, thread status → sent.
/knowledge
Doc list (name, type, chunks, status, uploaded date, delete), upload dropzone, paste-text modal. Show a processing spinner state — embedding takes a few seconds.
/settings
Sections (single page, anchored sub-nav):
Inbox: connected Gmail, reconnect/disconnect.
Automation: Autopilot toggle, threshold slider, blocked categories (multi-select), loop-prevention note.
AI behavior: tone preset (friendly/professional/concise), signature, custom instructions textarea (injected into system prompt).
Billing: current plan, usage this month, Stripe Customer Portal link.
Account: name, email, delete workspace.

5. API surface
FastAPI (Fly.io) — all business logic
POST   /webhooks/composio          # inbound Gmail events (signature-verified)
POST   /webhooks/stripe            # subscription lifecycle (signature-verified)
GET    /composio/connect           # initiate Gmail OAuth, returns redirect URL
GET    /composio/status            # poll connection status during onboarding
GET    /threads?status=&page=
GET    /threads/{id}
POST   /threads/{id}/approve       # send draft (optionally edited body)
POST   /threads/{id}/regenerate    # optional instruction param
POST   /threads/{id}/discard
POST   /kb/upload                  # multipart → parse → chunk → embed
DELETE /kb/{doc_id}
GET/PATCH /settings
POST   /billing/checkout           # Stripe Checkout session
POST   /billing/portal             # Customer Portal session
GET    /health                     # Fly health check

Every non-webhook route requires X-Internal-Key and X-Workspace-Id headers (see §2.0). Structure: app/routers/ per domain, Pydantic models for request/response, Motor (async PyMongo) for the DB, httpx for outbound calls where an SDK is missing.
Next.js — thin proxy only
One catch-all route handler app/api/backend/[...path]/route.ts: validate NextAuth session → attach internal key + workspaceId → forward to Fly → stream response back. ~40 lines, written once, never touched again. The frontend calls /api/backend/threads, etc.

6. Stripe (keep it stupid simple)
One plan at launch (e.g. $49/mo, 500 emails processed/month) + 7-day free trial, card required at trial start via Checkout. Trial-without-card is better top-of-funnel but worse conversion and invites abuse of your AI costs — with card is the right MVP default since every email costs you real API money.
Webhooks handled: checkout.session.completed, customer.subscription.updated/deleted, invoice.payment_failed.
Usage metering: increment usage.emailsProcessedThisMonth per drafted email; at limit, stop drafting and show an upgrade banner (emails still land in inbox unprocessed, nothing is lost).
Customer Portal for cancel/card updates — zero custom billing UI.

7. What's deliberately cut from the MVP
Multi-inbox, team members/roles, non-Gmail channels (Outlook, chat, Instagram), analytics beyond the four stat cards, CSAT tracking, auto-labeling in Gmail, URL/website scraping into the KB, multi-language tone handling, mobile layouts beyond "doesn't break", cmd+K. All of these are v1.1 candidates; none block launch.
Two cut-but-flag decisions worth a conscious choice:
Where drafts live. This spec keeps drafts in-app only. Alternative: also create real Gmail drafts so users can send from Gmail itself. Slicker for some users, but you lose tracking of what was approved/edited and the review queue becomes optional — weaker product loop. Recommend in-app only.
Training period. Some tools force 7 days of draft-only before Autopilot unlocks. Good safety story, adds friction. MVP compromise: Autopilot defaults off + guardrails, no forced lockout.

8. Seven-day build plan
Day 1 — Skeleton, both sides deployed. Next.js + Tailwind scaffold with design tokens/layout shell (sidebar, page frame), NextAuth magic links via Resend + MongoDB adapter, workspace creation on first login, Vercel deploy. FastAPI scaffold with /health, Motor connection, internal-key auth dependency, the Next.js proxy route — fly launch and get a green health check today. Both apps live on day one means webhook URLs and env plumbing are never a day-6 surprise.
Day 2 — Gmail in. Composio integration (Python SDK): connect flow, webhook endpoint on Fly, message persistence (threads/messages), APScheduler fallback sync, classification step with Haiku. By EOD: real support emails appearing in a raw inbox list.
Day 3 — Knowledge base. Upload → parse → chunk → embed → Atlas Vector Search index, retrieval function, /knowledge page. Test retrieval quality with your own docs.
Day 4 — Drafting + Inbox UI. Sonnet drafting pipeline with structured output, drafts collection, /inbox and thread view with approve/regenerate/discard, sending via Composio. This is the make-or-break day; protect it.
Day 5 — Autopilot + Dashboard. Guardrails, confidence threshold, auto-send path, loop prevention, events logging, /dashboard with stats and attention list, onboarding wizard.
Day 6 — Money + Settings. Stripe Checkout/Portal/webhooks, trial + usage limits, full /settings, tone/signature/custom instructions wired into the prompt, landing page.
Day 7 — Hardening + launch. End-to-end test with a real Gmail account and real docs, edge cases (HTML-only emails, attachments-only emails, non-English, very long threads, webhook replays), error states, empty states, rate limiting on the webhook route, prod secrets on both platforms, ship.

9. Fly.io deployment
Repo layout: monorepo — /web (Next.js, deployed to Vercel) and /api (FastAPI, deployed to Fly). One repo so Claude Code sees both sides.
Dockerfile: python:3.12-slim, install from requirements.txt (or uv for faster builds), run uvicorn app.main:app --host 0.0.0.0 --port 8080. pypdf/python-docx keep the image free of apt dependencies.
fly.toml essentials:
app = "yourapp-api"
primary_region = "fra"            # or ams — close to Cyprus + EU customers

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false      # scheduler must keep running
  min_machines_running = 1

[[http_service.checks]]
  path = "/health"
  interval = "30s"

Secrets: fly secrets set MONGODB_URI=... ANTHROPIC_API_KEY=... — everything in §10's backend column. Secrets restart the machine on set; batch them in one command.
Workflow: fly launch once, then fly deploy per release; fly logs for tailing the pipeline in real time, fly ssh console when you need to poke at the box. This is the CLI loop you're used to.
Sizing: one shared-cpu-1x / 512MB machine handles this workload comfortably — the heavy lifting is all external API calls, not CPU.
Atlas networking: Fly machines have no static IP by default. Either allow 0.0.0.0/0 in Atlas (fine at MVP — auth + TLS still apply) or buy a dedicated IPv4 on Fly and allowlist it. Don't burn an hour on this on day one; open it, note it, tighten later.
10. Env vars checklist
FastAPI (Fly secrets):
MONGODB_URI
INTERNAL_API_KEY                              # shared with Next.js proxy
COMPOSIO_API_KEY / COMPOSIO_WEBHOOK_SECRET
ANTHROPIC_API_KEY
OPENAI_API_KEY                                # embeddings only
STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / STRIPE_PRICE_ID
FRONTEND_URL                                  # for Stripe/Composio redirect URLs

Next.js (Vercel env):
NEXTAUTH_URL / NEXTAUTH_SECRET
RESEND_API_KEY / EMAIL_FROM                   # magic link delivery
BACKEND_URL                                   # https://yourapp-api.fly.dev
INTERNAL_API_KEY                              # same value as backend
MONGODB_URI                                   # NextAuth adapter only


11. Open decisions for you
Pricing point and email cap per plan (spec assumes $49/mo, 500 emails).
Card-required trial vs. free trial (spec recommends card-required — see §6).
In-app drafts only vs. also pushing Gmail drafts (spec recommends in-app — see §7).
Should discarded/ignored emails be visible somewhere, or hidden forever? (Spec: ignored status, visible under All.)

