import inspect
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from app import composio_client
from app.db import get_db
from app.deps import workspace_id_dep
from app.events import log_event
from app.ratelimit import SlidingWindowLimiter

router = APIRouter()

# Every one of these routes drives Composio API traffic (metered), and the
# generic proxy limit (120 req/min per workspace) is far too generous a bound
# for that spend. The onboarding/settings UIs poll `?live=1` at one request
# every 2s (30/min), so 60/min leaves 2x headroom for a second tab; connect
# is a once-per-click action, so 10/min is already generous.
_live_poll_limiter = SlidingWindowLimiter(max_per_window=60, window_seconds=60)
_connect_limiter = SlidingWindowLimiter(max_per_window=10, window_seconds=60)


def _throttle(limiter: SlidingWindowLimiter, workspace_id: str) -> None:
    if not limiter.allow(workspace_id):
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests, slow down",
        )


@router.get("/composio/connect")
async def connect(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Initiate the Gmail OAuth connect flow, upserting a `pending`
    `connections` doc keyed by workspace.

    If the workspace already has an `active` connection, this is a no-op:
    re-initiating would demote the existing connection back to `pending`
    and could self-lock a workspace that already has Gmail connected."""
    db = get_db()

    existing = await db.connections.find_one({"workspaceId": workspace_id, "provider": "gmail"})
    if existing is not None and existing.get("status") == "active":
        return {"alreadyConnected": True, "emailAddress": existing.get("emailAddress")}

    # Throttled after the cheap already-connected check: only requests that
    # would actually hit Composio consume budget.
    _throttle(_connect_limiter, workspace_id)

    result = composio_client.initiate_connection(workspace_id)
    if inspect.isawaitable(result):
        result = await result

    await db.connections.update_one(
        {"workspaceId": workspace_id, "provider": "gmail"},
        {
            "$set": {
                "composioConnectionId": result["connectionId"],
                "status": "pending",
            },
            "$setOnInsert": {"workspaceId": workspace_id, "provider": "gmail"},
        },
        upsert=True,
    )

    return {"redirectUrl": result["redirectUrl"]}


@router.get("/composio/status")
async def status(
    live: bool = False, workspace_id: str = Depends(workspace_id_dep)
) -> dict:
    """Report the workspace's Gmail connection status.

    Default (`live=False`): a cheap read of the stored `connections` doc —
    no SDK call, no mutation. This is what the (app) layout gate calls on
    every navigation, so it must not auto-heal a disconnected connection
    back to active nor make a network round trip per page load.

    `live=True` (used by onboarding/settings while polling right after the
    user goes through the OAuth flow): poll the SDK and flip the stored doc
    to `active` once Composio reports it so, same as before.
    """
    db = get_db()
    connection = await db.connections.find_one({"workspaceId": workspace_id, "provider": "gmail"})
    if connection is None:
        return {"status": "none", "emailAddress": None}

    if not live:
        return {"status": connection.get("status"), "emailAddress": connection.get("emailAddress")}

    if not connection.get("composioConnectionId"):
        return {"status": "none", "emailAddress": None}

    # Every live poll is at least one Composio API call — bound it per
    # workspace, independently of the generic proxy limit.
    _throttle(_live_poll_limiter, workspace_id)

    result = composio_client.get_connection_status(connection["composioConnectionId"])
    if inspect.isawaitable(result):
        result = await result

    if result["status"] == "NOT_FOUND":
        # The connected account no longer exists in Composio — self-heal the
        # stored doc so the layout gate sends the user back through connect
        # instead of every live poll 500-ing on the dangling id.
        await db.connections.update_one(
            {"workspaceId": workspace_id, "provider": "gmail"},
            {
                "$set": {"status": "disconnected"},
                "$unset": {"composioConnectionId": ""},
            },
        )
        return {"status": "none", "emailAddress": None}

    if result["status"] == "ACTIVE":
        # The connected-account object itself carries no email address
        # (verified live) — `get_connection_status`'s `emailAddress` is
        # essentially always `None` in practice. Prefer the address already
        # stored on the doc; only when neither is known fall back to a
        # `GMAIL_GET_PROFILE` fetch (a metered Composio tool execution).
        # This keeps the one-time backfill for connections that went active
        # before this fetch existed (stored doc active, emailAddress null)
        # while making steady-state live polls a single Composio call —
        # previously the fetch ran on EVERY live poll, letting a client
        # polling at the proxy limit drive ~3x metered Composio traffic.
        email_address = result.get("emailAddress") or connection.get("emailAddress")
        if not email_address:
            fetched = composio_client.fetch_mailbox_address(
                connection["composioConnectionId"], workspace_id
            )
            if inspect.isawaitable(fetched):
                fetched = await fetched
            email_address = fetched
        update: dict = {
            "status": "active",
            "emailAddress": email_address,
            "connectedAt": datetime.now(timezone.utc),
        }
        # Enable the Gmail trigger only on the pending→active transition —
        # not on every live poll of an already-active connection (each call
        # is a Composio API write). Dropped triggers on active connections
        # are re-asserted by the fallback-sync job for subscribed workspaces.
        if connection.get("status") != "active":
            trigger_result = composio_client.ensure_gmail_trigger(
                connection["composioConnectionId"]
            )
            if inspect.isawaitable(trigger_result):
                await trigger_result
    else:
        update = {"status": str(result["status"]).lower()}

    await db.connections.update_one(
        {"workspaceId": workspace_id, "provider": "gmail"}, {"$set": update}
    )

    return {"status": update["status"], "emailAddress": update.get("emailAddress")}


@router.delete("/composio/connection")
async def disconnect(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Manually disconnect the workspace's Gmail connection: flips the stored
    `connections` doc to `disconnected`, clears `composioConnectionId` (so
    the webhook can no longer resolve this workspace by the old connection
    id — otherwise a stale/racing webhook delivery would resurrect ingestion
    for a connection the user just severed), stamps `disconnectedAt`, and
    logs an audit event. Also deletes the connected account on the Composio
    side (best-effort): leaving it alive means Composio keeps the OAuth
    grant and keeps firing (and metering) a trigger delivery for every
    inbound email on a mailbox nobody is processing anymore."""
    db = get_db()

    connection = await db.connections.find_one(
        {"workspaceId": workspace_id, "provider": "gmail"}
    )
    connection_id = (connection or {}).get("composioConnectionId")
    if connection_id:
        # Best-effort (never raises): the local status flip below must
        # succeed even when Composio is unreachable.
        delete_result = composio_client.delete_connected_account(connection_id)
        if inspect.isawaitable(delete_result):
            await delete_result

    await db.connections.update_one(
        {"workspaceId": workspace_id, "provider": "gmail"},
        {
            "$set": {"status": "disconnected", "disconnectedAt": datetime.now(timezone.utc)},
            "$unset": {"composioConnectionId": ""},
        },
    )
    await log_event(db, workspace_id, "connection.disconnected")
    return {"status": "disconnected"}
