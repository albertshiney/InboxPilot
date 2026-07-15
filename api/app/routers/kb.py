from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app import kb
from app.db import get_db
from app.deps import workspace_id_dep
from app.events import log_event

router = APIRouter(prefix="/kb", tags=["kb"])


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

    if file is not None:
        filename = file.filename or "upload"
        content = await file.read()
        source_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
        size_bytes = len(content)
    else:
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
