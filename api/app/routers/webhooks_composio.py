"""Composio Gmail webhook ingestion.

Mounted *outside* `workspace_id_dep` — Composio calls this route directly,
so it authenticates via HMAC signature verification instead of the
internal API key / workspace header pair every other route uses.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app import composio_client
from app.db import get_db
from app.ingest import ingest_message
from app.pipeline import process_inbound
from app.ratelimit import rate_limit_dependency

router = APIRouter()

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "webhook-signature"
ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"


async def verify_composio_signature(raw_body: bytes, headers) -> bool:
    """Verify an inbound Composio webhook using the real standard-webhooks
    scheme (`webhook-id` / `webhook-timestamp` / `webhook-signature` headers,
    HMAC-SHA256 over `f"{id}.{timestamp}.{body}"`), delegated to
    `composio_client.verify_webhook` (a thin wrapper around
    `client.triggers.verify_webhook`).

    The signing secret comes from `COMPOSIO_WEBHOOK_SECRET` if set, else the
    secret auto-registered at startup via `ensure_webhook_subscription`. If
    neither is available, verification fails closed."""
    webhook_id = headers.get(ID_HEADER)
    timestamp = headers.get(TIMESTAMP_HEADER)
    signature = headers.get(SIGNATURE_HEADER)
    if not webhook_id or not timestamp or not signature:
        return False

    secret = await composio_client.ensure_webhook_subscription()
    if not secret:
        logger.warning(
            "No Composio webhook secret available (set COMPOSIO_WEBHOOK_SECRET or "
            "BACKEND_PUBLIC_URL so it can be auto-registered) — rejecting webhook."
        )
        return False

    return await composio_client.verify_webhook(
        id=webhook_id,
        payload=raw_body.decode(),
        secret=secret,
        signature=signature,
        timestamp=timestamp,
    )


pipeline_hook = process_inbound
"""Task 8 wires this seam to `pipeline.process_inbound`. Referenced via
module attribute (`webhooks_composio.pipeline_hook`) everywhere it's
called so tests can swap it out with `monkeypatch.setattr` /
direct reassignment."""


def _parse_received_at(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@router.post("/webhooks/composio", dependencies=[Depends(rate_limit_dependency)])
async def receive_composio_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw_body = await request.body()

    if not await verify_composio_signature(raw_body, request.headers):
        return Response(status_code=401, content="invalid signature")

    try:
        payload = await request.json()
        connection_id = payload.get("connectionId")
    except (ValueError, KeyError, TypeError, AttributeError):
        # Signature already verified — a malformed body from a legitimate
        # sender shouldn't be treated as an error. Degrade gracefully.
        return {"ok": True, "skipped": True}

    db = get_db()
    connection = await db.connections.find_one({"composioConnectionId": connection_id})
    if connection is None or connection.get("status") != "active":
        # Either no workspace resolves to this connection id at all, or it
        # resolves to one that's pending/disconnected — e.g. the user just
        # disconnected and a stale/racing webhook delivery arrived after.
        # Ingesting on behalf of a non-active connection would resurrect a
        # severed connection's inbox processing, so skip.
        return {"ok": True, "skipped": True}

    workspace_id = connection["workspaceId"]
    try:
        message = payload["message"]
        raw = {
            "gmailMessageId": message["gmailMessageId"],
            "gmailThreadId": message["gmailThreadId"],
            "subject": message.get("subject", ""),
            "fromEmail": message["fromEmail"],
            "fromName": message.get("fromName"),
            "toEmail": message.get("toEmail", ""),
            "bodyText": message.get("bodyText", ""),
            "bodyHtml": message.get("bodyHtml"),
            "receivedAt": _parse_received_at(message["receivedAt"]),
            "isOutbound": message.get("isOutbound", False),
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        # Missing/invalid "message" or field shape — same graceful-degrade
        # rationale as the JSON-parse failure above.
        return {"ok": True, "skipped": True}

    message_id = await ingest_message(db, workspace_id, raw, connection.get("emailAddress"))

    if message_id is not None:
        background_tasks.add_task(pipeline_hook, workspace_id, message_id)

    return {"ok": True}
