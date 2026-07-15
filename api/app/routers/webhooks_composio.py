"""Composio Gmail webhook ingestion.

Mounted *outside* `workspace_id_dep` — Composio calls this route directly,
so it authenticates via HMAC signature verification instead of the
internal API key / workspace header pair every other route uses.

The real Composio V3 trigger webhook envelope (verified against the
installed SDK, `composio` 0.17.1, `composio/core/models/triggers.py`) is:

    {
      "type": "composio.trigger.message",
      "id": "...",
      "timestamp": "...",
      "metadata": {
        "connected_account_id": "...",
        "trigger_slug": "GMAIL_NEW_GMAIL_MESSAGE",
        "trigger_id": "...",
        "auth_config_id": "...",
        "user_id": "...",
      },
      "data": { ... toolkit-specific fields, e.g. Gmail message fields ... },
    }

`composio_client.verify_webhook` verifies the signature and hands back the
SDK's *normalized* `TriggerEvent` for this envelope (`trigger_slug`,
`metadata.connected_account.id`, `payload` for the inner `data`). This
route only falls back to reading `metadata`/`data` off the raw JSON body
directly when the SDK couldn't normalize the payload (still a verified
signature — see `verify_composio_signature`).
"""

import json
import logging
from datetime import datetime
from typing import Any, NamedTuple

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app import composio_client
from app.config import get_settings
from app.db import get_db
from app.ingest import ingest_message
from app.pipeline import process_inbound
from app.ratelimit import rate_limit_dependency

router = APIRouter()

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "webhook-signature"
ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"

GMAIL_NEW_MESSAGE_TRIGGER_SLUG = "GMAIL_NEW_GMAIL_MESSAGE"


class VerifyOutcome(NamedTuple):
    """Result of `verify_composio_signature`.

    `signature_valid=False` means the request must be rejected (401) —
    everything else (an unparseable-but-signed body, an unrelated trigger
    slug, a missing connection) is a *graceful skip* (200), handled by the
    route itself.
    """

    signature_valid: bool
    event: dict[str, Any] | None


async def verify_composio_signature(raw_body: bytes, headers) -> VerifyOutcome:
    """Verify an inbound Composio webhook using the real standard-webhooks
    scheme (`webhook-id` / `webhook-timestamp` / `webhook-signature` headers,
    HMAC-SHA256 over `f"{id}.{timestamp}.{body}"`), delegated to
    `composio_client.verify_webhook` (a thin wrapper around
    `client.triggers.verify_webhook`), and returns the SDK's normalized
    trigger event alongside the pass/fail signature outcome.

    The signing secret comes from `COMPOSIO_WEBHOOK_SECRET` if set, else the
    secret auto-registered at startup via `ensure_webhook_subscription`. If
    neither is available, verification fails closed.

    If the secret came from the auto-registration cache (not env-pinned)
    and verification fails against it, the secret may have been rotated
    server-side since it was cached; the cache is invalidated once and
    verification is retried against a freshly fetched secret before giving
    up. An env-pinned `COMPOSIO_WEBHOOK_SECRET` has no such retry path —
    restart the process after rotating that secret.
    """
    webhook_id = headers.get(ID_HEADER)
    timestamp = headers.get(TIMESTAMP_HEADER)
    signature = headers.get(SIGNATURE_HEADER)
    if not webhook_id or not timestamp or not signature:
        return VerifyOutcome(False, None)

    secret = await composio_client.ensure_webhook_subscription()
    if not secret:
        logger.warning(
            "No Composio webhook secret available (set COMPOSIO_WEBHOOK_SECRET or "
            "BACKEND_PUBLIC_URL so it can be auto-registered) — rejecting webhook."
        )
        return VerifyOutcome(False, None)

    payload_str = raw_body.decode(errors="replace")
    result = await composio_client.verify_webhook(
        id=webhook_id,
        payload=payload_str,
        secret=secret,
        signature=signature,
        timestamp=timestamp,
    )

    if result is None:
        settings = get_settings()
        if not settings.composio_webhook_secret:
            # Secret is auto-registered/cached, not env-pinned — it may have
            # been rotated. Invalidate the cache once and retry with a
            # freshly fetched secret before failing.
            fresh_secret = await composio_client.ensure_webhook_subscription(
                force_refresh=True
            )
            if fresh_secret and fresh_secret != secret:
                result = await composio_client.verify_webhook(
                    id=webhook_id,
                    payload=payload_str,
                    secret=fresh_secret,
                    signature=signature,
                    timestamp=timestamp,
                )
        if result is None:
            return VerifyOutcome(False, None)

    return VerifyOutcome(True, result.get("event"))


pipeline_hook = process_inbound
"""Task 8 wires this seam to `pipeline.process_inbound`. Referenced via
module attribute (`webhooks_composio.pipeline_hook`) everywhere it's
called so tests can swap it out with `monkeypatch.setattr` /
direct reassignment."""


def _parse_received_at(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _first(data: dict, *keys: str):
    """Return the first present, non-`None` value for `keys` in `data`.

    Used for the Gmail `data` fields whose exact wire spelling
    (snake_case vs camelCase) is a documented live smoke-check, not
    something verified against SDK source — so both plausible spellings
    are tried."""
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


@router.post("/webhooks/composio", dependencies=[Depends(rate_limit_dependency)])
async def receive_composio_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw_body = await request.body()

    outcome = await verify_composio_signature(raw_body, request.headers)
    if not outcome.signature_valid:
        return Response(status_code=401, content="invalid signature")

    try:
        raw_json = json.loads(raw_body.decode(errors="replace"))
    except (ValueError, TypeError):
        raw_json = None
    raw_metadata = (raw_json.get("metadata") if isinstance(raw_json, dict) else None) or {}
    raw_data = (raw_json.get("data") if isinstance(raw_json, dict) else None) or {}

    event = outcome.event
    if event is not None:
        # Normalized SDK TriggerEvent — prefer it, but fall back to the raw
        # dict fields for anything it left empty (defensive; in practice the
        # SDK normalizes this envelope fully).
        trigger_slug = event.get("trigger_slug") or raw_metadata.get("trigger_slug", "")
        connected_account_id = (
            (event.get("metadata") or {}).get("connected_account", {}).get("id")
            or raw_metadata.get("connected_account_id", "")
        )
        data = event.get("payload") or raw_data
    else:
        # Signature verified, but the SDK couldn't normalize this payload
        # into a known trigger envelope — read the raw dict fields directly
        # per the documented V3 trigger envelope shape.
        trigger_slug = raw_metadata.get("trigger_slug", "")
        connected_account_id = raw_metadata.get("connected_account_id", "")
        data = raw_data

    if trigger_slug != GMAIL_NEW_MESSAGE_TRIGGER_SLUG:
        # Some other trigger slug (or an unparseable/non-trigger event) —
        # not ours to handle.
        return {"ok": True, "skipped": True}

    if not connected_account_id or not isinstance(data, dict):
        return {"ok": True, "skipped": True}

    db = get_db()
    connection = await db.connections.find_one({"composioConnectionId": connected_account_id})
    if connection is None or connection.get("status") != "active":
        # Either no workspace resolves to this connection id at all, or it
        # resolves to one that's pending/disconnected — e.g. the user just
        # disconnected and a stale/racing webhook delivery arrived after.
        # Ingesting on behalf of a non-active connection would resurrect a
        # severed connection's inbox processing, so skip.
        return {"ok": True, "skipped": True}

    workspace_id = connection["workspaceId"]
    try:
        gmail_message_id = _first(data, "message_id", "messageId")
        gmail_thread_id = _first(data, "thread_id", "threadId")
        if not gmail_message_id or not gmail_thread_id:
            return {"ok": True, "skipped": True}

        raw = {
            "gmailMessageId": gmail_message_id,
            "gmailThreadId": gmail_thread_id,
            "subject": data.get("subject") or "",
            "fromEmail": data.get("sender") or "",
            "fromName": data.get("senderName") or data.get("fromName"),
            "toEmail": data.get("to") or data.get("toEmail") or "",
            "bodyText": _first(data, "message_text", "messageText") or "",
            "bodyHtml": _first(data, "message_html", "messageHtml"),
            "receivedAt": _parse_received_at(
                _first(data, "message_timestamp", "receivedAt")
            ),
            "isOutbound": data.get("isOutbound", False),
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        # Missing/invalid "data" field shape — same graceful-degrade
        # rationale as the JSON-parse failure above.
        return {"ok": True, "skipped": True}

    message_id = await ingest_message(db, workspace_id, raw, connection.get("emailAddress"))

    if message_id is not None:
        background_tasks.add_task(pipeline_hook, workspace_id, message_id)

    return {"ok": True}
