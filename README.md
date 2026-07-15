# InboxPilot

InboxPilot is an AI customer-support tool: a user connects their support Gmail
inbox via Composio and uploads their docs (FAQs, policies, product docs).
Email processing only starts once the workspace's card-required, 7-day free
trial begins ($49/mo, 500 emails/month) — until then, incoming email lands
unprocessed rather than consuming AI spend. Once trialing or subscribed,
every incoming support email is classified, matched against their knowledge
base, and gets an AI-drafted reply waiting in a review queue. By default a
human approves each draft with one click; if Autopilot is on, replies above a
confidence threshold are sent automatically and everything else falls back
to the review queue.

## Monorepo layout

```
/web   Next.js (App Router) + Tailwind — frontend, deployed to Vercel
/api   FastAPI (Python) — backend, deployed to Fly.io
```

`/web` holds the UI, NextAuth login, and thin proxy routes with no business
logic. `/api` holds everything else: Composio webhooks, the
classify/retrieve/draft pipeline, KB parsing + embeddings, Stripe webhooks,
sending, and the fallback sync job. All MongoDB writes happen there.

## Running locally

### API (FastAPI)

```bash
cd api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload --port 8080
```

Run tests:

```bash
cd api
source .venv/bin/activate
python -m pytest -q
```

### Web (Next.js)

```bash
cd web
npm install
cp .env.example .env.local   # fill in real values
npm run dev
```

## Environment variables

### FastAPI (Fly secrets)

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | MongoDB Atlas connection string |
| `INTERNAL_API_KEY` | Shared secret with the Next.js proxy |
| `COMPOSIO_API_KEY` | Composio API key |
| `COMPOSIO_AUTH_CONFIG_ID` | *Optional.* Gmail auth config id, only needed when bringing your own Google OAuth app — unset means Composio-managed auth (Composio creates/reuses its own managed Gmail auth config) |
| `COMPOSIO_WEBHOOK_SECRET` | *Optional.* Composio webhook signature secret — auto-fetched at startup when `BACKEND_PUBLIC_URL` is set (via `client.triggers.set_webhook_subscription`), or copy it from the Composio dashboard |
| `BACKEND_PUBLIC_URL` | Public base URL of this API (e.g. `https://inboxpilot-api.fly.dev`) — enables automatic webhook subscription registration at startup |
| `ANTHROPIC_API_KEY` | Anthropic API key (drafting + classification) |
| `OPENAI_API_KEY` | OpenAI API key (embeddings only) |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature secret |
| `STRIPE_PRICE_ID` | Stripe price id for the subscription plan |
| `FRONTEND_URL` | Frontend origin, used for Stripe/Composio redirect URLs |

### Next.js (Vercel env)

| Variable | Purpose |
| --- | --- |
| `NEXTAUTH_URL` | Canonical app URL for NextAuth |
| `NEXTAUTH_SECRET` | NextAuth session secret |
| `RESEND_API_KEY` | Resend API key (magic link delivery) |
| `EMAIL_FROM` | From address for magic link emails |
| `BACKEND_URL` | FastAPI base URL, e.g. `https://inboxpilot-api.fly.dev` |
| `INTERNAL_API_KEY` | Same value as the backend's `INTERNAL_API_KEY` |
| `MONGODB_URI` | Same MongoDB Atlas connection string (NextAuth adapter only) |

## Going live

Everything needed to take a fresh environment (dev cluster/app, staging, or
prod) from "code deployed" to "actually processing real email." Work through
this top to bottom for a new environment; re-check it after any credential
rotation.

### 1. MongoDB Atlas vector search index

`kb.py`'s `$vectorSearch` retrieval requires the `kb_chunks_vector` Atlas
Search index to exist before any KB upload can be retrieved — it isn't
created by `ensure_indexes` (mongomock doesn't support it, which is also why
tests monkeypatch around it). Create it once per environment by following
[`api/scripts/create_vector_index.md`](api/scripts/create_vector_index.md).

### 2. Fly.io backend secrets

Deploy `/api` to Fly, then set every backend env var in one shot:

```bash
cd api
fly secrets set \
  MONGODB_URI="mongodb+srv://..." \
  INTERNAL_API_KEY="$(openssl rand -hex 32)" \
  COMPOSIO_API_KEY="..." \
  COMPOSIO_AUTH_CONFIG_ID="..." \
  COMPOSIO_WEBHOOK_SECRET="..." \
  BACKEND_PUBLIC_URL="https://inboxpilot-api.fly.dev" \
  ANTHROPIC_API_KEY="..." \
  OPENAI_API_KEY="..." \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  STRIPE_PRICE_ID="price_..." \
  FRONTEND_URL="https://app.inboxpilot.example"
```

`COMPOSIO_AUTH_CONFIG_ID` and `COMPOSIO_WEBHOOK_SECRET` can both be omitted:
with `BACKEND_PUBLIC_URL` set, the API registers its own webhook subscription
and fetches the signing secret automatically at startup, and Gmail auth
defaults to Composio-managed auth (no auth config id required) unless you're
bringing your own Google OAuth app.

`INTERNAL_API_KEY` must match the value set on Vercel below — it's the
shared secret between the Next.js proxy and FastAPI, not a third-party
credential.

### 3. Vercel frontend env

In the Vercel project settings, set (Production **and** Preview, if previews
should hit a real backend):

- `NEXTAUTH_URL`
- `NEXTAUTH_SECRET`
- `RESEND_API_KEY`
- `EMAIL_FROM`
- `BACKEND_URL`
- `INTERNAL_API_KEY` (same value as the Fly secret above)
- `MONGODB_URI` (same Atlas connection string)

### 4. Composio: Gmail trigger + webhook URL

Webhook registration and per-connection trigger enablement are now automatic;
this step is mostly verification.

1. If using Composio-managed auth (the default, `COMPOSIO_AUTH_CONFIG_ID`
   unset), nothing to configure here — Composio creates/reuses its own
   managed Gmail auth config on first connect. If bringing your own Google
   OAuth app, confirm the auth config used by `COMPOSIO_AUTH_CONFIG_ID` is
   live (not sandbox) and has the Gmail scopes the app requests (read +
   send).
2. With `BACKEND_PUBLIC_URL` set, the API registers its webhook subscription
   (`https://<fly-app>.fly.dev/webhooks/composio`) and fetches the signing
   secret automatically at startup (`app/main.py` lifespan →
   `composio_client.ensure_webhook_subscription`) — verify by checking the
   startup logs for an error, or set `COMPOSIO_WEBHOOK_SECRET` manually from
   the Composio dashboard if you'd rather not grant the API that permission.
3. The "new Gmail message" trigger (`GMAIL_NEW_GMAIL_MESSAGE`) is enabled
   per connected account automatically the moment a connection's status
   flips to `active` (`composio_connect.py` → `ensure_gmail_trigger`) — no
   manual dashboard step required.
4. Signature verification uses the real Composio/standard-webhooks scheme
   (`client.triggers.verify_webhook`: HMAC-SHA256 over
   `f"{id}.{timestamp}.{body}"`, `webhook-id`/`webhook-timestamp`/
   `webhook-signature` headers) — if `COMPOSIO_WEBHOOK_SECRET` is wrong or
   missing and auto-registration didn't run, every webhook 401s; check
   startup logs first.

### 5. Stripe: product/price + webhook endpoint

1. Create the subscription product and its price in the Stripe dashboard
   (live mode); copy the price id into `STRIPE_PRICE_ID`.
2. Add a webhook endpoint pointing at
   `https://<fly-app>.fly.dev/webhooks/stripe` subscribed to at least:
   `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed` (the events
   `app/routers/webhooks_stripe.py` handles — anything else is accepted and
   ignored, so it's fine to subscribe to more).
3. Copy that endpoint's signing secret into `STRIPE_WEBHOOK_SECRET`, and the
   live secret key into `STRIPE_SECRET_KEY`.

### 6. Resend domain setup

1. Add and verify the sending domain in the Resend dashboard (SPF/DKIM
   records on the DNS zone) — magic-link emails from an unverified domain
   land in spam or get rejected outright.
2. Set `EMAIL_FROM` to an address on that verified domain and
   `RESEND_API_KEY` to a live (not test) key.

### Post-deploy smoke check

- Sign up, connect a Gmail inbox, confirm `/webhooks/composio` receives and
  ingests a real test email (check the `events` collection for
  `email_received`).
- Upload one KB document and confirm it reaches `status: "ready"` (proves
  the Atlas vector index from step 1 exists — uploads silently fail
  retrieval otherwise, they don't error at upload time).
- Run a Stripe test-mode checkout against the live webhook endpoint (or use
  the Stripe CLI's `stripe trigger checkout.session.completed`) and confirm
  the workspace's `subscriptionStatus` flips.
- Confirm both `/webhooks/composio` and `/webhooks/stripe` return 429 after
  120 rapid requests from the same IP (`api/app/ratelimit.py`) — proves the
  rate limiter is active in the deployed process, not just under test.

## Troubleshooting

- **Gmail shows "Connect" again after a working connection breaks** — the
  connect flow self-heals stale Composio connected accounts: if Composio's
  side of a previously-active connection has been deleted (dashboard
  cleanup, expired grant), the next status poll detects `NOT_FOUND` and
  flips the stored connection back to `disconnected` automatically, so the
  user just reconnects rather than getting stuck on a dangling connection
  id. No manual DB cleanup needed.
- **Connected Gmail shows no address for a bit** — Composio's connected-account
  object doesn't carry an email address at all; the actual mailbox address
  is fetched separately via `GMAIL_GET_PROFILE`
  (`composio_client.fetch_mailbox_address`) the first time a connection is
  polled active, and backfilled automatically on the next live poll for any
  connection that went active before this existed. The UI shows a plain
  "Connected" state (rather than blocking on an address) until that fetch
  lands.
- **Local logins/workspaces "disappear" after this change** — the web app's
  Mongo database name used to fall back to whatever `client.db()` resolves
  to when `MONGODB_URI` has no path segment (silently `test` for many Atlas
  SRV strings), while the FastAPI backend has always hard-coded
  `inboxpilot`. The database is now pinned to `inboxpilot` in both
  `web/auth.ts` and `web/lib/mongodb.ts`. If you had local logins created
  before this fix, run `api/scripts/migrate_test_db.py` once (manually,
  it's not wired into any command) to copy `users`/`workspaces`/`sessions`/
  `verification_tokens` from `test` into `inboxpilot` without overwriting
  anything already there.
