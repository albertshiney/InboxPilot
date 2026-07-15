import hashlib
import hmac
import json

from app.collections import ensure_indexes
from app.config import get_settings
from app.routers import webhooks_composio

WEBHOOK_PATH = "/webhooks/composio"


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


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
    if signature == "compute":
        signature = _sign(secret, raw)
    headers = {"content-type": "application/json"}
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
    signature = _sign("whsec_test", raw)
    headers = {"content-type": "application/json", "webhook-signature": signature}

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
