from typing import Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.collections import workspace_filter
from app.db import get_db
from app.deps import workspace_id_dep
from app.models import Workspace

router = APIRouter()

MIN_CONFIDENCE_THRESHOLD = 50
MAX_CONFIDENCE_THRESHOLD = 99


class SettingsPatchFields(BaseModel):
    """Partial `WorkspaceSettings` — every field optional so PATCH can send
    just the keys it wants to change. `extra="forbid"` rejects unknown
    settings keys (422) instead of letting them merge silently into the
    stored doc; `confidenceThreshold` typed as `int | None` so a string
    value fails validation (422) at the boundary instead of blowing up the
    clamp comparison later."""

    autopilot: bool | None = None
    confidenceThreshold: int | None = None
    tone: str | None = None
    signature: str | None = None
    blockedCategories: list[str] | None = None
    customInstructions: str | None = None

    model_config = {"extra": "forbid"}


class SettingsPatch(BaseModel):
    name: str | None = None
    settings: SettingsPatchFields | None = None


def _default_workspace_doc(workspace_id: str) -> dict:
    """Same shape as `defaultWorkspace()` in web/auth.ts, minus `_id` (the
    caller sets that from `workspace_filter`) and `createdAt` (NextAuth sets
    that on its own bootstrap path; this lazily-created doc never had one).
    Derived from `Workspace`'s own defaults so the two bootstrap paths can't
    drift apart."""
    return Workspace().model_dump(exclude={"id", "createdAt"})


async def _get_or_create_workspace(db: AsyncIOMotorDatabase, workspace_id: str) -> dict:
    filt = workspace_filter(workspace_id)
    doc = await db.workspaces.find_one(filt)
    if doc is None:
        doc = _default_workspace_doc(workspace_id)
        doc["_id"] = filt["_id"]
        await db.workspaces.insert_one(doc)
    return doc


async def _get_connection(db: AsyncIOMotorDatabase, workspace_id: str) -> dict | None:
    conn = await db.connections.find_one({"workspaceId": workspace_id, "provider": "gmail"})
    if conn is None:
        return None
    return {"emailAddress": conn["emailAddress"], "status": conn["status"]}


def _clamp_confidence_threshold(value: int) -> int:
    return max(MIN_CONFIDENCE_THRESHOLD, min(MAX_CONFIDENCE_THRESHOLD, value))


def _serialize(doc: dict, connection: dict | None) -> dict:
    settings = dict(doc.get("settings") or {})
    return {
        "name": doc.get("name", "My workspace"),
        "settings": settings,
        "plan": doc.get("plan"),
        "subscriptionStatus": doc.get("subscriptionStatus", "none"),
        "trialEndsAt": doc.get("trialEndsAt"),
        "usage": doc.get("usage") or {"emailsProcessedThisMonth": 0},
        "connection": connection,
    }


@router.get("/settings")
async def get_settings(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    db = get_db()
    doc = await _get_or_create_workspace(db, workspace_id)
    connection = await _get_connection(db, workspace_id)
    return _serialize(doc, connection)


@router.patch("/settings")
async def patch_settings(
    patch: SettingsPatch, workspace_id: str = Depends(workspace_id_dep)
) -> dict:
    db = get_db()
    doc = await _get_or_create_workspace(db, workspace_id)

    update: dict[str, Any] = {}

    if patch.name is not None:
        update["name"] = patch.name

    if patch.settings is not None:
        merged = dict(doc.get("settings") or {})
        merged.update(patch.settings.model_dump(exclude_unset=True))
        if "confidenceThreshold" in merged:
            merged["confidenceThreshold"] = _clamp_confidence_threshold(
                merged["confidenceThreshold"]
            )
        update["settings"] = merged

    if update:
        filt = workspace_filter(workspace_id)
        await db.workspaces.update_one(filt, {"$set": update})
        doc.update(update)

    connection = await _get_connection(db, workspace_id)
    return _serialize(doc, connection)
