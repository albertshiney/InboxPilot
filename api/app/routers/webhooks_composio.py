"""Composio Gmail webhook ingestion.

Mounted *outside* `workspace_id_dep` — Composio calls this route directly,
so it authenticates via HMAC signature verification instead of the
internal API key / workspace header pair every other route uses.
"""

import hashlib
import hmac
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.config import get_settings
from app.db import get_db
from app.ingest import ingest_message

router = APIRouter()

SIGNATURE_HEADER = "webhook-signature"


def verify_composio_signature(raw_body: bytes, headers) -> bool:
    """HMAC-SHA256 of the raw request body, keyed by
    `COMPOSIO_WEBHOOK_SECRET`, compared against the `webhook-signature`
    header. Kept isolated so the exact header/encoding scheme can be
    adjusted against Composio's webhook docs without touching the route."""
    secret = get_settings().composio_webhook_secret
    provided = headers.get(SIGNATURE_HEADER)
    if not secret or not provided:
        return False

    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


async def pipeline_hook(workspace_id: str, message_id: str) -> None:
    """No-op seam for Task 6/8's `pipeline.process_inbound`. Referenced via
    module attribute (`webhooks_composio.pipeline_hook`) everywhere it's
    called so a later task can swap it in with `monkeypatch.setattr` /
    direct reassignment."""
    return None


def _parse_received_at(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@router.post("/webhooks/composio")
async def receive_composio_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    raw_body = await request.body()

    if not verify_composio_signature(raw_body, request.headers):
        return Response(status_code=401, content="invalid signature")

    payload = await request.json()
    connection_id = payload.get("connectionId")

    db = get_db()
    connection = await db.connections.find_one({"composioConnectionId": connection_id})
    if connection is None:
        return {"ok": True, "skipped": True}

    workspace_id = connection["workspaceId"]
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

    message_id = await ingest_message(db, workspace_id, raw)

    if message_id is not None:
        background_tasks.add_task(pipeline_hook, workspace_id, message_id)

    return {"ok": True}
