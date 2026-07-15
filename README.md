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
| `COMPOSIO_AUTH_CONFIG_ID` | Gmail auth config id from Composio dashboard |
| `COMPOSIO_WEBHOOK_SECRET` | Composio webhook signature secret |
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
  ANTHROPIC_API_KEY="..." \
  OPENAI_API_KEY="..." \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  STRIPE_PRICE_ID="price_..." \
  FRONTEND_URL="https://app.inboxpilot.example"
```

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

1. In the Composio dashboard, confirm the Gmail auth config used by
   `COMPOSIO_AUTH_CONFIG_ID` is live (not sandbox) and has the Gmail scopes
   the app requests (read + send).
2. Set the trigger's webhook destination to
   `https://<fly-app>.fly.dev/webhooks/composio` — this is the route
   `app/routers/webhooks_composio.py` mounts, verified via HMAC-SHA256 over
   the raw body using `COMPOSIO_WEBHOOK_SECRET`.
3. Confirm the "new Gmail message" trigger type is enabled for connected
   accounts so `ingest_message` actually receives inbound mail.
4. Copy the webhook signing secret from Composio into
   `COMPOSIO_WEBHOOK_SECRET` (step 2 above) — signatures won't verify
   otherwise and every webhook will 401.

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
