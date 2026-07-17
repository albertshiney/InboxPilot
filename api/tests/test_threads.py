"""Tests for the threads API: list/detail/approve/regenerate/discard."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from app.draft import DraftResult
from tests.conftest import HEADERS


WORKSPACE_ID = "ws1"


@pytest.fixture(autouse=True)
def _reset_regen_throttle():
    # The regenerate route carries a process-global per-workspace throttle;
    # reset it between tests so hit counts don't leak across tests.
    from app.routers import threads as threads_router

    threads_router.reset_regen_throttle()
    yield
    threads_router.reset_regen_throttle()


async def _make_workspace(mock_db, **overrides):
    settings = dict(
        autopilot=False,
        confidenceThreshold=85,
        tone="friendly",
        signature="- Support",
        blockedCategories=["refund"],
        customInstructions="",
    )
    settings.update(overrides.pop("settings", {}))
    doc = {
        "_id": WORKSPACE_ID,
        "name": "Acme Co",
        "settings": settings,
        "usage": {"emailsProcessedThisMonth": 0},
        "plan": "pro",
        "subscriptionStatus": "active",
    }
    doc.update(overrides)
    await mock_db.workspaces.insert_one(doc)
    return WORKSPACE_ID


async def _make_thread(mock_db, workspace_id, **overrides):
    doc = {
        "_id": ObjectId(),
        "workspaceId": workspace_id,
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "customerEmail": "customer@example.com",
        "customerName": "Cus Tomer",
        "status": "needs_review",
        "category": "support_request",
        "lastMessageAt": datetime.now(timezone.utc),
        "snippet": "Where is my order?",
    }
    doc.update(overrides)
    result = await mock_db.threads.insert_one(doc)
    return str(result.inserted_id)


async def _make_message(mock_db, thread_id, **overrides):
    doc = {
        "threadId": thread_id,
        "gmailMessageId": f"gm-{ObjectId()}",
        "direction": "inbound",
        "from": "customer@example.com",
        "to": "support@ourcompany.com",
        "bodyText": "Hi, when will my order arrive?",
        "bodyHtml": None,
        "sentBy": "customer",
        "receivedAt": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    result = await mock_db.messages.insert_one(doc)
    return str(result.inserted_id)


async def _make_draft(mock_db, thread_id, message_id, **overrides):
    doc = {
        "threadId": thread_id,
        "messageId": message_id,
        "reply": "Your order ships within 2 days.",
        "confidence": 90,
        "category": "shipping",
        "requiresHuman": False,
        "reasoning": "found in KB",
        "sourcesUsed": ["shipping.txt"],
        "status": "pending",
        "editedReply": None,
        "createdAt": datetime.now(timezone.utc),
        "resolvedAt": None,
        "resolvedBy": None,
    }
    doc.update(overrides)
    result = await mock_db.drafts.insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_list_threads_filters_by_status_and_includes_latest_draft_summary(
    client, mock_db
):
    workspace_id = await _make_workspace(mock_db)
    needs_review_id = await _make_thread(mock_db, workspace_id, status="needs_review")
    msg_id = await _make_message(mock_db, needs_review_id)
    await _make_draft(mock_db, needs_review_id, msg_id, confidence=77, category="billing")

    sent_id = await _make_thread(mock_db, workspace_id, status="sent", gmailThreadId="gt-2")
    await _make_message(mock_db, sent_id)

    res = await client.get("/threads", params={"status": "needs_review"}, headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["items"]) == 1
    row = data["items"][0]
    assert row["id"] == needs_review_id
    assert row["confidence"] == 77
    assert row["category"] == "billing"

    res_all = await client.get("/threads", headers=HEADERS)
    assert res_all.json()["total"] == 2


@pytest.mark.asyncio
async def test_list_threads_sorted_by_last_message_at_desc_and_paginated(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    now = datetime.now(timezone.utc)
    older_id = await _make_thread(
        mock_db, workspace_id, gmailThreadId="gt-old", lastMessageAt=now - timedelta(days=1)
    )
    newer_id = await _make_thread(
        mock_db, workspace_id, gmailThreadId="gt-new", lastMessageAt=now
    )

    res = await client.get("/threads", headers=HEADERS)
    ids = [item["id"] for item in res.json()["items"]]
    assert ids.index(newer_id) < ids.index(older_id)


@pytest.mark.asyncio
async def test_get_thread_detail_returns_messages_in_order_and_latest_draft(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    now = datetime.now(timezone.utc)
    msg1 = await _make_message(
        mock_db, thread_id, bodyText="first", receivedAt=now - timedelta(minutes=10)
    )
    msg2 = await _make_message(
        mock_db, thread_id, bodyText="second", receivedAt=now
    )
    await _make_draft(mock_db, thread_id, msg2, reasoning="because KB says so")

    res = await client.get(f"/threads/{thread_id}", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == thread_id
    assert [m["bodyText"] for m in data["messages"]] == ["first", "second"]
    assert data["draft"]["reasoning"] == "because KB says so"
    assert data["draft"]["sourcesUsed"] == ["shipping.txt"]
    assert data["draft"]["editedReply"] is None


@pytest.mark.asyncio
async def test_approve_with_edited_body_sends_edited_text_and_marks_edited_sent(
    client, mock_db, monkeypatch
):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id)
    await mock_db.connections.insert_one(
        {
            "workspaceId": workspace_id,
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-1"})
    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "reply_to_thread", reply_mock)

    res = await client.post(
        f"/threads/{thread_id}/approve",
        json={"body": "Edited reply text"},
        headers=HEADERS,
    )
    assert res.status_code == 200

    reply_mock.assert_called_once()
    assert reply_mock.call_args[0][0] == "conn_123"
    assert reply_mock.call_args[0][1] == workspace_id
    assert reply_mock.call_args[0][2] == "gt-1"
    assert reply_mock.call_args[0][3] == "customer@example.com"
    assert reply_mock.call_args[0][4] == "Edited reply text"

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "edited_sent"
    assert draft["editedReply"] == "Edited reply text"
    assert draft["resolvedAt"] is not None

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "sent"

    outbound = await mock_db.messages.find_one({"sentBy": "human_approved"})
    assert outbound is not None
    assert outbound["bodyText"] == "Edited reply text"

    events = await mock_db.events.find({"type": "approved"}).to_list(None)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_approve_without_body_uses_draft_reply_and_marks_approved_sent(
    client, mock_db, monkeypatch
):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Original draft reply")

    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-2"})
    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "reply_to_thread", reply_mock)

    res = await client.post(f"/threads/{thread_id}/approve", json={}, headers=HEADERS)
    assert res.status_code == 200

    assert reply_mock.call_args[0][4] == "Original draft reply"

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "approved_sent"
    assert draft["editedReply"] is None


@pytest.mark.asyncio
async def test_approve_with_no_pending_draft_returns_409(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)

    res = await client.post(f"/threads/{thread_id}/approve", json={}, headers=HEADERS)
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_approve_with_empty_string_body_returns_400(client, mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Original draft reply")

    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-empty"})
    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "reply_to_thread", reply_mock)

    res = await client.post(
        f"/threads/{thread_id}/approve", json={"body": ""}, headers=HEADERS
    )
    assert res.status_code == 400

    reply_mock.assert_not_called()

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_with_whitespace_only_body_returns_400(client, mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Original draft reply")

    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-whitespace"})
    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "reply_to_thread", reply_mock)

    res = await client.post(
        f"/threads/{thread_id}/approve", json={"body": "   "}, headers=HEADERS
    )
    assert res.status_code == 400

    reply_mock.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_replaces_pending_draft_with_instruction(client, mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Old reply")

    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    generate_mock = AsyncMock(
        return_value=DraftResult(
            reply="New shorter reply",
            confidence=80,
            category="shipping",
            requires_human=False,
            reasoning="regenerated",
            sources_used=[],
        )
    )
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    res = await client.post(
        f"/threads/{thread_id}/regenerate",
        json={"instruction": "make it shorter"},
        headers=HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reply"] == "New shorter reply"

    generate_mock.assert_called_once()
    assert generate_mock.call_args.kwargs.get("extra_instruction") == "make it shorter"

    drafts = await mock_db.drafts.find({"threadId": thread_id}).to_list(None)
    assert len(drafts) == 1
    assert drafts[0]["reply"] == "New shorter reply"
    assert drafts[0]["status"] == "pending"

    workspace = await mock_db.workspaces.find_one({"_id": workspace_id})
    assert workspace["usage"]["emailsProcessedThisMonth"] == 1


@pytest.mark.asyncio
async def test_regenerate_without_active_subscription_returns_402(client, mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db, subscriptionStatus="none")
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Old reply")

    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    generate_mock = AsyncMock()
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    res = await client.post(
        f"/threads/{thread_id}/regenerate",
        json={"instruction": "make it shorter"},
        headers=HEADERS,
    )
    assert res.status_code == 402
    assert res.json()["detail"] == "Subscription required"

    generate_mock.assert_not_called()

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["reply"] == "Old reply"


@pytest.mark.asyncio
async def test_regenerate_at_usage_limit_returns_429(client, mock_db, monkeypatch):
    from app.pipeline import USAGE_LIMIT

    workspace_id = await _make_workspace(
        mock_db, usage={"emailsProcessedThisMonth": USAGE_LIMIT}
    )
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Old reply")

    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    generate_mock = AsyncMock()
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    res = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )
    assert res.status_code == 429
    assert res.json()["detail"] == "monthly usage limit reached"

    generate_mock.assert_not_called()

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["reply"] == "Old reply"


@pytest.mark.asyncio
async def test_regenerate_throttled_after_five_rapid_calls(client, mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Old reply")

    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    generate_mock = AsyncMock(
        return_value=DraftResult(
            reply="Fresh reply",
            confidence=80,
            category="shipping",
            requires_human=False,
            reasoning="regenerated",
            sources_used=[],
        )
    )
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    for _ in range(5):
        ok = await client.post(
            f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
        )
        assert ok.status_code == 200

    throttled = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )
    assert throttled.status_code == 429
    assert throttled.json()["detail"] == "too many regenerations, slow down"


@pytest.mark.asyncio
async def test_list_threads_page_over_max_returns_422(client, mock_db):
    await _make_workspace(mock_db)
    res = await client.get("/threads", params={"page": 1001}, headers=HEADERS)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_discard_sets_draft_discarded_and_thread_ignored(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id)

    res = await client.post(f"/threads/{thread_id}/discard", headers=HEADERS)
    assert res.status_code == 200

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "discarded"

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "ignored"

    events = await mock_db.events.find({"type": "discarded"}).to_list(None)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_regenerate_on_sent_thread_with_no_pending_draft_returns_409(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id, status="sent")
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, status="approved_sent")

    res = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )
    assert res.status_code == 409

    drafts = await mock_db.drafts.find({"threadId": thread_id}).to_list(None)
    assert len(drafts) == 1
    assert drafts[0]["status"] == "approved_sent"


@pytest.mark.asyncio
async def test_regenerate_on_needs_review_thread_with_pending_draft_still_works(
    client, mock_db, monkeypatch
):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id, status="needs_review")
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, reply="Old reply")

    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    generate_mock = AsyncMock(
        return_value=DraftResult(
            reply="Fresh reply",
            confidence=88,
            category="shipping",
            requires_human=False,
            reasoning="regenerated",
            sources_used=[],
        )
    )
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    res = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )
    assert res.status_code == 200
    assert res.json()["reply"] == "Fresh reply"

    drafts = await mock_db.drafts.find({"threadId": thread_id}).to_list(None)
    assert len(drafts) == 1
    assert drafts[0]["status"] == "pending"
    assert drafts[0]["reply"] == "Fresh reply"


@pytest.mark.asyncio
async def test_discard_on_sent_thread_with_resolved_draft_returns_409(client, mock_db):
    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id, status="sent")
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id, status="approved_sent")

    res = await client.post(f"/threads/{thread_id}/discard", headers=HEADERS)
    assert res.status_code == 409

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "sent"


@pytest.mark.asyncio
async def test_regenerate_reserves_usage_credit_before_generating(
    client, mock_db, monkeypatch
):
    """The usage credit must be reserved atomically BEFORE the LLM call, not
    incremented after it — otherwise concurrent regenerations can race past
    the cap and overspend."""
    from app.routers import threads as threads_router

    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    message_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, message_id)

    captured = {}

    async def capture_generate(*args, **kwargs):
        ws = await mock_db.workspaces.find_one({"_id": WORKSPACE_ID})
        captured["usage_at_generate"] = ws["usage"]["emailsProcessedThisMonth"]
        return DraftResult(
            reply="Regenerated reply.",
            confidence=88,
            category="shipping",
            requires_human=False,
            reasoning="regenerated",
            sources_used=[],
        )

    monkeypatch.setattr(threads_router, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(threads_router, "generate_draft", capture_generate)

    response = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )

    assert response.status_code == 200
    assert captured["usage_at_generate"] == 1
    ws = await mock_db.workspaces.find_one({"_id": WORKSPACE_ID})
    assert ws["usage"]["emailsProcessedThisMonth"] == 1


@pytest.mark.asyncio
async def test_regenerate_instruction_over_max_length_returns_422(
    client, mock_db, monkeypatch
):
    from app.routers import threads as threads_router

    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    message_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, message_id)

    generate_mock = AsyncMock()
    monkeypatch.setattr(threads_router, "generate_draft", generate_mock)

    response = await client.post(
        f"/threads/{thread_id}/regenerate",
        json={"instruction": "x" * 5_000},
        headers=HEADERS,
    )

    assert response.status_code == 422
    generate_mock.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_retrieve_query_truncates_oversized_body(
    client, mock_db, monkeypatch
):
    from app.draft import MAX_BODY_CHARS
    from app.routers import threads as threads_router

    workspace_id = await _make_workspace(mock_db)
    thread_id = await _make_thread(mock_db, workspace_id)
    message_id = await _make_message(
        mock_db, thread_id, bodyText="x" * (MAX_BODY_CHARS * 3)
    )
    await _make_draft(mock_db, thread_id, message_id)

    captured = {}

    async def capture_retrieve(db, ws_id, query, **kwargs):
        captured["query"] = query
        return []

    monkeypatch.setattr(threads_router, "retrieve", capture_retrieve)
    monkeypatch.setattr(
        threads_router,
        "generate_draft",
        AsyncMock(
            return_value=DraftResult(
                reply="ok",
                confidence=88,
                category="shipping",
                requires_human=False,
                reasoning="r",
                sources_used=[],
            )
        ),
    )

    response = await client.post(
        f"/threads/{thread_id}/regenerate", json={}, headers=HEADERS
    )

    assert response.status_code == 200
    assert len(captured["query"]) <= MAX_BODY_CHARS + 200


@pytest.mark.asyncio
async def test_approve_without_active_subscription_returns_402(client, mock_db, monkeypatch):
    """Sending is a paid feature: a lapsed workspace must not keep
    approving/sending leftover pending drafts after cancellation."""
    workspace_id = await _make_workspace(mock_db, subscriptionStatus="canceled", plan=None)
    thread_id = await _make_thread(mock_db, workspace_id)
    msg_id = await _make_message(mock_db, thread_id)
    await _make_draft(mock_db, thread_id, msg_id)

    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-gated"})
    from app.routers import threads as threads_router

    monkeypatch.setattr(threads_router, "reply_to_thread", reply_mock)

    res = await client.post(f"/threads/{thread_id}/approve", json={}, headers=HEADERS)

    assert res.status_code == 402
    reply_mock.assert_not_called()

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "pending"


async def test_approve_with_oversized_body_returns_422(client, mock_db):
    res = await client.post(
        f"/threads/{ObjectId()}/approve",
        json={"body": "x" * 100_001},
        headers=HEADERS,
    )

    assert res.status_code == 422


async def test_regenerate_with_oversized_instruction_returns_422(client, mock_db):
    res = await client.post(
        f"/threads/{ObjectId()}/regenerate",
        json={"instruction": "x" * 2_001},
        headers=HEADERS,
    )

    assert res.status_code == 422
