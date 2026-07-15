"""Pydantic models for InboxPilot's Mongo collections (spec §3).

These are the single source of truth for field names used by every backend
task after this one. Workspace ids are always compared/stored as `str` even
though the `workspaces` collection itself is keyed by a NextAuth-issued
Mongo ObjectId (see `collections.workspace_filter`) — every other collection
stores `workspaceId` as that plain string.

Note on `Message.from_`: Python's `from` is a keyword, so the sender field
is declared as `from_` with a pydantic alias of `"from"` (`populate_by_name
= True` lets callers construct the model with either name; the stored/wire
key is `"from"`, produced via `model_dump(by_alias=True)`).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ThreadStatus = Literal["needs_review", "auto_sent", "sent", "ignored", "archived"]
DraftStatus = Literal["pending", "approved_sent", "auto_sent", "edited_sent", "discarded"]
SentBy = Literal["customer", "ai_auto", "human_approved"]
Direction = Literal["inbound", "outbound"]
KbDocumentStatus = Literal["processing", "ready", "failed"]


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
    stripeCustomerId: str | None = None
    plan: str | None = None
    subscriptionStatus: str = "none"
    trialEndsAt: datetime | None = None
    usage: Usage = Field(default_factory=Usage)
    createdAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Connection(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    provider: Literal["gmail"] = "gmail"
    composioConnectionId: str | None = None
    emailAddress: str | None = None
    status: str
    connectedAt: datetime | None = None

    model_config = {"populate_by_name": True}


class Thread(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    gmailThreadId: str
    subject: str
    customerEmail: str
    customerName: str | None = None
    status: ThreadStatus = "needs_review"
    category: str | None = None
    lastMessageAt: datetime
    snippet: str

    model_config = {"populate_by_name": True}


class Message(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    threadId: str
    gmailMessageId: str
    direction: Direction
    from_: str = Field(alias="from")
    to: str
    bodyText: str
    bodyHtml: str | None = None
    sentBy: SentBy
    receivedAt: datetime

    model_config = {"populate_by_name": True}


class Draft(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    threadId: str
    messageId: str
    reply: str
    confidence: int
    category: str
    requiresHuman: bool
    reasoning: str
    sourcesUsed: list[str] = Field(default_factory=list)
    status: DraftStatus = "pending"
    editedReply: str | None = None
    createdAt: datetime
    resolvedAt: datetime | None = None
    resolvedBy: str | None = None

    model_config = {"populate_by_name": True}


class KbDocument(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    filename: str
    type: str
    sizeBytes: int
    chunkCount: int = 0
    status: KbDocumentStatus = "processing"
    createdAt: datetime

    model_config = {"populate_by_name": True}


class KbChunk(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    documentId: str
    documentName: str
    text: str
    embedding: list[float]
    order: int

    model_config = {"populate_by_name": True}


class Event(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    workspaceId: str
    type: str
    meta: dict[str, Any] | None = None
    ts: datetime

    model_config = {"populate_by_name": True}
