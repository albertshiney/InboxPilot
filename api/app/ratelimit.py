"""Simple in-memory sliding-window rate limiter for the two webhook routes
(`/webhooks/composio`, `/webhooks/stripe`).

Both webhook senders (Composio, Stripe) can retry aggressively on transient
failures, and these routes sit outside `workspace_id_dep`'s internal-API-key
gate — so they're the two routes most exposed to abuse/hammering. A single
process-local dict keyed by client IP is enough: InboxPilot runs as a
single Fly.io machine per environment, so there's no need for a shared
store (Redis etc.) to make the limit correct across instances.

Not thread-safe against true concurrent mutation of the same deque, but
FastAPI's async event loop runs one coroutine at a time between awaits and
nothing here awaits mid-mutation, so this is safe under asyncio.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_MINUTE = 120

_hits: dict[str, deque] = defaultdict(deque)


def reset_rate_limiter() -> None:
    """Test-only hook: clears all sliding-window state so tests don't leak
    hit counts into each other (or into the same IP bucket across tests)."""
    _hits.clear()


def _client_ip(request: Request) -> str:
    # Fly.io terminates TLS at its edge and proxies to the app over a
    # private network, so `request.client.host` is Fly's proxy address, not
    # the real client — the actual client IP arrives in `X-Forwarded-For`
    # (comma-separated, original client first, each hop appending its own
    # peer after). Read that first entry when present; fall back to
    # `request.client.host` for local dev / direct connections where no
    # proxy sets the header.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency: raises 429 once an IP exceeds
    `MAX_REQUESTS_PER_MINUTE` requests within a trailing `WINDOW_SECONDS`
    sliding window; otherwise records this request and returns."""
    ip = _client_ip(request)
    now = time.monotonic()
    hits = _hits[ip]

    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()

    if len(hits) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    hits.append(now)
