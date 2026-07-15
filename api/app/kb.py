"""Knowledge-base pipeline: extract text, chunk, embed, and retrieve via
Atlas `$vectorSearch`.

`_vector_search` is the only piece that talks to Mongo's `$vectorSearch`
aggregation stage, which Atlas alone can execute (mongomock can't), so
tests monkeypatch it directly rather than exercising the real aggregation.
"""

import io
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from .config import get_settings
from .llm import get_openai

CHUNK_TOKENS = 600
OVERLAP_TOKENS = 80
CHARS_PER_TOKEN = 4
EMBED_BATCH_SIZE = 100
VECTOR_INDEX_NAME = "kb_chunks_vector"


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded file's bytes based on its
    extension. Raises `ValueError` for unsupported extensions."""
    lower = filename.lower()

    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if lower.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)

    if lower.endswith(".txt") or lower.endswith(".md"):
        return content.decode("utf-8")

    raise ValueError(f"unsupported file type: {filename}")


def chunk_text(
    text: str, chunk_tokens: int = CHUNK_TOKENS, overlap_tokens: int = OVERLAP_TOKENS
) -> list[str]:
    """Sliding-window chunker over whitespace-split words. Token counts are
    approximated as `len(text)//4`. Never returns empty strings."""
    words = text.split()
    if not words:
        return []

    chunk_words = max(1, chunk_tokens * CHARS_PER_TOKEN // 5)
    overlap_words = max(0, overlap_tokens * CHARS_PER_TOKEN // 5)
    step = max(1, chunk_words - overlap_words)

    chunks: list[str] = []
    start = 0
    while start < len(words):
        window = words[start : start + chunk_words]
        chunk = " ".join(window).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
        start += step

    return chunks


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via OpenAI, batched at `EMBED_BATCH_SIZE`."""
    settings = get_settings()
    client = get_openai()

    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        response = await client.embeddings.create(model=settings.embed_model, input=batch)
        embeddings.extend(item.embedding for item in response.data)

    return embeddings


async def _vector_search(
    db: AsyncIOMotorDatabase, workspace_id: str, embedding: list[float], k: int
) -> list[dict[str, Any]]:
    """Run the Atlas `$vectorSearch` aggregation on `kb_chunks`. Requires a
    real Atlas cluster with the `kb_chunks_vector` index (see
    `api/scripts/create_vector_index.md`) — mongomock cannot execute this,
    so tests monkeypatch this function."""
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": 200,
                "limit": k,
                "filter": {"workspaceId": workspace_id},
            }
        },
        {
            "$project": {
                "text": 1,
                "documentName": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = db.kb_chunks.aggregate(pipeline)
    return await cursor.to_list(None)


async def retrieve(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    query: str,
    k: int = 8,
    floor: float = 0.45,
) -> list[dict[str, Any]]:
    """Embed `query`, run Atlas vector search scoped to the workspace, and
    drop any result scoring below `floor`."""
    [embedding] = await embed_texts([query])
    results = await _vector_search(db, workspace_id, embedding, k)
    return [
        {"text": r["text"], "score": r["score"], "documentName": r["documentName"]}
        for r in results
        if r["score"] >= floor
    ]
