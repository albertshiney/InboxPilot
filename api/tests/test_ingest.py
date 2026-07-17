from datetime import datetime, timezone

from app.collections import ensure_indexes
from app.ingest import ingest_message


def _raw(**overrides) -> dict:
    base = {
        "gmailMessageId": "gm-1",
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "fromEmail": "customer@example.com",
        "fromName": "Cus Tomer",
        "toEmail": "support@ourcompany.com",
        "bodyText": "Hi, I never received my order. " + ("x" * 200),
        "bodyHtml": "<p>Hi</p>",
        "receivedAt": datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        "isOutbound": False,
    }
    base.update(overrides)
    return base


async def test_ingest_message_inserts_thread_and_message_and_logs_event(mock_db):
    await ensure_indexes(mock_db)

    message_id = await ingest_message(mock_db, "ws1", _raw())

    assert message_id is not None

    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message is not None
    assert message["direction"] == "inbound"
    assert message["sentBy"] == "customer"
    assert message["from"] == "customer@example.com"
    assert message["to"] == "support@ourcompany.com"

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread is not None
    assert thread["subject"] == "Where is my order?"
    assert thread["customerEmail"] == "customer@example.com"
    assert thread["customerName"] == "Cus Tomer"
    assert len(thread["snippet"]) == 140
    assert str(message["threadId"]) == str(thread["_id"])

    event = await mock_db.events.find_one({"workspaceId": "ws1", "type": "email_received"})
    assert event is not None


async def test_ingest_message_dedupes_on_gmail_message_id(mock_db):
    await ensure_indexes(mock_db)

    first = await ingest_message(mock_db, "ws1", _raw())
    assert first is not None

    second = await ingest_message(mock_db, "ws1", _raw())
    assert second is None

    assert await mock_db.messages.count_documents({}) == 1
    assert await mock_db.threads.count_documents({}) == 1
    assert await mock_db.events.count_documents({"type": "email_received"}) == 1


async def test_ingest_message_same_gmail_id_across_workspaces_not_deduped(mock_db):
    """M8: the dedupe key is (workspaceId, gmailMessageId). Two different
    tenants receiving a Gmail message that happens to share the same
    gmailMessageId must BOTH ingest — one tenant's id can never suppress
    another's email."""
    await ensure_indexes(mock_db)

    first = await ingest_message(mock_db, "ws1", _raw())
    second = await ingest_message(mock_db, "ws2", _raw())

    assert first is not None
    assert second is not None

    assert await mock_db.messages.count_documents({}) == 2
    assert await mock_db.messages.count_documents({"workspaceId": "ws1"}) == 1
    assert await mock_db.messages.count_documents({"workspaceId": "ws2"}) == 1


async def test_ingest_message_same_gmail_id_within_workspace_deduped(mock_db):
    """M8: within a single workspace the same gmailMessageId is still
    deduped — only the first ingest wins."""
    await ensure_indexes(mock_db)

    first = await ingest_message(mock_db, "ws1", _raw())
    second = await ingest_message(mock_db, "ws1", _raw())

    assert first is not None
    assert second is None

    assert await mock_db.messages.count_documents({"workspaceId": "ws1"}) == 1


async def test_ingest_message_skips_outbound(mock_db):
    await ensure_indexes(mock_db)

    result = await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-out", isOutbound=True))

    assert result is None
    assert await mock_db.messages.count_documents({}) == 0
    assert await mock_db.threads.count_documents({}) == 0


async def test_ingest_message_skips_from_connected_support_address(mock_db):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    result = await ingest_message(
        mock_db, "ws1", _raw(gmailMessageId="gm-self", fromEmail="support@ourcompany.com")
    )

    assert result is None
    assert await mock_db.messages.count_documents({}) == 0


async def test_ingest_message_html_only_derives_body_text_fallback(mock_db):
    """When Gmail delivers an HTML-only message (bodyText empty/missing),
    fall back to a tag-stripped rendering of bodyHtml so the message still
    has usable text for classification/drafting/snippets."""
    await ensure_indexes(mock_db)

    html = (
        "<html><head><style>p{color:red}</style>"
        "<script>alert('x')</script></head>"
        "<body><p>Hello <b>there</b>,</p><p>Where is my order?</p></body></html>"
    )
    message_id = await ingest_message(
        mock_db, "ws1", _raw(bodyText="", bodyHtml=html)
    )

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message["bodyText"] == "Hello there , Where is my order?"
    # The style/script contents must not leak into the derived text.
    assert "red" not in message["bodyText"]
    assert "alert" not in message["bodyText"]

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread["snippet"] == "Hello there , Where is my order?"


async def test_ingest_message_html_fallback_unescapes_entities(mock_db):
    """HTML entities (e.g. `&amp;`, `&#39;`) must be decoded to their
    literal characters, not left as raw markup, in the derived text."""
    await ensure_indexes(mock_db)

    html = "<p>Bob&#39;s Bagels &amp; Coffee</p>"
    message_id = await ingest_message(
        mock_db, "ws1", _raw(gmailMessageId="gm-entities", bodyText="", bodyHtml=html)
    )

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-entities"})
    assert message["bodyText"] == "Bob's Bagels & Coffee"


async def test_ingest_message_html_fallback_strips_unclosed_script_tag(mock_db):
    """Malformed/truncated HTML with an opening `<script>`/`<style>` tag
    and no matching close tag must not leak its contents into the derived
    text — the unclosed block should be stripped through end-of-string."""
    await ensure_indexes(mock_db)

    html = "<p>Where is my order?</p><script>var leaked = 'should not appear';"
    message_id = await ingest_message(
        mock_db, "ws1", _raw(gmailMessageId="gm-unclosed", bodyText="", bodyHtml=html)
    )

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-unclosed"})
    assert message["bodyText"] == "Where is my order?"
    assert "leaked" not in message["bodyText"]


async def test_ingest_message_empty_body_and_no_html_still_ingests(mock_db):
    """Attachments-only / empty-body email: still ingested with an empty
    bodyText — the pipeline downstream drafts against the subject alone."""
    await ensure_indexes(mock_db)

    message_id = await ingest_message(mock_db, "ws1", _raw(bodyText="", bodyHtml=None))

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message["bodyText"] == ""

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread["snippet"] == ""


async def test_ingest_message_non_ascii_body_roundtrips_intact(mock_db):
    """Non-English / emoji body must survive ingestion untouched, both in
    the stored message and the thread snippet."""
    await ensure_indexes(mock_db)

    body = "Hej! Jeg har ikke modtaget min ordre endnu 😢 Kan I hjælpe mig? Æblegrød er lækkert."
    message_id = await ingest_message(mock_db, "ws1", _raw(bodyText=body, bodyHtml=None))

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message["bodyText"] == body

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread["snippet"] == body[:140]


async def test_ingest_message_same_thread_updates_last_message_at_and_snippet(mock_db):
    await ensure_indexes(mock_db)

    await ingest_message(mock_db, "ws1", _raw())
    await ingest_message(
        mock_db,
        "ws1",
        _raw(
            gmailMessageId="gm-2",
            bodyText="second message body",
            receivedAt=datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc),
        ),
    )

    assert await mock_db.threads.count_documents({}) == 1
    assert await mock_db.messages.count_documents({}) == 2

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread["snippet"] == "second message body"
    # Mongo/BSON round-trips datetimes as naive UTC (matches existing driver
    # behavior elsewhere in this codebase).
    assert thread["lastMessageAt"] == datetime(2026, 7, 15, 13, 0)


async def test_ingest_message_truncates_oversized_bodies(mock_db):
    """Stored message bodies are truncated to MAX_STORED_BODY_CHARS so a
    single giant email cannot bloat the messages collection."""
    from app import ingest

    await ensure_indexes(mock_db)

    huge_text = "a" * (ingest.MAX_STORED_BODY_CHARS + 5_000)
    huge_html = "<p>" + "b" * (ingest.MAX_STORED_BODY_CHARS + 5_000) + "</p>"
    message_id = await ingest_message(
        mock_db, "ws1", _raw(bodyText=huge_text, bodyHtml=huge_html)
    )

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert len(message["bodyText"]) == ingest.MAX_STORED_BODY_CHARS
    assert len(message["bodyHtml"]) == ingest.MAX_STORED_BODY_CHARS


async def test_ingest_message_none_body_html_stays_none_after_truncation(mock_db):
    await ensure_indexes(mock_db)

    message_id = await ingest_message(mock_db, "ws1", _raw(bodyHtml=None))

    assert message_id is not None
    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message["bodyHtml"] is None


async def test_ingest_message_daily_cap_blocks_unsubscribed_workspace(mock_db, monkeypatch):
    """A workspace with no active/trialing subscription gets the strict
    daily ingest cap — beyond it, messages are dropped, not stored."""
    from app import ingest

    await ensure_indexes(mock_db)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_UNSUBSCRIBED", 2)

    first = await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-1"))
    second = await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-2"))
    third = await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-3"))

    assert first is not None
    assert second is not None
    assert third is None
    assert await mock_db.messages.count_documents({}) == 2


async def test_ingest_message_daily_cap_uses_subscribed_tier_for_active_workspace(
    mock_db, monkeypatch
):
    """An active subscription gets the generous cap even when the
    unsubscribed cap is lower."""
    from app import ingest

    await ensure_indexes(mock_db)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_UNSUBSCRIBED", 1)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_SUBSCRIBED", 3)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "subscriptionStatus": "active"}
    )

    results = [
        await ingest_message(mock_db, "ws1", _raw(gmailMessageId=f"gm-{i}"))
        for i in range(4)
    ]

    assert [r is not None for r in results] == [True, True, True, False]
    assert await mock_db.messages.count_documents({}) == 3


async def test_ingest_message_daily_cap_logs_single_event(mock_db, monkeypatch):
    """Hitting the cap logs exactly one ingest_cap_hit event — a sustained
    flood must not turn into an events-collection flood."""
    from app import ingest

    await ensure_indexes(mock_db)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_UNSUBSCRIBED", 1)

    await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-1"))
    for i in range(2, 6):
        assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId=f"gm-{i}")) is None

    events = await mock_db.events.find({"type": "ingest_cap_hit"}).to_list(None)
    assert len(events) == 1


async def test_ingest_message_daily_cap_is_per_workspace(mock_db, monkeypatch):
    """One workspace exhausting its cap must not block another's ingestion."""
    from app import ingest

    await ensure_indexes(mock_db)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_UNSUBSCRIBED", 1)

    assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-1")) is not None
    assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-2")) is None
    assert await ingest_message(mock_db, "ws2", _raw(gmailMessageId="gm-1")) is not None


async def test_ingest_message_dedupe_does_not_consume_cap(mock_db, monkeypatch):
    """Webhook redeliveries of an already-seen message must not eat into
    the daily ingest budget."""
    from app import ingest

    await ensure_indexes(mock_db)
    monkeypatch.setattr(ingest, "DAILY_INGEST_CAP_UNSUBSCRIBED", 2)

    assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-1")) is not None
    for _ in range(5):
        assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-1")) is None

    assert await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-2")) is not None
