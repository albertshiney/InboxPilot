# InboxPilot

InboxPilot is an AI customer-support tool: a user connects their support Gmail
inbox via Composio and uploads their docs (FAQs, policies, product docs).
From that point, every incoming support email is classified, matched against
their knowledge base, and gets an AI-drafted reply waiting in a review queue.
By default a human approves each draft with one click; if Autopilot is on,
replies above a confidence threshold are sent automatically and everything
else falls back to the review queue.

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
