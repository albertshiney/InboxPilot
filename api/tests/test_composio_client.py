"""Unit tests for the composio_client.py SDK-facing seam: dual Gmail auth
paths, real webhook signature verification, webhook auto-registration, and
Gmail trigger enablement. All tests monkeypatch `composio_client._client`
with a fake object recording calls — no network, no real SDK client
constructed."""

from datetime import datetime, timezone
from types import SimpleNamespace

from composio.exceptions import ComposioMultipleConnectedAccountsError

from app import composio_client
from app.config import get_settings


def _account(id, status, toolkit="gmail"):
    return SimpleNamespace(id=id, status=status, toolkit=SimpleNamespace(slug=toolkit))


class _FakeToolkits:
    def __init__(self):
        self.calls = []
        self.authorize_excs = []

    def authorize(self, *, user_id, toolkit):
        self.calls.append({"user_id": user_id, "toolkit": toolkit})
        if self.authorize_excs:
            raise self.authorize_excs.pop(0)
        return {"redirect_url": "https://managed-auth.example/authorize", "id": "conn_managed"}


class _FakeConnectedAccounts:
    def __init__(self):
        self.calls = []
        self.list_items = []
        self.list_calls = []
        self.delete_calls = []

    def initiate(self, user_id, auth_config_id, *, toolkit, **kwargs):
        self.calls.append(
            {"user_id": user_id, "auth_config_id": auth_config_id, "toolkit": toolkit}
        )
        return {"redirect_url": "https://byo-auth.example/authorize", "id": "conn_byo"}

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return SimpleNamespace(items=self.list_items)

    def delete(self, nanoid):
        self.delete_calls.append(nanoid)

    def get(self, nanoid):
        if self.get_exc is not None:
            raise self.get_exc
        return {"status": "ACTIVE", "connection_data": {}}

    get_exc = None


class _FakeTriggers:
    def __init__(self, verify_exc=None, subscription_result=None):
        self.verify_calls = []
        self.verify_exc = verify_exc
        self.subscription_calls = []
        self.subscription_result = subscription_result or {"secret": "s3"}
        self.create_calls = []
        self.create_exc = None

    def verify_webhook(self, *, id, payload, secret, signature, timestamp, tolerance=300):
        self.verify_calls.append(
            {
                "id": id,
                "payload": payload,
                "secret": secret,
                "signature": signature,
                "timestamp": timestamp,
            }
        )
        if self.verify_exc is not None:
            raise self.verify_exc
        return {
            "version": "V3",
            "payload": {"trigger_slug": "GMAIL_NEW_GMAIL_MESSAGE"},
            "raw_payload": {},
        }

    def set_webhook_subscription(self, *, webhook_url, **kwargs):
        self.subscription_calls.append(webhook_url)
        return self.subscription_result

    def create(self, slug, *, connected_account_id=None, **kwargs):
        self.create_calls.append({"slug": slug, "connected_account_id": connected_account_id})
        if self.create_exc is not None:
            raise self.create_exc


class _FakeTools:
    def __init__(self, execute_result=None, execute_exc=None):
        self.execute_calls = []
        self.execute_result = execute_result if execute_result is not None else {"data": {}}
        self.execute_exc = execute_exc

    def execute(
        self,
        slug,
        *,
        connected_account_id=None,
        user_id=None,
        arguments=None,
        dangerously_skip_version_check=None,
        **kwargs,
    ):
        self.execute_calls.append(
            {
                "slug": slug,
                "connected_account_id": connected_account_id,
                "user_id": user_id,
                "arguments": arguments,
                "dangerously_skip_version_check": dangerously_skip_version_check,
            }
        )
        if self.execute_exc is not None:
            raise self.execute_exc
        return self.execute_result


class _FakeClient:
    def __init__(self, tools_execute_result=None, tools_execute_exc=None, **kwargs):
        self.toolkits = _FakeToolkits()
        self.connected_accounts = _FakeConnectedAccounts()
        self.triggers = _FakeTriggers(**kwargs)
        self.tools = _FakeTools(execute_result=tools_execute_result, execute_exc=tools_execute_exc)


def _install_fake_client(monkeypatch, **kwargs):
    fake = _FakeClient(**kwargs)
    monkeypatch.setattr(composio_client, "_client", lambda: fake)
    return fake


async def test_initiate_connection_uses_managed_auth_when_auth_config_id_unset(monkeypatch):
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIG_ID", "")
    get_settings.cache_clear()
    fake = _install_fake_client(monkeypatch)

    result = await composio_client.initiate_connection("ws1")

    assert fake.toolkits.calls == [{"user_id": "ws1", "toolkit": "gmail"}]
    assert fake.connected_accounts.calls == []
    assert result == {"redirectUrl": "https://managed-auth.example/authorize", "connectionId": "conn_managed"}


async def test_initiate_connection_uses_byo_auth_config_when_set(monkeypatch):
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIG_ID", "ac_123")
    get_settings.cache_clear()
    fake = _install_fake_client(monkeypatch)

    result = await composio_client.initiate_connection("ws1")

    assert fake.connected_accounts.calls == [
        {"user_id": "ws1", "auth_config_id": "ac_123", "toolkit": "gmail"}
    ]
    assert fake.toolkits.calls == []
    assert result == {"redirectUrl": "https://byo-auth.example/authorize", "connectionId": "conn_byo"}


async def test_initiate_connection_reuses_active_account_on_multiple_accounts_error(monkeypatch):
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIG_ID", "")
    get_settings.cache_clear()
    fake = _install_fake_client(monkeypatch)
    fake.toolkits.authorize_excs = [ComposioMultipleConnectedAccountsError("multiple")]
    fake.connected_accounts.list_items = [
        _account("ca_stale", "INITIATED"),
        _account("ca_active", "ACTIVE"),
    ]

    result = await composio_client.initiate_connection("ws1")

    assert result == {"redirectUrl": None, "connectionId": "ca_active"}
    assert fake.connected_accounts.delete_calls == ["ca_stale"]


async def test_initiate_connection_deletes_stale_accounts_and_retries_on_multiple_accounts_error(
    monkeypatch,
):
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIG_ID", "")
    get_settings.cache_clear()
    fake = _install_fake_client(monkeypatch)
    fake.toolkits.authorize_excs = [ComposioMultipleConnectedAccountsError("multiple")]
    fake.connected_accounts.list_items = [
        _account("ca_stale1", "INITIATED"),
        _account("ca_stale2", "FAILED"),
    ]

    result = await composio_client.initiate_connection("ws1")

    assert sorted(fake.connected_accounts.delete_calls) == ["ca_stale1", "ca_stale2"]
    assert len(fake.toolkits.calls) == 2
    assert result == {
        "redirectUrl": "https://managed-auth.example/authorize",
        "connectionId": "conn_managed",
    }


async def test_get_connection_status_returns_not_found_when_account_deleted(monkeypatch):
    import httpx
    from composio_client import NotFoundError

    fake = _install_fake_client(monkeypatch)
    fake.connected_accounts.get_exc = NotFoundError(
        "Connected account not found",
        response=httpx.Response(404, request=httpx.Request("GET", "http://composio.test")),
        body=None,
    )

    result = await composio_client.get_connection_status("ca_gone")

    assert result == {"status": "NOT_FOUND", "emailAddress": None}


async def test_verify_webhook_true_when_sdk_does_not_raise(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    ok = await composio_client.verify_webhook(
        id="msg_1", payload="{}", secret="s3", signature="v1,abc", timestamp="123"
    )

    assert ok == {"event": {"trigger_slug": "GMAIL_NEW_GMAIL_MESSAGE"}}
    assert fake.triggers.verify_calls == [
        {"id": "msg_1", "payload": "{}", "secret": "s3", "signature": "v1,abc", "timestamp": "123"}
    ]


async def test_verify_webhook_false_when_sdk_raises(monkeypatch):
    from composio.exceptions import WebhookSignatureVerificationError

    _install_fake_client(
        monkeypatch, verify_exc=WebhookSignatureVerificationError("bad signature")
    )

    ok = await composio_client.verify_webhook(
        id="msg_1", payload="{}", secret="s3", signature="v1,bad", timestamp="123"
    )

    assert ok is None


async def test_verify_webhook_true_when_signature_valid_but_payload_shape_unrecognized(
    monkeypatch,
):
    """`client.triggers.verify_webhook` also tries to parse `payload` into one
    of its own known trigger-event envelopes (V1/V2/V3) and raises
    `WebhookPayloadError` if it doesn't match — which this app's own
    ingestion payload shape never will. That's a payload-shape concern, not
    a signature concern, so it must not fail verification."""
    from composio.exceptions import WebhookPayloadError

    _install_fake_client(monkeypatch, verify_exc=WebhookPayloadError("unrecognized shape"))

    ok = await composio_client.verify_webhook(
        id="msg_1", payload='{"connectionId": "conn_123"}', secret="s3", signature="v1,abc",
        timestamp="123",
    )

    assert ok == {"event": None}


async def test_verify_webhook_false_when_timestamp_malformed(monkeypatch):
    """A malformed timestamp must fail closed even though the SDK would also
    raise `WebhookPayloadError` for it — that specific `WebhookPayloadError`
    means the signature was *never checked* (timestamp validation runs
    first), unlike the payload-shape case above."""
    _install_fake_client(monkeypatch)

    ok = await composio_client.verify_webhook(
        id="msg_1", payload="{}", secret="s3", signature="v1,abc", timestamp="not-a-number"
    )

    assert ok is None


async def test_ensure_webhook_subscription_short_circuits_on_env_secret(monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "whsec_env")
    get_settings.cache_clear()
    composio_client._reset_webhook_secret_cache()
    fake = _install_fake_client(monkeypatch)

    secret = await composio_client.ensure_webhook_subscription()

    assert secret == "whsec_env"
    assert fake.triggers.subscription_calls == []


async def test_ensure_webhook_subscription_registers_and_caches_when_no_env_secret(monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "")
    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://api.example.com")
    monkeypatch.setenv("COMPOSIO_API_KEY", "sk_test")
    get_settings.cache_clear()
    composio_client._reset_webhook_secret_cache()
    fake = _install_fake_client(monkeypatch, subscription_result={"secret": "s3"})

    secret = await composio_client.ensure_webhook_subscription()

    assert secret == "s3"
    assert fake.triggers.subscription_calls == ["https://api.example.com/webhooks/composio"]

    # Second call is served from cache, no repeat SDK call.
    secret_again = await composio_client.ensure_webhook_subscription()
    assert secret_again == "s3"
    assert fake.triggers.subscription_calls == ["https://api.example.com/webhooks/composio"]

    composio_client._reset_webhook_secret_cache()


async def test_ensure_webhook_subscription_returns_none_without_backend_url(monkeypatch):
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", "")
    monkeypatch.setenv("BACKEND_PUBLIC_URL", "")
    get_settings.cache_clear()
    composio_client._reset_webhook_secret_cache()
    fake = _install_fake_client(monkeypatch)

    secret = await composio_client.ensure_webhook_subscription()

    assert secret is None
    assert fake.triggers.subscription_calls == []


async def test_ensure_gmail_trigger_calls_sdk_create(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    await composio_client.ensure_gmail_trigger("conn_123")

    assert fake.triggers.create_calls == [
        {"slug": "GMAIL_NEW_GMAIL_MESSAGE", "connected_account_id": "conn_123"}
    ]


async def test_ensure_gmail_trigger_swallows_exceptions(monkeypatch):
    fake = _install_fake_client(monkeypatch)
    fake.triggers.create_exc = RuntimeError("boom")

    await composio_client.ensure_gmail_trigger("conn_123")  # must not raise


async def test_fetch_mailbox_address_returns_email_from_profile(monkeypatch):
    fake = _install_fake_client(
        monkeypatch, tools_execute_result={"data": {"emailAddress": "support@ourcompany.com"}}
    )

    email = await composio_client.fetch_mailbox_address("conn_123", user_id="ws1")

    assert email == "support@ourcompany.com"
    assert fake.tools.execute_calls == [
        {
            "slug": "GMAIL_GET_PROFILE",
            "connected_account_id": "conn_123",
            "user_id": "ws1",
            "arguments": {},
            "dangerously_skip_version_check": True,
        }
    ]


async def test_fetch_mailbox_address_tolerates_snake_case_field(monkeypatch):
    _install_fake_client(
        monkeypatch, tools_execute_result={"data": {"email_address": "support@ourcompany.com"}}
    )

    email = await composio_client.fetch_mailbox_address("conn_123", user_id="ws1")

    assert email == "support@ourcompany.com"


async def test_fetch_mailbox_address_returns_none_on_failure(monkeypatch):
    _install_fake_client(monkeypatch, tools_execute_exc=RuntimeError("boom"))

    email = await composio_client.fetch_mailbox_address("conn_123", user_id="ws1")

    assert email is None


async def test_fetch_mailbox_address_returns_none_when_no_email_in_response(monkeypatch):
    _install_fake_client(monkeypatch, tools_execute_result={"data": {}})

    email = await composio_client.fetch_mailbox_address("conn_123", user_id="ws1")

    assert email is None


# Captured live from `GMAIL_FETCH_EMAILS` (toolkit version 20260702_01) on
# 2026-07-16 — the real wire shape the mapping below must handle: camelCase
# ids, `messageTimestamp` (ISO string, not `receivedAt`), RFC-formatted
# `sender`, no `messageHtml`/`senderName`/`isOutbound` fields at all.
_LIVE_GMAIL_MESSAGE = {
    "attachmentList": [],
    "display_url": "https://mail.google.com/mail/u/0/#inbox/19f6a366077e74f0",
    "labelIds": ["UNREAD", "IMPORTANT", "CATEGORY_PERSONAL", "INBOX"],
    "messageId": "19f6a366077e74f0",
    "messageText": "I want to learn more\r\n\r\nDo you have a phone number I can call?\r\n",
    "messageTimestamp": "2026-07-16T09:16:04Z",
    "preview": {"body": "I want to learn more", "subject": "Number"},
    "sender": '"Albert Olgaard" <albert.olgaard@gmail.com>',
    "subject": "Number",
    "threadId": "19f6a366077e74f0",
    "to": "albert@shiney.ai",
}


async def test_fetch_recent_messages_maps_live_gmail_payload(monkeypatch):
    fake = _install_fake_client(
        monkeypatch, tools_execute_result={"data": {"messages": [_LIVE_GMAIL_MESSAGE]}}
    )
    since = datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)

    messages = await composio_client.fetch_recent_messages("conn_123", "ws1", since)

    assert fake.tools.execute_calls == [
        {
            "slug": "GMAIL_FETCH_EMAILS",
            "connected_account_id": "conn_123",
            "user_id": "ws1",
            "arguments": {"query": f"after:{int(since.timestamp())}", "max_results": 50},
            "dangerously_skip_version_check": True,
        }
    ]
    assert messages == [
        {
            "gmailMessageId": "19f6a366077e74f0",
            "gmailThreadId": "19f6a366077e74f0",
            "subject": "Number",
            "fromEmail": "albert.olgaard@gmail.com",
            "fromName": "Albert Olgaard",
            "toEmail": "albert@shiney.ai",
            "bodyText": "I want to learn more\r\n\r\nDo you have a phone number I can call?\r\n",
            "bodyHtml": None,
            "receivedAt": datetime(2026, 7, 16, 9, 16, 4, tzinfo=timezone.utc),
            "isOutbound": False,
        }
    ]


async def test_fetch_recent_messages_marks_sent_label_as_outbound(monkeypatch):
    sent = dict(_LIVE_GMAIL_MESSAGE, labelIds=["SENT"], sender="albert@shiney.ai")
    _install_fake_client(monkeypatch, tools_execute_result={"data": {"messages": [sent]}})

    messages = await composio_client.fetch_recent_messages(
        "conn_123", "ws1", datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)
    )

    assert messages[0]["isOutbound"] is True
    assert messages[0]["fromEmail"] == "albert@shiney.ai"
    assert messages[0]["fromName"] is None


async def test_fetch_recent_messages_returns_empty_on_missing_data(monkeypatch):
    _install_fake_client(monkeypatch, tools_execute_result={"data": {}})

    messages = await composio_client.fetch_recent_messages(
        "conn_123", "ws1", datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)
    )

    assert messages == []


async def test_reply_to_thread_sends_message_body_and_recipient(monkeypatch):
    fake = _install_fake_client(
        monkeypatch, tools_execute_result={"data": {"id": "gm-out-1"}}
    )

    result = await composio_client.reply_to_thread(
        "conn_123", "ws1", "gt-1", "customer@example.com", "Thanks for reaching out!"
    )

    assert result == {"gmailMessageId": "gm-out-1"}
    assert fake.tools.execute_calls == [
        {
            "slug": "GMAIL_REPLY_TO_THREAD",
            "connected_account_id": "conn_123",
            "user_id": "ws1",
            "arguments": {
                "thread_id": "gt-1",
                "message_body": "Thanks for reaching out!",
                "recipient_email": "customer@example.com",
            },
            "dangerously_skip_version_check": True,
        }
    ]
