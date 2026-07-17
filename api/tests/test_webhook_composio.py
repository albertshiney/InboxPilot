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
    """Build a real Composio V3 trigger webhook envelope (verified against
    the installed SDK source, `composio/core/models/triggers.py`):

        {"type": "composio.trigger.message", "id": ..., "metadata": {...},
         "data": {...}}

    with `metadata.trigger_slug` = "GMAIL_NEW_GMAIL_MESSAGE" and Gmail
    fields under `data` (field names are a documented live smoke-check, not
    SDK-verified — this app tolerates both plausible spellings)."""
    data = {
        "message_id": "gm-1",
        "thread_id": "gt-1",
        "subject": "Where is my order?",
        "sender": "customer@example.com",
        "message_text": "Hi, I never received my order.",
        "message_html": "<p>Hi</p>",
        "message_timestamp": "2026-07-15T12:00:00Z",
    }
    data.update(overrides.pop("data", {}))
    metadata = {
        "connected_account_id": "conn_123",
        "trigger_slug": "GMAIL_NEW_GMAIL_MESSAGE",
        "trigger_id": "trig_1",
        "auth_config_id": "ac_1",
        "user_id": "ws1",
    }
    metadata.update(overrides.pop("metadata", {}))
    body = {
        "type": "composio.trigger.message",
        "id": "evt_1",
        "timestamp": "2026-07-15T12:00:00Z",
        "metadata": metadata,
        "data": data,
    }
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


async def test_webhook_missing_data_fields_returns_ok_skipped(client, mock_db, monkeypatch):
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

    body = _payload(data={"message_id": None, "thread_id": None})  # no message_id/thread_id in "data"

    r = await _post(client, "whsec_test", body)

    assert r.status_code == 200
    assert r.json() == {"ok": True, "skipped": True}
    assert await mock_db.messages.count_documents({}) == 0


async def test_webhook_non_gmail_trigger_slug_returns_ok_skipped(client, mock_db, monkeypatch):
    """Only `GMAIL_NEW_GMAIL_MESSAGE` events are ours to ingest — any other
    trigger slug (or non-trigger V3 event) must be a no-op skip, not an
    error, since the shared project webhook subscription may carry other
    event types too."""
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

    body = _payload(metadata={"trigger_slug": "SLACK_NEW_MESSAGE"})

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


async def test_webhook_parses_rfc_formatted_sender_into_bare_email_and_name(
    client, mock_db, monkeypatch
):
    """Gmail delivers `sender` in full RFC 5322 form (`'"Name" <a@b.com>'`,
    verified live) — the stored `customerEmail` must be the bare address
    (it is compared against the connected mailbox and used as the reply
    recipient) with the display name split out into `customerName`."""
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

    async def fake_hook(workspace_id, message_id):
        pass

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_hook)

    body = _payload(data={"sender": '"Cus Tomer" <customer@example.com>'})

    r = await _post(client, "whsec_test", body)

    assert r.status_code == 200
    assert r.json() == {"ok": True}

    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message["from"] == "customer@example.com"

    thread = await mock_db.threads.find_one({"gmailThreadId": "gt-1"})
    assert thread["customerEmail"] == "customer@example.com"
    assert thread["customerName"] == "Cus Tomer"


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


async def test_webhook_rate_limited_after_max_requests_per_minute(client, mock_db, monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        r = await _post(client, "whsec_test", _payload())
        assert r.status_code == 200

    r = await _post(client, "whsec_test", _payload())
    assert r.status_code == 429


async def test_webhook_oversized_body_rejected_before_verification(client, mock_db, monkeypatch):
    """Bodies over MAX_WEBHOOK_BODY_BYTES are rejected with 413 — an attacker
    must not be able to make the route buffer arbitrarily large payloads."""
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()
    await ensure_indexes(mock_db)

    body = _payload(data={"message_text": "x" * (webhooks_composio.MAX_WEBHOOK_BODY_BYTES + 1)})
    r = await _post(client, "whsec_test", body)

    assert r.status_code == 413
    assert await mock_db.messages.count_documents({}) == 0


async def test_webhook_per_connected_account_rate_limited(client, mock_db, monkeypatch):
    """One connected account (one mailbox) must not be able to consume the
    whole webhook budget: past its per-account window it gets 429 so Composio
    backs off, and fallback_sync recovers anything shed."""
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

    async def fake_pipeline_hook(workspace_id, message_id):
        return None

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_pipeline_hook)

    budget = webhooks_composio._account_limiter.max_per_window
    for _ in range(budget):
        r = await _post(client, "whsec_test", _payload())
        assert r.status_code == 200

    r = await _post(client, "whsec_test", _payload())
    assert r.status_code == 429
