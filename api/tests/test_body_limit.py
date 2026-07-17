"""Tests for the request-body size limit middleware.

Webhook routes are public and read the whole body before signature
verification, so oversized bodies must be rejected up front (413) — both
via the Content-Length fast path and by counting streamed bytes so a
chunked request without Content-Length can't bypass the limit.
"""

import pytest

from app import bodylimit
from app.bodylimit import BodySizeLimitMiddleware

WEBHOOK_PATH = "/webhooks/composio"


async def test_oversized_webhook_body_returns_413(client, mock_db):
    body = b"x" * (bodylimit.WEBHOOK_MAX_BODY_BYTES + 1)

    res = await client.post(
        WEBHOOK_PATH, content=body, headers={"content-type": "application/json"}
    )

    assert res.status_code == 413


async def test_webhook_body_at_limit_passes_middleware(client, mock_db):
    # A body within the limit must reach the route itself — which rejects
    # it as unsigned (401), proving the middleware let it through.
    body = b"{}"

    res = await client.post(
        WEBHOOK_PATH, content=body, headers={"content-type": "application/json"}
    )

    assert res.status_code == 401


async def test_streamed_body_without_content_length_is_capped():
    """Chunked transfer (no Content-Length) must still be bounded: the
    middleware counts bytes as they stream and aborts with 413."""

    async def inner_app(scope, receive, send):
        # Drain the body like a real route would.
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BodySizeLimitMiddleware(inner_app)

    chunk = b"x" * 1024
    chunks_needed = bodylimit.WEBHOOK_MAX_BODY_BYTES // len(chunk) + 2
    sent = 0

    async def receive():
        nonlocal sent
        sent += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": sent < chunks_needed,
        }

    responses = []

    async def send(message):
        responses.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": WEBHOOK_PATH,
        "headers": [],
    }
    await middleware(scope, receive, send)

    start = next(m for m in responses if m["type"] == "http.response.start")
    assert start["status"] == 413


async def test_non_webhook_routes_get_default_limit(client, mock_db):
    from tests.conftest import HEADERS

    body = b"x" * (bodylimit.DEFAULT_MAX_BODY_BYTES + 1)

    res = await client.post("/kb/upload", content=body, headers=HEADERS)

    assert res.status_code == 413


async def test_webhook_limit_is_stricter_than_default():
    assert bodylimit.WEBHOOK_MAX_BODY_BYTES < bodylimit.DEFAULT_MAX_BODY_BYTES
