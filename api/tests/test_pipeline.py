"""Tests for the drafting pipeline orchestration."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from app import pipeline
from app.draft import DraftResult


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
    usage = dict(emailsProcessedThisMonth=0)
    usage.update(overrides.pop("usage", {}))
    doc = {
        "_id": ObjectId(),
        "name": "Acme Co",
        "settings": settings,
        "usage": usage,
        "plan": "pro",
        "subscriptionStatus": "active",
    }
    doc.update(overrides)
    result = await mock_db.workspaces.insert_one(doc)
    return str(result.inserted_id)


async def _make_thread_and_message(mock_db, workspace_id, **overrides):
    thread_doc = {
        "_id": ObjectId(),
        "workspaceId": workspace_id,
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "customerEmail": "customer@example.com",
        "customerName": "Cus Tomer",
        "status": "needs_review",
        "category": None,
        "lastMessageAt": datetime.now(timezone.utc),
        "snippet": "Where is my order?",
    }
    thread_result = await mock_db.threads.insert_one(thread_doc)
    thread_id = thread_result.inserted_id

    message_doc = {
        "threadId": str(thread_id),
        "gmailMessageId": "gm-1",
        "direction": "inbound",
        "from": "customer@example.com",
        "to": "support@ourcompany.com",
        "bodyText": "Hi, when will my order arrive?",
        "bodyHtml": None,
        "sentBy": "customer",
        "receivedAt": datetime.now(timezone.utc),
    }
    message_doc.update(overrides)
    message_result = await mock_db.messages.insert_one(message_doc)

    return str(thread_id), str(message_result.inserted_id)


def _draft_result(**overrides):
    base = dict(
        reply="Your order ships within 2 days.",
        confidence=90,
        category="shipping",
        requires_human=False,
        reasoning="found in KB",
        sources_used=["shipping.txt"],
    )
    base.update(overrides)
    return DraftResult(**base)


@pytest.mark.asyncio
async def test_newsletter_classification_ignores_thread_and_skips_draft(mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db)
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="newsletter"))
    generate_draft_mock = AsyncMock()
    monkeypatch.setattr(pipeline, "generate_draft", generate_draft_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "ignored"
    assert await mock_db.drafts.count_documents({}) == 0
    generate_draft_mock.assert_not_called()


@pytest.mark.asyncio
async def test_support_request_with_autopilot_off_creates_pending_draft_and_needs_review(
    mock_db, monkeypatch
):
    workspace_id = await _make_workspace(mock_db, settings={"autopilot": False})
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="support_request"))
    monkeypatch.setattr(pipeline, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "generate_draft", AsyncMock(return_value=_draft_result()))
    reply_mock = AsyncMock()
    monkeypatch.setattr(pipeline, "reply_to_thread", reply_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft is not None
    assert draft["status"] == "pending"

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"

    workspace = await mock_db.workspaces.find_one({"_id": ObjectId(workspace_id)})
    assert workspace["usage"]["emailsProcessedThisMonth"] == 1

    reply_mock.assert_not_called()


@pytest.mark.asyncio
async def test_autopilot_on_confidence_above_threshold_and_clean_guardrails_auto_sends(
    mock_db, monkeypatch
):
    workspace_id = await _make_workspace(
        mock_db, settings={"autopilot": True, "confidenceThreshold": 85}
    )
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)
    await mock_db.connections.insert_one(
        {
            "workspaceId": workspace_id,
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="support_request"))
    monkeypatch.setattr(pipeline, "retrieve", AsyncMock(return_value=[{"text": "x", "documentName": "d.txt", "score": 0.9}]))
    monkeypatch.setattr(
        pipeline, "generate_draft", AsyncMock(return_value=_draft_result(confidence=90))
    )
    reply_mock = AsyncMock(return_value={"gmailMessageId": "gm-out-1"})
    monkeypatch.setattr(pipeline, "reply_to_thread", reply_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    reply_mock.assert_called_once()
    assert reply_mock.call_args[0][0] == "conn_123"
    assert reply_mock.call_args[0][1] == "gt-1"

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "auto_sent"

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "auto_sent"

    outbound = await mock_db.messages.find_one({"sentBy": "ai_auto"})
    assert outbound is not None
    assert outbound["gmailMessageId"] == "gm-out-1"

    events = await mock_db.events.find({"type": "auto_sent"}).to_list(None)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_autopilot_on_but_blocked_category_guardrail_prevents_send(mock_db, monkeypatch):
    workspace_id = await _make_workspace(
        mock_db, settings={"autopilot": True, "confidenceThreshold": 85}
    )
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="support_request"))
    monkeypatch.setattr(pipeline, "retrieve", AsyncMock(return_value=[{"text": "x", "documentName": "d.txt", "score": 0.9}]))
    monkeypatch.setattr(
        pipeline,
        "generate_draft",
        AsyncMock(return_value=_draft_result(confidence=95, category="refund")),
    )
    reply_mock = AsyncMock()
    monkeypatch.setattr(pipeline, "reply_to_thread", reply_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    reply_mock.assert_not_called()

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft["status"] == "pending"


@pytest.mark.asyncio
async def test_usage_at_limit_skips_classification_and_marks_needs_review(mock_db, monkeypatch):
    workspace_id = await _make_workspace(mock_db, usage={"emailsProcessedThisMonth": 500})
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    classify_mock = AsyncMock(return_value="support_request")
    monkeypatch.setattr(pipeline, "classify_email", classify_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    classify_mock.assert_not_called()

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"

    events = await mock_db.events.find({"type": "usage_limit_hit"}).to_list(None)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_draft_generation_error_marks_needs_review_and_logs_pipeline_error(
    mock_db, monkeypatch
):
    workspace_id = await _make_workspace(mock_db)
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="support_request"))
    monkeypatch.setattr(pipeline, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "generate_draft", AsyncMock(side_effect=RuntimeError("boom")))

    await pipeline.process_inbound(workspace_id, message_id)

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"

    events = await mock_db.events.find({"type": "pipeline_error"}).to_list(None)
    assert len(events) == 1
    assert "boom" in events[0]["meta"]["error"]


@pytest.mark.asyncio
async def test_past_due_workspace_with_prior_plan_skips_drafting(mock_db, monkeypatch):
    workspace_id = await _make_workspace(
        mock_db,
        subscriptionStatus="past_due",
        stripeCustomerId="cus_123",
    )
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    classify_mock = AsyncMock(return_value="support_request")
    monkeypatch.setattr(pipeline, "classify_email", classify_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    classify_mock.assert_not_called()

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"

    events = await mock_db.events.find({"type": "subscription_inactive"}).to_list(None)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_canceled_workspace_with_prior_plan_skips_drafting(mock_db, monkeypatch):
    workspace_id = await _make_workspace(
        mock_db,
        plan=None,
        subscriptionStatus="canceled",
        stripeCustomerId="cus_123",
    )
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    classify_mock = AsyncMock(return_value="support_request")
    monkeypatch.setattr(pipeline, "classify_email", classify_mock)

    await pipeline.process_inbound(workspace_id, message_id)

    classify_mock.assert_not_called()

    thread = await mock_db.threads.find_one({"_id": ObjectId(thread_id)})
    assert thread["status"] == "needs_review"


@pytest.mark.asyncio
async def test_never_checked_out_workspace_still_drafts(mock_db, monkeypatch):
    """subscriptionStatus 'none' with no stripeCustomerId (never checked out)
    must keep working — only workspaces that HAVE had a plan get gated."""
    workspace_id = await _make_workspace(
        mock_db,
        plan=None,
        subscriptionStatus="none",
        stripeCustomerId=None,
    )
    thread_id, message_id = await _make_thread_and_message(mock_db, workspace_id)

    monkeypatch.setattr(pipeline, "classify_email", AsyncMock(return_value="support_request"))
    monkeypatch.setattr(pipeline, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, "generate_draft", AsyncMock(return_value=_draft_result()))

    await pipeline.process_inbound(workspace_id, message_id)

    draft = await mock_db.drafts.find_one({"threadId": thread_id})
    assert draft is not None
