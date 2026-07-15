from datetime import datetime

from app.events import log_event


async def test_log_event_writes_doc_with_ts(mock_db):
    await log_event(mock_db, "ws1", "thread.classified", meta={"category": "refund"})

    doc = await mock_db.events.find_one({"workspaceId": "ws1"})
    assert doc is not None
    assert doc["workspaceId"] == "ws1"
    assert doc["type"] == "thread.classified"
    assert doc["meta"] == {"category": "refund"}
    assert isinstance(doc["ts"], datetime)


async def test_log_event_defaults_meta_to_none(mock_db):
    await log_event(mock_db, "ws1", "settings.updated")

    doc = await mock_db.events.find_one({"workspaceId": "ws1", "type": "settings.updated"})
    assert doc is not None
    assert doc["meta"] is None
