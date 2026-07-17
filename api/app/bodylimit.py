"""Request-body size limits, enforced as pure ASGI middleware.

The webhook routes are public and read the entire body into memory before
signature verification (`await request.body()`), and neither uvicorn nor
Fly's proxy bounds body size — so without this, an attacker can POST
arbitrarily large bodies (within the per-IP rate limit) and exhaust the
machine's memory regardless of signature validity. Internal routes get a
larger default that still comfortably covers the biggest legitimate body
(the 10MB KB upload plus multipart overhead).

Implemented as raw ASGI (not `BaseHTTPMiddleware`) so streamed request
bodies pass through chunk-by-chunk: the `Content-Length` header is checked
up front when present, and actual received bytes are counted as they
stream, so a chunked request without `Content-Length` (or one that lies)
cannot bypass the limit.
"""

WEBHOOK_MAX_BODY_BYTES = 1 * 1024 * 1024
"""Composio/Stripe webhook payloads are a few KB; 1MB is generous."""

DEFAULT_MAX_BODY_BYTES = 12 * 1024 * 1024
"""KB uploads cap file content at 10MB — 12MB covers multipart overhead."""

_WEBHOOK_PATH_PREFIX = "/webhooks/"


class _BodyTooLarge(Exception):
    pass


def _limit_for_path(path: str) -> int:
    if path.startswith(_WEBHOOK_PATH_PREFIX):
        return WEBHOOK_MAX_BODY_BYTES
    return DEFAULT_MAX_BODY_BYTES


async def _send_413(send) -> None:
    body = b"request body too large"
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = _limit_for_path(scope.get("path", ""))

        # Fast path: a declared Content-Length over the limit is rejected
        # before the app reads anything.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > limit:
                        await _send_413(send)
                        return
                except ValueError:
                    pass
                break

        received = 0
        response_started = False

        async def wrapped_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        async def wrapped_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except _BodyTooLarge:
            if response_started:
                # Too late for a clean 413 — let the server tear the
                # connection down rather than send a corrupt response.
                raise
            await _send_413(send)
