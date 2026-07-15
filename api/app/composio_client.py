"""Thin wrapper around the Composio Python SDK (`composio` 0.17.x).

Every call into the Composio SDK for Gmail connect/trigger/action/webhook
flows is funneled through the functions below so that:

  1. Tests monkeypatch *this module* (either the public functions, or
     `_client` with a fake recording object), never a real SDK client — the
     SDK's own object graph (auth configs, connected accounts, tool
     execution) is irrelevant to callers.
  2. A future SDK surface change (composio 0.17 -> vNext) is a one-file
     change.

The call shapes used here (`client.connected_accounts.initiate`,
`client.toolkits.authorize`, `client.triggers.verify_webhook`,
`client.triggers.set_webhook_subscription`, `client.triggers.create`,
`client.tools.execute`, etc.) are verified against the installed SDK
(0.17.1); if a future Composio release changes these signatures, adjust the
bodies of the functions in this module only — their signatures are the
contract the rest of the app depends on.
"""

import asyncio
import logging
from datetime import datetime
from functools import lru_cache
from typing import TypedDict

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cached secret from `ensure_webhook_subscription`, set once at startup when
# the auto-registration path runs (no explicit `COMPOSIO_WEBHOOK_SECRET`).
# Module-level cache (not `lru_cache`) so `_reset_webhook_secret_cache` can
# clear it between tests without needing to know the wrapped function.
_webhook_secret_cache: str | None = None


def _reset_webhook_secret_cache() -> None:
    """Test seam: clear the cached auto-registered webhook secret."""
    global _webhook_secret_cache
    _webhook_secret_cache = None


class RawGmailMessage(TypedDict):
    gmailMessageId: str
    gmailThreadId: str
    subject: str
    fromEmail: str
    fromName: str | None
    toEmail: str
    bodyText: str
    bodyHtml: str | None
    receivedAt: datetime
    isOutbound: bool


@lru_cache
def _client():
    from composio import Composio

    return Composio(api_key=get_settings().composio_api_key)


async def initiate_connection(workspace_id: str) -> dict:
    """Start the Gmail OAuth connect flow for a workspace.

    When `COMPOSIO_AUTH_CONFIG_ID` is unset, uses Composio-managed auth
    (`toolkits.authorize`) — Composio creates/reuses its own managed Gmail
    auth config, so no auth config id is required up front. When set (a
    bring-your-own Google OAuth app), uses `connected_accounts.initiate`
    against that specific auth config, same as before.

    Returns `{"redirectUrl": str, "connectionId": str}`.
    """
    client = _client()
    auth_config_id = get_settings().composio_auth_config_id
    if auth_config_id:
        result = await asyncio.to_thread(
            client.connected_accounts.initiate,
            user_id=workspace_id,
            auth_config_id=auth_config_id,
            toolkit="gmail",
        )
    else:
        result = await asyncio.to_thread(
            client.toolkits.authorize,
            user_id=workspace_id,
            toolkit="gmail",
        )
    return {
        "redirectUrl": getattr(result, "redirect_url", None) or result["redirect_url"],
        "connectionId": getattr(result, "id", None) or result["id"],
    }


async def get_connection_status(connection_id: str) -> dict:
    """Poll the SDK for a connected account's current state.

    Returns `{"status": str, "emailAddress": str | None}`.
    """
    client = _client()
    account = await asyncio.to_thread(client.connected_accounts.get, connection_id)
    status = getattr(account, "status", None) or account.get("status")
    email_address = None
    metadata = getattr(account, "connection_data", None) or {}
    if isinstance(metadata, dict):
        email_address = metadata.get("emailAddress") or metadata.get("email")
    return {"status": status, "emailAddress": email_address}


async def fetch_recent_messages(connection_id: str, since_dt: datetime) -> list[RawGmailMessage]:
    """Fallback-sync path: list Gmail messages received since `since_dt` for
    the given connected account, normalized to `RawGmailMessage`."""
    client = _client()
    result = await asyncio.to_thread(
        client.tools.execute,
        "GMAIL_FETCH_EMAILS",
        connected_account_id=connection_id,
        arguments={"after": since_dt.isoformat()},
    )
    data = result.get("data") if isinstance(result, dict) else getattr(result, "data", {})
    raw_messages = (data or {}).get("messages", [])

    messages: list[RawGmailMessage] = []
    for m in raw_messages:
        messages.append(
            RawGmailMessage(
                gmailMessageId=m["messageId"],
                gmailThreadId=m["threadId"],
                subject=m.get("subject", ""),
                fromEmail=m.get("sender", ""),
                fromName=m.get("senderName"),
                toEmail=m.get("to", ""),
                bodyText=m.get("messageText", ""),
                bodyHtml=m.get("messageHtml"),
                receivedAt=m["receivedAt"],
                isOutbound=m.get("isOutbound", False),
            )
        )
    return messages


async def reply_to_thread(connection_id: str, gmail_thread_id: str, body: str) -> dict:
    """Send a reply in an existing Gmail thread via the connected account.

    Returns `{"gmailMessageId": str}`.
    """
    client = _client()
    result = await asyncio.to_thread(
        client.tools.execute,
        "GMAIL_REPLY_TO_THREAD",
        connected_account_id=connection_id,
        arguments={"thread_id": gmail_thread_id, "body": body},
    )
    data = result.get("data") if isinstance(result, dict) else getattr(result, "data", {})
    return {"gmailMessageId": (data or {}).get("id")}


async def verify_webhook(
    *, id: str, payload: str, secret: str, signature: str, timestamp: str
) -> bool:
    """Verify an inbound Composio webhook's HMAC signature using the SDK's
    standard-webhooks scheme (`client.triggers.verify_webhook`):
    HMAC-SHA256 over `f"{id}.{timestamp}.{payload}"`, base64-encoded,
    compared against the `"v1,<base64>"` signature header, with a timestamp
    tolerance window.

    This function answers exactly one question — "is the signature
    legitimate" — deliberately decoupled from whether `payload` happens to
    parse as one of the SDK's known trigger-event envelopes (V1/V2/V3).
    `client.triggers.verify_webhook` conflates the two: it validates the
    signature *and then* parses `payload` into a normalized trigger event,
    raising `WebhookPayloadError` if the body doesn't match a recognized
    shape — which it wouldn't for this app's own ingestion payload shape.
    So a `WebhookPayloadError` reached after we've confirmed the timestamp
    is well-formed (see below) means the signature check upstream of it
    already passed, and is treated as a verified signature; the route's own
    JSON/field parsing is what decides whether the (correctly signed) body
    is otherwise usable.

    Returns `False` on any actual verification failure (bad signature,
    stale/malformed timestamp) rather than raising — callers treat this as
    a plain yes/no gate.
    """
    try:
        int(timestamp)
    except (TypeError, ValueError):
        return False

    client = _client()
    try:
        await asyncio.to_thread(
            client.triggers.verify_webhook,
            id=id,
            payload=payload,
            secret=secret,
            signature=signature,
            timestamp=timestamp,
        )
        return True
    except Exception as exc:
        from composio.exceptions import WebhookPayloadError

        # Timestamp is already known well-formed at this point, so a
        # WebhookPayloadError here can only be the post-signature-check
        # trigger-envelope parse failing — i.e. the signature was valid.
        return isinstance(exc, WebhookPayloadError)


async def ensure_webhook_subscription() -> str | None:
    """Resolve the Composio webhook signing secret, auto-registering the
    project's webhook subscription if needed.

    Resolution order:
      1. `COMPOSIO_WEBHOOK_SECRET` env var, if non-empty — used verbatim.
      2. A previously cached secret from an earlier call in this process.
      3. If `BACKEND_PUBLIC_URL` and `COMPOSIO_API_KEY` are both set, call
         `client.triggers.set_webhook_subscription` (idempotent
         create-or-update) pointed at `{BACKEND_PUBLIC_URL}/webhooks/composio`,
         cache and return the secret it hands back.
      4. Otherwise `None` — signature verification will fail closed.
    """
    global _webhook_secret_cache

    settings = get_settings()
    if settings.composio_webhook_secret:
        return settings.composio_webhook_secret

    if _webhook_secret_cache:
        return _webhook_secret_cache

    if not settings.backend_public_url or not settings.composio_api_key:
        return None

    client = _client()
    webhook_url = f"{settings.backend_public_url.rstrip('/')}/webhooks/composio"
    result = await asyncio.to_thread(
        client.triggers.set_webhook_subscription,
        webhook_url=webhook_url,
    )
    secret = result.get("secret") if isinstance(result, dict) else getattr(result, "secret", None)
    if secret:
        _webhook_secret_cache = secret
    return secret


async def ensure_gmail_trigger(connection_id: str) -> None:
    """Enable the "new Gmail message" trigger for a connected account.

    `client.triggers.create` is upsert semantics, so this is safe to call
    every time a connection flips to active — repeated calls for the same
    connected account are a no-op rather than a duplicate trigger.
    Exceptions are logged, never raised — the connection is already active
    from the caller's perspective, and trigger setup failing shouldn't fail
    that response.
    """
    client = _client()
    try:
        await asyncio.to_thread(
            client.triggers.create,
            "GMAIL_NEW_GMAIL_MESSAGE",
            connected_account_id=connection_id,
        )
    except Exception:
        logger.exception(
            "Failed to enable GMAIL_NEW_GMAIL_MESSAGE trigger for connection %s", connection_id
        )
