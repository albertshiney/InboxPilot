from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app import composio_client
from app.db import get_db
from app.deps import workspace_id_dep

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
async def status(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Poll the SDK for the workspace's Gmail connection status; flips the
    stored `connections` doc to `active` once Composio reports it so."""
    db = get_db()
    connection = await db.connections.find_one({"workspaceId": workspace_id, "provider": "gmail"})
    if connection is None or not connection.get("composioConnectionId"):
        return {"status": "none", "emailAddress": None}

    result = composio_client.get_connection_status(connection["composioConnectionId"])

    if result["status"] == "ACTIVE":
        update: dict = {
            "status": "active",
            "emailAddress": result["emailAddress"],
            "connectedAt": datetime.now(timezone.utc),
        }
    else:
        update = {"status": str(result["status"]).lower()}

    await db.connections.update_one(
        {"workspaceId": workspace_id, "provider": "gmail"}, {"$set": update}
    )

    return {"status": update["status"], "emailAddress": update.get("emailAddress")}
