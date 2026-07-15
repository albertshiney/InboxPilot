"""Thin wrapper around the Composio Python SDK (`composio` 0.17.x).

Every call into the Composio SDK for Gmail connect/trigger/action flows is
funneled through the four functions below so that:

  1. Tests monkeypatch *this module*, never the SDK client directly — the
     SDK's own object graph (auth configs, connected accounts, tool
     execution) is irrelevant to callers.
  2. A future SDK surface change (composio 0.17 -> vNext) is a one-file
     change.

The exact 0.17 call shapes used here (`client.connected_accounts`,
`client.tools.execute`, etc.) are the best-effort mapping onto the SDK as
installed; if Composio's actual Gmail auth-config id / trigger payload
shape differs, adjust the bodies of these four functions only — the
signatures below are the contract the rest of the app depends on.
"""

from datetime import datetime
from functools import lru_cache
from typing import TypedDict

from app.config import get_settings


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


def initiate_connection(workspace_id: str) -> dict:
    """Start the Gmail OAuth connect flow for a workspace.

    Returns `{"redirectUrl": str, "connectionId": str}`.
    """
    client = _client()
    result = client.connected_accounts.initiate(
        user_id=workspace_id,
        auth_config_id=get_settings().composio_api_key,
        toolkit="gmail",
    )
    return {
        "redirectUrl": getattr(result, "redirect_url", None) or result["redirect_url"],
        "connectionId": getattr(result, "id", None) or result["id"],
    }


def get_connection_status(connection_id: str) -> dict:
    """Poll the SDK for a connected account's current state.

    Returns `{"status": str, "emailAddress": str | None}`.
    """
    client = _client()
    account = client.connected_accounts.get(connection_id)
    status = getattr(account, "status", None) or account.get("status")
    email_address = None
    metadata = getattr(account, "connection_data", None) or {}
    if isinstance(metadata, dict):
        email_address = metadata.get("emailAddress") or metadata.get("email")
    return {"status": status, "emailAddress": email_address}


def fetch_recent_messages(connection_id: str, since_dt: datetime) -> list[RawGmailMessage]:
    """Fallback-sync path: list Gmail messages received since `since_dt` for
    the given connected account, normalized to `RawGmailMessage`."""
    client = _client()
    result = client.tools.execute(
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


def reply_to_thread(connection_id: str, gmail_thread_id: str, body: str) -> dict:
    """Send a reply in an existing Gmail thread via the connected account.

    Returns `{"gmailMessageId": str}`.
    """
    client = _client()
    result = client.tools.execute(
        "GMAIL_REPLY_TO_THREAD",
        connected_account_id=connection_id,
        arguments={"thread_id": gmail_thread_id, "body": body},
    )
    data = result.get("data") if isinstance(result, dict) else getattr(result, "data", {})
    return {"gmailMessageId": (data or {}).get("id")}
