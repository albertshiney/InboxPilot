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
