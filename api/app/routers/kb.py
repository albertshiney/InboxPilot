import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app import kb
from app.collections import workspace_filter
from app.db import get_db
from app.deps import workspace_id_dep
from app.events import log_event

router = APIRouter(prefix="/kb", tags=["kb"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
MAX_DOCUMENTS_PER_WORKSPACE = 50

# Per-workspace upload throttle: at most UPLOAD_MAX_PER_WINDOW uploads per
# UPLOAD_WINDOW_SECONDS. Every upload triggers embedding calls (real AI
# spend), and the MAX_DOCUMENTS_PER_WORKSPACE cap alone doesn't bound spend —
# a delete-and-reupload loop stays under the cap forever. In-process sliding
# window keyed by workspace id, mirroring the regeneration throttle in
# threads.py. Safe under asyncio: no awaits between the check and the append.
UPLOAD_WINDOW_SECONDS = 3600
UPLOAD_MAX_PER_WINDOW = 20
_upload_hits: dict[str, deque] = defaultdict(deque)


def reset_upload_throttle() -> None:
    """Test-only hook: clears all upload throttle state so tests don't leak
    hit counts into each other."""
    _upload_hits.clear()


def _check_upload_throttle(workspace_id: str) -> None:
    """Raise 429 once a workspace exceeds UPLOAD_MAX_PER_WINDOW uploads
    within a trailing UPLOAD_WINDOW_SECONDS window; otherwise record this
    upload. No awaits between the check and the append."""
    now = time.monotonic()
    hits = _upload_hits[workspace_id]

    while hits and now - hits[0] > UPLOAD_WINDOW_SECONDS:
        hits.popleft()

    if len(hits) >= UPLOAD_MAX_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many uploads, slow down",
        )

    hits.append(now)


def _serialize(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "workspaceId": doc["workspaceId"],
        "filename": doc["filename"],
        "type": doc["type"],
        "sizeBytes": doc["sizeBytes"],
        "chunkCount": doc["chunkCount"],
        "status": doc["status"],
        "createdAt": doc["createdAt"],
    }


@router.get("")
async def list_documents(workspace_id: str = Depends(workspace_id_dep)) -> list[dict]:
    db = get_db()
    docs = await db.kb_documents.find({"workspaceId": workspace_id}).sort("createdAt", -1).to_list(None)
    return [_serialize(d) for d in docs]


@router.post("/upload")
async def upload(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    title: str | None = Form(default=None),
    workspace_id: str = Depends(workspace_id_dep),
) -> dict:
    db = get_db()

    # Validate that either file or text is provided
    if file is None and not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a file or pasted text",
        )

    # Validate that pasted text has a title
    if file is None and text and not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="title is required with pasted text",
        )

    # Uploading knowledge consumes AI spend (embeddings) — gate on an active
    # subscription, same as the drafting routes.
    workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
    subscription_status = (workspace or {}).get("subscriptionStatus") or "none"
    if subscription_status not in ("active", "trialing"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="subscription required"
        )

    # Per-workspace document cap.
    doc_count = await db.kb_documents.count_documents({"workspaceId": workspace_id})
    if doc_count >= MAX_DOCUMENTS_PER_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="document limit reached",
        )

    # Per-workspace burst throttle (raises 429 on exceed). Checked after the
    # cheap validations so rejected requests don't consume throttle budget.
    _check_upload_throttle(workspace_id)

    if file is not None:
        filename = file.filename or "upload"
        source_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
        # Reject disallowed extensions BEFORE reading the file body.
        if source_type not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported file type"
            )
        # Read at most MAX_UPLOAD_BYTES + 1 so an oversized file is detected
        # without buffering the whole thing.
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="file too large",
            )
        size_bytes = len(content)
    else:
        if len(text or "") > MAX_TEXT_CHARS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="file too large",
            )
        filename = title or "Pasted text"
        content = (text or "").encode("utf-8")
        source_type = "text"
        size_bytes = len(content)

    doc_id = str(ObjectId())
    doc = {
        "_id": doc_id,
        "workspaceId": workspace_id,
        "filename": filename,
        "type": source_type,
        "sizeBytes": size_bytes,
        "chunkCount": 0,
        "status": "processing",
        "createdAt": datetime.now(timezone.utc),
    }
    await db.kb_documents.insert_one(doc)

    try:
        if file is not None:
            extracted = kb.extract_text(filename, content)
            # A file within MAX_UPLOAD_BYTES can still decompress to far more
            # text (PDF/DOCX are compressed formats) — enforce the same cap as
            # pasted text so a crafted file can't buy unbounded embedding
            # spend or exhaust memory. Raising here lands in the except below,
            # marking the document "failed" before any embedding call.
            if len(extracted) > MAX_TEXT_CHARS:
                raise ValueError("extracted text exceeds MAX_TEXT_CHARS")
        else:
            extracted = text or ""

        chunks = kb.chunk_text(extracted)
        if not chunks:
            raise ValueError("no extractable text content")

        embeddings = await kb.embed_texts(chunks)

        chunk_docs = [
            {
                "workspaceId": workspace_id,
                "documentId": doc_id,
                "documentName": filename,
                "text": chunk,
                "embedding": embedding,
                "order": i,
            }
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        await db.kb_chunks.insert_many(chunk_docs)

        update = {"status": "ready", "chunkCount": len(chunk_docs)}
        await db.kb_documents.update_one({"_id": doc_id}, {"$set": update})
        doc.update(update)
        await log_event(db, workspace_id, "kb.document_uploaded", {"documentId": doc_id, "filename": filename})
    except Exception:
        update = {"status": "failed", "chunkCount": 0}
        await db.kb_documents.update_one({"_id": doc_id}, {"$set": update})
        doc.update(update)
        await log_event(db, workspace_id, "kb.document_failed", {"documentId": doc_id, "filename": filename})

    return _serialize(doc)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, workspace_id: str = Depends(workspace_id_dep)) -> dict:
    db = get_db()
    await db.kb_documents.delete_one({"_id": doc_id, "workspaceId": workspace_id})
    await db.kb_chunks.delete_many({"documentId": doc_id, "workspaceId": workspace_id})
    return {"ok": True}
