# Security Launch Checklist — Operational Items

These are the security remediations that **cannot be fixed in code** and must be
done by an operator before/at MVP launch. The code-level fixes (SSRF, rate
limits, trial abuse, upload caps, LLM screening, indexes, headers) are handled in
the codebase separately.

---

## C1 — Rotate all live credentials (CRITICAL, do before launch)

The following real secrets currently live in local `.env` files. The files are
**not** committed to git (verified: gitignored, never in history), so this is not
a public leak — but every value below was exposed in plaintext outside a secret
manager and must be rotated, then stored in the platform secret store (Fly
secrets for the API, Vercel env for the web app), never in a committed file.

Rotate each, then set via `fly secrets set KEY=...` / Vercel dashboard:

- [ ] **MongoDB** — rotate the `albert_db_user` password in Atlas (or create a new
      user and delete the old). This user is cluster-admin; see the least-privilege
      note below. Update `MONGODB_URI` in both API (Fly) and web (Vercel).
- [ ] **NEXTAUTH_SECRET** — generate a new value (`openssl rand -base64 32`).
      Rotating this invalidates existing sessions (acceptable pre-launch).
- [ ] **INTERNAL_API_KEY** — generate a new random value; must match between web
      (Vercel) and API (Fly). See H1 below.
- [ ] **ANTHROPIC_API_KEY** — roll in the Anthropic console.
- [ ] **OPENAI_API_KEY** — roll in the OpenAI dashboard.
- [ ] **COMPOSIO_API_KEY** — roll in the Composio dashboard.
- [ ] **STRIPE_SECRET_KEY** — currently a test-mode key. Roll it, and swap to the
      live key when going to production. Update `STRIPE_WEBHOOK_SECRET` and
      `STRIPE_PRICE_ID` to the live-mode equivalents at the same time.
- [ ] **RESEND_API_KEY** — roll in the Resend dashboard (can send mail as your
      verified domain).

### Least-privilege database users (recommended, defense in depth)
The web tier only needs the NextAuth collections (`users`, `accounts`,
`sessions`, `verification_tokens`) plus `workspaces`. Create two Atlas users:
- [ ] `api_app` — `readWrite` on `inboxpilot` (used by the FastAPI service).
- [ ] `web_app` — `readWrite` scoped to the auth + `workspaces` collections only.

Give each service its own `MONGODB_URI`. This limits blast radius if the web tier
is compromised.

---

## H1 — Restrict the backend's trust boundary (HIGH)

**Problem:** Every non-webhook FastAPI route trusts a single static
`INTERNAL_API_KEY` plus a caller-supplied `X-Workspace-Id` header. Anyone who
holds that key can set `X-Workspace-Id` to any value and read/act on any tenant.
The SSRF that leaked the key (C2) is fixed in code, and the comparison is now
constant-time — but the key remains the whole wall.

**Why this is an ops task, not a code fix:** A signed token minted by the proxy
would have to be signed with a secret. If that secret is the same shared
`INTERNAL_API_KEY`, an attacker who obtains the key can simply re-sign any
workspace id — so token-signing with the shared key adds no real protection. The
effective mitigations are operational:

- [ ] **Network-isolate the non-webhook routes.** Only the two webhook endpoints
      (`/webhooks/stripe`, `/webhooks/composio`) need to be publicly reachable.
      Put the rest behind Fly private networking / `.internal` and have the
      Vercel proxy reach the API over the private network, so an attacker on the
      public internet cannot hit `/threads`, `/settings`, etc. at all, key or no
      key. This is the single highest-value hardening for the trust model.
- [ ] **If full network isolation isn't feasible for launch:** introduce a
      dedicated `PROXY_SIGNING_SECRET` (separate from `INTERNAL_API_KEY`, known
      only to web + API), have the proxy mint a short-lived (`exp <= 60s`)
      HS256 token binding the workspace id, and verify it in `deps.py`. This
      requires updating `deps.py`, the proxy, `conftest.py`, and the API env.
      Track as a fast-follow if deferred. (Ask the code team to implement —
      deliberately not shipped in the launch batch to avoid destabilizing auth
      right before launch.)
- [ ] Confirm the Fly app has **no** public listener on the app routes
      (`fly ips list`, service config) once isolation is in place.

---

## Deployment invariants to confirm

- [ ] **Single API machine** (rate limiter is in-memory): keep the Fly app at
      exactly one machine (`fly scale count 1`) until the limiter is moved to a
      shared store, or the per-IP webhook limit multiplies per machine.
- [ ] **Stripe live mode**: verify `STRIPE_WEBHOOK_SECRET` is set in production —
      the webhook now fails closed (returns 500) if it is empty, so a missing
      secret will break billing loudly rather than accept forged events.
- [ ] **Security headers**: verify HSTS / X-Frame-Options are present on the
      deployed web app (added in `next.config.ts`).
