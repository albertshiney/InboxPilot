import inspect
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app import composio_client
from app.db import get_db
from app.deps import workspace_id_dep
from app.events import log_event

router = APIRouter()


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

    result = composio_client.get_connection_status(connection["composioConnectionId"])
    if inspect.isawaitable(result):
        result = await result

    if result["status"] == "ACTIVE":
        update: dict = {
            "status": "active",
            "emailAddress": result["emailAddress"],
            "connectedAt": datetime.now(timezone.utc),
        }
        trigger_result = composio_client.ensure_gmail_trigger(connection["composioConnectionId"])
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
    logs an audit event. Does not revoke the underlying Composio OAuth
    grant — this is a local status flip so the (app) layout gate sends the
    user back to onboarding."""
    db = get_db()
    await db.connections.update_one(
        {"workspaceId": workspace_id, "provider": "gmail"},
        {
            "$set": {"status": "disconnected", "disconnectedAt": datetime.now(timezone.utc)},
            "$unset": {"composioConnectionId": ""},
        },
    )
    await log_event(db, workspace_id, "connection.disconnected")
    return {"status": "disconnected"}
