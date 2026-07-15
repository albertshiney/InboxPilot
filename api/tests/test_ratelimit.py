"""Tests for the in-memory sliding-window webhook rate limiter."""

from fastapi import HTTPException
import pytest

from app import ratelimit


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    """Minimal stand-in for `fastapi.Request` — only the attributes
    `rate_limit_dependency` touches (`.client.host`, `.headers`)."""

    def __init__(self, host: str = "1.2.3.4", forwarded_for: str | None = None):
        self.client = _FakeClient(host)
        self.headers = {}
        if forwarded_for is not None:
            self.headers["x-forwarded-for"] = forwarded_for


@pytest.fixture(autouse=True)
def _reset():
    ratelimit.reset_rate_limiter()
    yield
    ratelimit.reset_rate_limiter()


async def test_allows_requests_under_the_limit():
    request = _FakeRequest()
    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        await ratelimit.rate_limit_dependency(request)  # should not raise


async def test_blocks_the_request_over_the_limit():
    request = _FakeRequest()
    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        await ratelimit.rate_limit_dependency(request)

    with pytest.raises(HTTPException) as exc_info:
        await ratelimit.rate_limit_dependency(request)

    assert exc_info.value.status_code == 429


async def test_tracks_ips_independently():
    a = _FakeRequest(host="1.1.1.1")
    b = _FakeRequest(host="2.2.2.2")

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        await ratelimit.rate_limit_dependency(a)

    # `b` is a different IP and hasn't been touched — must not be limited.
    await ratelimit.rate_limit_dependency(b)


async def test_old_hits_roll_off_the_window(monkeypatch):
    request = _FakeRequest()
    fake_now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: fake_now[0])

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        await ratelimit.rate_limit_dependency(request)

    # Still within the window — the next request is blocked.
    with pytest.raises(HTTPException):
        await ratelimit.rate_limit_dependency(request)

    # Advance past the 60s window: old hits should roll off and the
    # request should be allowed again.
    fake_now[0] += ratelimit.WINDOW_SECONDS + 1
    await ratelimit.rate_limit_dependency(request)


async def test_prefers_x_forwarded_for_over_client_host():
    # Fly.io terminates TLS at the edge, so `request.client.host` is Fly's
    # proxy address, not the real client — the real IP must come from
    # X-Forwarded-For (first entry) when present.
    request = _FakeRequest(host="10.0.0.1", forwarded_for="9.9.9.9, 10.0.0.1")

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        await ratelimit.rate_limit_dependency(request)

    with pytest.raises(HTTPException) as exc_info:
        await ratelimit.rate_limit_dependency(request)
    assert exc_info.value.status_code == 429

    # A request claiming the proxy's own host directly (no X-Forwarded-For)
    # is a different bucket and must not be blocked by the above.
    direct = _FakeRequest(host="10.0.0.1")
    await ratelimit.rate_limit_dependency(direct)


def test_reset_rate_limiter_clears_all_state():
    ratelimit._hits["1.2.3.4"].append(0.0)
    ratelimit.reset_rate_limiter()
    assert len(ratelimit._hits["1.2.3.4"]) == 0
