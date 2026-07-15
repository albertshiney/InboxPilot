import io

import pytest

from app import kb
from .conftest import HEADERS


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_short_text_returns_one_chunk():
    text = "Hello world, this is a short document."
    chunks = kb.chunk_text(text)
    assert chunks == [text]


def test_chunk_text_long_text_returns_multiple_overlapping_chunks():
    words = [f"word{i}" for i in range(3000)]
    text = " ".join(words)
    chunks = kb.chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.strip() != ""

    # Consecutive chunks should share some trailing/leading text (the
    # overlap window).
    for a, b in zip(chunks, chunks[1:]):
        overlap = set(a.split()) & set(b.split())
        assert overlap, "expected overlap between consecutive chunks"


def test_chunk_text_never_returns_empty_strings():
    chunks = kb.chunk_text("   ")
    assert all(c != "" for c in chunks)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


def test_extract_text_txt_roundtrip():
    content = "Plain text content.\nSecond line.".encode("utf-8")
    assert kb.extract_text("notes.txt", content) == "Plain text content.\nSecond line."


def test_extract_text_md_roundtrip():
    content = "# Heading\nBody".encode("utf-8")
    assert kb.extract_text("notes.md", content) == "# Heading\nBody"


def test_extract_text_unsupported_extension_raises():
    with pytest.raises(ValueError):
        kb.extract_text("notes.exe", b"binary junk")


# ---------------------------------------------------------------------------
# Upload route (embeddings + vector search monkeypatched)
# ---------------------------------------------------------------------------


def _fake_embedding(seed: int) -> list[float]:
    return [float((seed + i) % 7) / 7 for i in range(8)]


async def _fake_embed_texts(texts):
    return [_fake_embedding(i) for i in range(len(texts))]


@pytest.fixture(autouse=True)
def _patch_embeddings(monkeypatch):
    monkeypatch.setattr(kb, "embed_texts", _fake_embed_texts)


async def test_upload_file_creates_document_and_chunks(client, mock_db):
    files = {"file": ("notes.txt", io.BytesIO(b"hello world " * 500), "text/plain")}
    r = await client.post("/kb/upload", headers=HEADERS, files=files)
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "ready"
    assert body["filename"] == "notes.txt"
    assert body["chunkCount"] > 0

    doc = await mock_db.kb_documents.find_one({"_id": body["id"]})
    assert doc is not None
    assert doc["status"] == "ready"
    assert doc["chunkCount"] == body["chunkCount"]

    chunks = await mock_db.kb_chunks.find({"documentId": body["id"]}).to_list(None)
    assert len(chunks) == body["chunkCount"]
    for chunk in chunks:
        assert chunk["workspaceId"] == "ws1"
        assert chunk["documentName"] == "notes.txt"
        assert "embedding" in chunk


async def test_upload_paste_text_creates_document(client, mock_db):
    r = await client.post(
        "/kb/upload",
        headers=HEADERS,
        data={"text": "Some pasted knowledge base content.", "title": "Pasted Notes"},
    )
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "ready"
    assert body["filename"] == "Pasted Notes"
    assert body["chunkCount"] == 1

    chunks = await mock_db.kb_chunks.find({"documentId": body["id"]}).to_list(None)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Some pasted knowledge base content."


async def test_upload_unsupported_file_marks_document_failed(client, mock_db):
    files = {"file": ("virus.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    r = await client.post("/kb/upload", headers=HEADERS, files=files)
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "failed"
    assert body["chunkCount"] == 0

    chunks = await mock_db.kb_chunks.find({"documentId": body["id"]}).to_list(None)
    assert chunks == []


async def test_list_kb_documents(client, mock_db):
    files = {"file": ("a.txt", io.BytesIO(b"content a"), "text/plain")}
    await client.post("/kb/upload", headers=HEADERS, files=files)

    r = await client.get("/kb", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["filename"] == "a.txt"


async def test_delete_kb_document_removes_doc_and_chunks(client, mock_db):
    files = {"file": ("a.txt", io.BytesIO(b"content a"), "text/plain")}
    r = await client.post("/kb/upload", headers=HEADERS, files=files)
    doc_id = r.json()["id"]

    r = await client.delete(f"/kb/{doc_id}", headers=HEADERS)
    assert r.status_code == 200

    doc = await mock_db.kb_documents.find_one({"_id": doc_id})
    assert doc is None
    chunks = await mock_db.kb_chunks.find({"documentId": doc_id}).to_list(None)
    assert chunks == []


async def test_upload_scoped_to_workspace_from_header(client, mock_db):
    files = {"file": ("a.txt", io.BytesIO(b"content a"), "text/plain")}
    await client.post("/kb/upload", headers=HEADERS, files=files)

    other_headers = {**HEADERS, "X-Workspace-Id": "ws2"}
    r = await client.get("/kb", headers=other_headers)
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


async def test_retrieve_respects_floor(mock_db, monkeypatch):
    async def fake_vector_search(db, workspace_id, embedding, k):
        return [
            {"text": "high score chunk", "score": 0.9, "documentName": "doc-a.txt"},
            {"text": "low score chunk", "score": 0.3, "documentName": "doc-b.txt"},
        ]

    monkeypatch.setattr(kb, "_vector_search", fake_vector_search)
    monkeypatch.setattr(kb, "embed_texts", _fake_embed_texts)

    results = await kb.retrieve(mock_db, "ws1", "some query", k=8, floor=0.45)

    assert len(results) == 1
    assert results[0]["text"] == "high score chunk"
    assert results[0]["score"] == 0.9
    assert results[0]["documentName"] == "doc-a.txt"
