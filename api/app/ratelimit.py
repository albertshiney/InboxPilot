"""Simple in-memory sliding-window rate limiter for the two webhook routes
(`/webhooks/composio`, `/webhooks/stripe`).

Both webhook senders (Composio, Stripe) can retry aggressively on transient
failures, and these routes sit outside `workspace_id_dep`'s internal-API-key
gate — so they're the two routes most exposed to abuse/hammering. A single
process-local dict keyed by client IP is enough: InboxPilot runs as a
single Fly.io machine per environment, so there's no need for a shared
store (Redis etc.) to make the limit correct across instances.

Requests with an invalid webhook signature still consume rate-limit budget
before they're rejected — that's intended for an IP-keyed limiter: the
limiter's job is to bound how many requests a given source can make at all,
signature-valid or not.

Not thread-safe against true concurrent mutation of the same deque, but
FastAPI's async event loop runs one coroutine at a time between awaits and
nothing here awaits mid-mutation, so this is safe under asyncio.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60
# Both webhook senders are trusted platforms that egress from a small pool of
# IPs, so every customer's deliveries share the same per-IP bucket — the HMAC
# signature check is the real authentication gate, and this limiter is only a
# flood backstop. 120/min was low enough that one high-volume mailbox could
# 429 every other customer's deliveries; 600/min keeps the backstop while
# leaving headroom for legitimate aggregate traffic. Per-sender fairness is
# enforced separately (per-connected-account limiter in webhooks_composio).
MAX_REQUESTS_PER_MINUTE = 600

# Once the number of tracked IPs crosses this, a request prunes and evicts
# every stale entry across the whole dict in one sweep, rather than just its
# own IP's key — bounds memory under a wide-IP-range flood instead of
# growing unboundedly with one deque per distinct source IP ever seen.
_MAX_TRACKED_IPS = 10_000

_hits: dict[str, deque] = defaultdict(deque)


class SlidingWindowLimiter:
    """Reusable in-process sliding-window limiter keyed by an arbitrary
    string (workspace id, connected-account id, ...). Same asyncio-safety
    rationale as the module docstring: `allow` has no awaits between the
    check and the append, so no two coroutines can interleave mid-decision.

    Every instance registers itself so `reset_rate_limiter()` (called by the
    test conftest between tests) clears it along with the IP-keyed state.
    """

    _instances: list["SlidingWindowLimiter"] = []

    def __init__(self, max_per_window: int, window_seconds: float) -> None:
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        SlidingWindowLimiter._instances.append(self)

    def allow(self, key: str) -> bool:
        """Record a hit for `key` and return True, or return False (without
        recording) once the key is at its per-window budget."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if not hits:
            # Drop-and-recreate keeps the dict from accumulating one empty
            # deque per key ever seen.
            del self._hits[key]
            hits = self._hits[key]
        if len(hits) >= self.max_per_window:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


def reset_rate_limiter() -> None:
    """Test-only hook: clears all sliding-window state so tests don't leak
    hit counts into each other (or into the same IP bucket across tests)."""
    _hits.clear()
    for limiter in SlidingWindowLimiter._instances:
        limiter.reset()


def _client_ip(request: Request) -> str:
    # Fly.io terminates TLS at its edge and proxies to the app over a
    # private network, so `request.client.host` is Fly's proxy address, not
    # the real client. Fly sets `Fly-Client-IP` itself (it can't be spoofed
    # by the client — Fly's edge overwrites it), so prefer that when
    # present. Otherwise fall back to `X-Forwarded-For`: that header is
    # attacker-controlled up to the last hop (a client can send
    # `X-Forwarded-For: evil, 1.2.3.4` to try to get bucketed as "evil"), so
    # take the LAST entry — the one the trusted proxy appended — not the
    # first. Finally fall back to `request.client.host` for local dev /
    # direct connections where no proxy sets either header.
    fly_client_ip = request.headers.get("fly-client-ip")
    if fly_client_ip:
        return fly_client_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _evict_stale(now: float, skip_key: str | None = None) -> None:
    """Full sweep: prune expired hits from every tracked IP's deque (not
    just the current request's) and drop any key left with an empty deque.
    Without this, `_hits` grows by one key per distinct IP ever seen and
    never shrinks — a wide range of one-off/rotating source IPs is a
    memory-exhaustion vector, since only the *current* request's own IP is
    ever pruned otherwise. `skip_key` skips the current request's IP, which
    the caller already pruned directly."""
    for key, hits in list(_hits.items()):
        if key == skip_key:
            continue
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if not hits:
            del _hits[key]


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency: raises 429 once an IP exceeds
    `MAX_REQUESTS_PER_MINUTE` requests within a trailing `WINDOW_SECONDS`
    sliding window; otherwise records this request and returns."""
    ip = _client_ip(request)
    now = time.monotonic()
    hits = _hits[ip]

    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()

    if not hits:
        del _hits[ip]
        hits = _hits[ip]

    if len(_hits) > _MAX_TRACKED_IPS:
        _evict_stale(now, skip_key=ip)

    if len(hits) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    hits.append(now)
