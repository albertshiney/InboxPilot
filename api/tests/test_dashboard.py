"""Tests for GET /dashboard/stats: period-windowed event counts, live
needs_review count, and the oldest-10 attention list."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from tests.conftest import HEADERS

WORKSPACE_ID = "ws1"
OTHER_WORKSPACE_ID = "ws2"


async def _log_event(mock_db, workspace_id, type_, ts, meta=None):
    await mock_db.events.insert_one(
        {"workspaceId": workspace_id, "type": type_, "meta": meta, "ts": ts}
    )


async def _make_thread(mock_db, workspace_id, **overrides):
    doc = {
        "_id": ObjectId(),
        "workspaceId": workspace_id,
        "gmailThreadId": f"gt-{ObjectId()}",
        "subject": "Where is my order?",
        "customerEmail": "customer@example.com",
        "customerName": "Cus Tomer",
        "status": "needs_review",
        "category": "shipping",
        "lastMessageAt": datetime.now(timezone.utc),
        "snippet": "Where is my order?",
    }
    doc.update(overrides)
    result = await mock_db.threads.insert_one(doc)
    return str(result.inserted_id)


async def _make_draft(mock_db, thread_id, **overrides):
    doc = {
        "threadId": thread_id,
        "messageId": None,
        "reply": "Your order ships within 2 days.",
        "confidence": 77,
        "category": "shipping",
        "requiresHuman": False,
        "reasoning": "found in KB",
        "sourcesUsed": [],
        "status": "pending",
        "editedReply": None,
        "createdAt": datetime.now(timezone.utc),
        "resolvedAt": None,
        "resolvedBy": None,
    }
    doc.update(overrides)
    await mock_db.drafts.insert_one(doc)


@pytest.mark.asyncio
async def test_stats_today_only_counts_events_since_local_midnight(client, mock_db):
    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Inside today's window.
    await _log_event(mock_db, WORKSPACE_ID, "email_received", today_midnight + timedelta(hours=1))
    await _log_event(mock_db, WORKSPACE_ID, "draft_created", today_midnight + timedelta(hours=1))
    await _log_event(mock_db, WORKSPACE_ID, "auto_sent", today_midnight + timedelta(hours=1))

    # Before today (yesterday) - must be excluded.
    await _log_event(mock_db, WORKSPACE_ID, "email_received", today_midnight - timedelta(hours=1))

    res = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["emailsReceived"] == 1
    assert data["draftsCreated"] == 1
    assert data["autoSent"] == 1
    assert data["autoSentPct"] == 100


@pytest.mark.asyncio
async def test_stats_7d_and_30d_windows_filter_correctly(client, mock_db):
    now = datetime.now(timezone.utc)

    await _log_event(mock_db, WORKSPACE_ID, "email_received", now - timedelta(days=3))
    await _log_event(mock_db, WORKSPACE_ID, "email_received", now - timedelta(days=10))
    await _log_event(mock_db, WORKSPACE_ID, "email_received", now - timedelta(days=29))
    await _log_event(mock_db, WORKSPACE_ID, "email_received", now - timedelta(days=40))

    res_7d = await client.get("/dashboard/stats", params={"period": "7d"}, headers=HEADERS)
    assert res_7d.json()["emailsReceived"] == 1

    res_30d = await client.get("/dashboard/stats", params={"period": "30d"}, headers=HEADERS)
    assert res_30d.json()["emailsReceived"] == 3


@pytest.mark.asyncio
async def test_auto_sent_pct_rounds_and_zero_when_no_emails(client, mock_db):
    now = datetime.now(timezone.utc)

    res_none = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    assert res_none.json()["autoSentPct"] == 0
    assert res_none.json()["emailsReceived"] == 0

    for _ in range(3):
        await _log_event(mock_db, WORKSPACE_ID, "email_received", now)
    await _log_event(mock_db, WORKSPACE_ID, "auto_sent", now)

    res = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    data = res.json()
    assert data["emailsReceived"] == 3
    assert data["autoSent"] == 1
    # 1/3 = 33.33...% rounds to 33
    assert data["autoSentPct"] == 33


@pytest.mark.asyncio
async def test_needs_review_is_a_live_count_not_period_scoped(client, mock_db):
    now = datetime.now(timezone.utc)
    await _make_thread(mock_db, WORKSPACE_ID, status="needs_review", lastMessageAt=now - timedelta(days=90))
    await _make_thread(mock_db, WORKSPACE_ID, status="needs_review", lastMessageAt=now)
    await _make_thread(mock_db, WORKSPACE_ID, status="sent", lastMessageAt=now)

    res = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    assert res.json()["needsReview"] == 2


@pytest.mark.asyncio
async def test_events_and_threads_scoped_to_workspace(client, mock_db):
    now = datetime.now(timezone.utc)
    await _log_event(mock_db, WORKSPACE_ID, "email_received", now)
    await _log_event(mock_db, OTHER_WORKSPACE_ID, "email_received", now)
    await _make_thread(mock_db, WORKSPACE_ID, status="needs_review")
    await _make_thread(mock_db, OTHER_WORKSPACE_ID, status="needs_review")

    res = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    data = res.json()
    assert data["emailsReceived"] == 1
    assert data["needsReview"] == 1


@pytest.mark.asyncio
async def test_attention_list_capped_at_10_oldest_needs_review_with_draft_summary(
    client, mock_db
):
    now = datetime.now(timezone.utc)
    thread_ids = []
    for i in range(12):
        tid = await _make_thread(
            mock_db,
            WORKSPACE_ID,
            status="needs_review",
            lastMessageAt=now - timedelta(hours=i),
            subject=f"Thread {i}",
            customerEmail=f"c{i}@example.com",
        )
        await _make_draft(mock_db, tid, confidence=50 + i, category="billing")
        thread_ids.append(tid)

    # A non-needs_review thread should never appear.
    sent_id = await _make_thread(mock_db, WORKSPACE_ID, status="sent")
    await _make_draft(mock_db, sent_id, status="approved_sent")

    res = await client.get("/dashboard/stats", params={"period": "today"}, headers=HEADERS)
    data = res.json()
    attention = data["attention"]
    assert len(attention) == 10

    # Oldest lastMessageAt = i=11 down to i=2 (10 oldest of the 12).
    expected_oldest_first = [thread_ids[i] for i in range(11, 1, -1)]
    assert [row["id"] for row in attention] == expected_oldest_first

    row = attention[0]
    assert row["customerEmail"] == "c11@example.com"
    assert row["subject"] == "Thread 11"
    assert row["category"] == "billing"
    assert row["confidence"] == 61
    assert "waitingSinceIso" in row


@pytest.mark.asyncio
async def test_stats_requires_workspace_header(client, mock_db):
    res = await client.get("/dashboard/stats", params={"period": "today"})
    assert res.status_code == 401
