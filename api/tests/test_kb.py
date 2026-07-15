import io
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_upload_neither_file_nor_text_returns_400(client, mock_db):
    """Test that upload fails with 400 when neither file nor text is provided."""
    r = await client.post("/kb/upload", headers=HEADERS, data={})
    assert r.status_code == 400
    assert "Provide a file or pasted text" in r.json()["detail"]

    # Verify no document was created
    docs = await mock_db.kb_documents.find().to_list(None)
    assert len(docs) == 0


async def test_upload_text_without_title_returns_400(client, mock_db):
    """Test that upload fails with 400 when text is provided without a title."""
    r = await client.post(
        "/kb/upload",
        headers=HEADERS,
        data={"text": "Some content without a title"},
    )
    assert r.status_code == 400
    assert "title is required with pasted text" in r.json()["detail"]

    # Verify no document was created
    docs = await mock_db.kb_documents.find().to_list(None)
    assert len(docs) == 0


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


async def test_delete_kb_document_respects_workspace_scope(client, mock_db):
    """Test that DELETE /kb/{doc_id} cannot delete a document from a different workspace."""
    # Upload a document in ws1
    files = {"file": ("a.txt", io.BytesIO(b"content a"), "text/plain")}
    r = await client.post("/kb/upload", headers=HEADERS, files=files)
    doc_id = r.json()["id"]

    # Verify document and chunks exist in ws1
    doc = await mock_db.kb_documents.find_one({"_id": doc_id})
    assert doc is not None
    chunks = await mock_db.kb_chunks.find({"documentId": doc_id}).to_list(None)
    assert len(chunks) > 0

    # Try to delete with ws2 headers
    other_headers = {**HEADERS, "X-Workspace-Id": "ws2"}
    r = await client.delete(f"/kb/{doc_id}", headers=other_headers)
    assert r.status_code == 200  # The endpoint returns 200 but deletes 0 documents

    # Verify document and chunks still exist in ws1 (not deleted)
    doc = await mock_db.kb_documents.find_one({"_id": doc_id})
    assert doc is not None
    chunks = await mock_db.kb_chunks.find({"documentId": doc_id}).to_list(None)
    assert len(chunks) > 0


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


async def test_embed_texts_batches_api_calls_for_150_texts(monkeypatch):
    """Test that embed_texts with 150 texts calls the embeddings API twice (batch size 100)."""
    from app import llm

    # First, undo the autouse fixture that patches embed_texts
    import inspect
    original_embed_texts = kb.embed_texts.__wrapped__ if hasattr(kb.embed_texts, '__wrapped__') else None

    # If we can't get the original, let's just re-import it
    if original_embed_texts is None:
        from importlib import reload
        from app import kb as kb_module
        reload(kb_module)

    call_sizes = []

    class MockEmbedding:
        def __init__(self, idx):
            self.embedding = [float(idx % 7) / 7 for _ in range(8)]

    class MockResponse:
        def __init__(self, count):
            self.data = [MockEmbedding(i) for i in range(count)]

    async def mock_create(model, input):
        call_sizes.append(len(input))
        return MockResponse(len(input))

    class MockEmbeddings:
        async def create(self, model, input):
            return await mock_create(model, input)

    class MockClient:
        def __init__(self):
            self.embeddings = MockEmbeddings()

    def fake_get_openai():
        return MockClient()

    # Patch get_openai
    llm.reset_clients()
    monkeypatch.setattr(llm, "get_openai", fake_get_openai)
    monkeypatch.setattr(kb_module, "get_openai", fake_get_openai)

    texts = [f"text {i}" for i in range(150)]
    embeddings = await kb_module.embed_texts(texts)

    # Verify API was called twice (batch size 100)
    assert len(call_sizes) == 2, f"Expected 2 API calls, got {len(call_sizes)}"
    assert call_sizes == [100, 50]
    assert len(embeddings) == 150
