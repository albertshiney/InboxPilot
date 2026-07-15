import base64
import hashlib
import hmac
import json
import time

from app import ratelimit
from app.collections import ensure_indexes
from app.config import get_settings
from app.routers import webhooks_composio

WEBHOOK_PATH = "/webhooks/composio"

WEBHOOK_ID = "msg_test123"


def _sign(secret: str, raw_body: bytes, webhook_id: str = WEBHOOK_ID, timestamp: str | None = None) -> tuple[str, str]:
    """Build the real Composio/standard-webhooks signature: base64(HMAC-SHA256
    over f"{id}.{timestamp}.{body}"), returned alongside the timestamp used
    (so callers can put it in the `webhook-timestamp` header too).
    """
    if timestamp is None:
        timestamp = str(int(time.time()))
    signed_content = f"{webhook_id}.{timestamp}.{raw_body.decode()}"
    digest = hmac.new(secret.encode(), signed_content.encode(), hashlib.sha256).digest()
    signature = "v1," + base64.b64encode(digest).decode()
    return signature, timestamp


def _payload(**overrides) -> dict:
    message = {
        "gmailMessageId": "gm-1",
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "fromEmail": "customer@example.com",
        "fromName": "Cus Tomer",
        "toEmail": "support@ourcompany.com",
        "bodyText": "Hi, I never received my order.",
        "bodyHtml": "<p>Hi</p>",
        "receivedAt": "2026-07-15T12:00:00Z",
        "isOutbound": False,
    }
    message.update(overrides.pop("message", {}))
    body = {"connectionId": "conn_123", "message": message}
    body.update(overrides)
    return body


async def _post(client, secret: str, body: dict, signature: str | None = "compute"):
    raw = json.dumps(body).encode()
    timestamp = str(int(time.time()))
    if signature == "compute":
        signature, timestamp = _sign(secret, raw, timestamp=timestamp)
    headers = {"content-type": "application/json", "webhook-id": WEBHOOK_ID, "webhook-timestamp": timestamp}
    if signature is not None:
        headers["webhook-signature"] = signature
    return await client.post(WEBHOOK_PATH, content=raw, headers=headers)


async def test_webhook_rejects_bad_signature(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()

    r = await _post(client, "whsec_test", _payload(), signature="deadbeef")

    assert r.status_code == 401


async def test_webhook_unknown_connection_returns_ok_skipped(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)

    r = await _post(client, "whsec_test", _payload())

    assert r.status_code == 200
    assert r.json() == {"ok": True, "skipped": True}
    assert await mock_db.messages.count_documents({}) == 0


async def test_webhook_non_json_body_returns_ok_skipped(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)

    raw = b"not-json-at-all"
    signature, timestamp = _sign("whsec_test", raw)
    headers = {
        "content-type": "application/json",
        "webhook-id": WEBHOOK_ID,
        "webhook-timestamp": timestamp,
        "webhook-signature": signature,
    }

    r = await client.post(WEBHOOK_PATH, content=raw, headers=headers)

    assert r.status_code == 200
    assert r.json() == {"ok": True, "skipped": True}
    assert await mock_db.messages.count_documents({}) == 0


async def test_webhook_missing_message_field_returns_ok_skipped(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    body = {"connectionId": "conn_123"}  # no "message" key

    r = await _post(client, "whsec_test", body)

    assert r.status_code == 200
    assert r.json() == {"ok": True, "skipped": True}
    assert await mock_db.messages.count_documents({}) == 0


async def test_webhook_known_connection_persists_and_calls_pipeline_hook(
    client, mock_db, monkeypatch
):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    calls = []

    async def fake_hook(workspace_id, message_id):
        calls.append((workspace_id, message_id))

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_hook)

    r = await _post(client, "whsec_test", _payload())

    assert r.status_code == 200
    assert r.json() == {"ok": True}

    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message is not None

    # BackgroundTasks run after the response is sent but before the ASGI
    # transport returns control in httpx's ASGITransport, so the spy should
    # already have been invoked.
    assert len(calls) == 1
    assert calls[0][0] == "ws1"
    assert calls[0][1] == str(message["_id"])


async def test_webhook_replay_does_not_duplicate_message_or_rerun_pipeline(
    client, mock_db, monkeypatch
):
    """A duplicate delivery of the same event (Composio/Gmail retries on
    timeout, at-least-once delivery) must not create a second message row
    nor fire the drafting pipeline a second time — `ingest_message`'s
    `gmailMessageId` dedupe is what the route relies on for this."""
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    calls = []

    async def fake_hook(workspace_id, message_id):
        calls.append((workspace_id, message_id))

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_hook)

    payload = _payload()

    first = await _post(client, "whsec_test", payload)
    assert first.status_code == 200
    assert first.json() == {"ok": True}

    second = await _post(client, "whsec_test", payload)
    assert second.status_code == 200
    assert second.json() == {"ok": True}

    assert await mock_db.messages.count_documents({"gmailMessageId": "gm-1"}) == 1
    assert len(calls) == 1


async def test_webhook_disconnected_connection_returns_ok_skipped_and_ingests_nothing(
    client, mock_db, monkeypatch
):
    """A stale/racing webhook delivery that arrives after the workspace
    disconnected its Gmail connection must not resurrect ingestion for it —
    the connection resolves by id, but its stored status is no longer
    `active`, so the route should skip rather than process the message."""
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "disconnected",
        }
    )

    calls = []

    async def fake_hook(workspace_id, message_id):
        calls.append((workspace_id, message_id))

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_hook)

    r = await _post(client, "whsec_test", _payload())

    assert r.status_code == 200
    assert r.json() == {"ok": True, "skipped": True}
    assert await mock_db.messages.count_documents({}) == 0
    assert calls == []


async def test_webhook_rate_limited_after_120_requests_per_minute(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        r = await _post(client, "whsec_test", _payload())
        assert r.status_code == 200

    r = await _post(client, "whsec_test", _payload())
    assert r.status_code == 429
