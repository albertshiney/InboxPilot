"""Pydantic models for InboxPilot's Mongo collections (spec §3).

These are the single source of truth for field names used by every backend
task after this one. Workspace ids are always compared/stored as `str` even
though the `workspaces` collection itself is keyed by a NextAuth-issued
Mongo ObjectId (see `collections.workspace_filter`) — every other collection
stores `workspaceId` as that plain string.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ThreadStatus = Literal["needs_review", "auto_sent", "sent", "ignored", "archived"]
DraftStatus = Literal["pending", "approved_sent", "auto_sent", "edited_sent", "discarded"]
SentBy = Literal["customer", "ai_auto", "human_approved"]


class WorkspaceSettings(BaseModel):
    autopilot: bool = False
    confidenceThreshold: int = 85
    tone: str = "friendly"
    signature: str = ""
    blockedCategories: list[str] = Field(default_factory=lambda: ["refund"])
    customInstructions: str = ""


class Usage(BaseModel):
    emailsProcessedThisMonth: int = 0


class Workspace(BaseModel):
    """Mirrors `defaultWorkspace()` in web/auth.ts field-for-field."""

    id: str | None = Field(default=None, alias="_id")
    name: str = "My workspace"
    ownerId: str | None = None
    settings: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    plan: str | None = None
    subscriptionStatus: str = "none"
    stripeCustomerId: str | None = None
    trialEndsAt: datetime | None = None
    usage: Usage = Field(default_factory=Usage)
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Connection(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    provider: str = "gmail"
    emailAddress: str
    status: str
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Thread(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    gmailThreadId: str | None = None
    subject: str | None = None
    customerEmail: str | None = None
    status: ThreadStatus = "needs_review"
    lastMessageAt: datetime | None = None
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Message(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    threadId: str
    gmailMessageId: str
    sentBy: SentBy
    from_: str | None = Field(default=None, alias="from")
    to: list[str] | None = None
    body: str | None = None
    receivedAt: datetime | None = None
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Draft(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    threadId: str
    body: str
    confidence: float | None = None
    status: DraftStatus = "pending"
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"populate_by_name": True}


class KbDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    filename: str
    status: str = "processing"
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class KbChunk(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    documentId: str
    text: str
    embedding: list[float] | None = None
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Event(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    type: str
    meta: dict[str, Any] | None = None
    ts: datetime

    model_config = {"populate_by_name": True}
