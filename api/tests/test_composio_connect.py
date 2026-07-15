from app.collections import ensure_indexes
from app.routers import composio_connect

from tests.conftest import HEADERS

CONNECT_PATH = "/composio/connect"


async def test_connect_already_active_is_noop(client, mock_db, monkeypatch):
    await ensure_indexes(mock_db)
    doc = {
        "workspaceId": "ws1",
        "provider": "gmail",
        "composioConnectionId": "conn_123",
        "emailAddress": "support@ourcompany.com",
        "status": "active",
    }
    await mock_db.connections.insert_one(doc)

    calls = []

    def fake_initiate(workspace_id):
        calls.append(workspace_id)
        return {"redirectUrl": "https://should-not-be-used", "connectionId": "conn_new"}

    monkeypatch.setattr(composio_connect.composio_client, "initiate_connection", fake_initiate)

    r = await client.get(CONNECT_PATH, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"alreadyConnected": True, "emailAddress": "support@ourcompany.com"}

    assert calls == []

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "active"
    assert stored["composioConnectionId"] == "conn_123"
    assert stored["emailAddress"] == "support@ourcompany.com"


async def test_disconnect_sets_status_disconnected(client, mock_db):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    r = await client.delete("/composio/connection", headers=HEADERS)

    assert r.status_code == 200
    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "disconnected"


async def test_disconnect_clears_composio_connection_id_and_stamps_disconnected_at(
    client, mock_db
):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    r = await client.delete("/composio/connection", headers=HEADERS)
    assert r.status_code == 200

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert "composioConnectionId" not in stored
    assert stored["disconnectedAt"] is not None


async def test_status_default_returns_stored_doc_without_calling_sdk(
    client, mock_db, monkeypatch
):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("SDK should not be called for the default (non-live) status check")

    monkeypatch.setattr(composio_connect.composio_client, "get_connection_status", fail_if_called)

    r = await client.get("/composio/status", headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "active", "emailAddress": "support@ourcompany.com"}


async def test_disconnect_then_default_status_stays_disconnected_without_sdk_call(
    client, mock_db, monkeypatch
):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("SDK should not be called for the default (non-live) status check")

    monkeypatch.setattr(composio_connect.composio_client, "get_connection_status", fail_if_called)

    disconnect_res = await client.delete("/composio/connection", headers=HEADERS)
    assert disconnect_res.status_code == 200

    status_res = await client.get("/composio/status", headers=HEADERS)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "disconnected"

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "disconnected"


async def test_status_live_polls_sdk_and_updates_stored_doc(client, mock_db, monkeypatch):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "pending",
        }
    )

    def fake_get_connection_status(connection_id):
        assert connection_id == "conn_123"
        return {"status": "ACTIVE", "emailAddress": "support@ourcompany.com"}

    monkeypatch.setattr(
        composio_connect.composio_client, "get_connection_status", fake_get_connection_status
    )

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "active", "emailAddress": "support@ourcompany.com"}

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "active"
    assert stored["emailAddress"] == "support@ourcompany.com"


async def test_status_live_self_heals_when_composio_account_gone(client, mock_db, monkeypatch):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_gone",
            "status": "pending",
        }
    )

    def fake_get_connection_status(connection_id):
        return {"status": "NOT_FOUND", "emailAddress": None}

    monkeypatch.setattr(
        composio_connect.composio_client, "get_connection_status", fake_get_connection_status
    )

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "none", "emailAddress": None}

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "disconnected"
    assert stored.get("composioConnectionId") is None


async def test_status_live_transition_to_active_enables_gmail_trigger(client, mock_db, monkeypatch):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "pending",
        }
    )

    monkeypatch.setattr(
        composio_connect.composio_client,
        "get_connection_status",
        lambda connection_id: {"status": "ACTIVE", "emailAddress": "support@ourcompany.com"},
    )

    trigger_calls = []

    def fake_ensure_gmail_trigger(connection_id):
        trigger_calls.append(connection_id)

    monkeypatch.setattr(composio_connect.composio_client, "ensure_gmail_trigger", fake_ensure_gmail_trigger)

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert trigger_calls == ["conn_123"]


async def test_status_live_activation_fetches_and_stores_mailbox_address(client, mock_db, monkeypatch):
    """The connected-account object itself carries no email address —
    `GMAIL_GET_PROFILE` (via `fetch_mailbox_address`) is the real source,
    called when the SDK's own status result doesn't carry one."""
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "pending",
        }
    )

    monkeypatch.setattr(
        composio_connect.composio_client,
        "get_connection_status",
        lambda connection_id: {"status": "ACTIVE", "emailAddress": None},
    )

    fetch_calls = []

    async def fake_fetch_mailbox_address(connection_id):
        fetch_calls.append(connection_id)
        return "support@ourcompany.com"

    monkeypatch.setattr(
        composio_connect.composio_client, "fetch_mailbox_address", fake_fetch_mailbox_address
    )
    monkeypatch.setattr(composio_connect.composio_client, "ensure_gmail_trigger", lambda cid: None)

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "active", "emailAddress": "support@ourcompany.com"}
    assert fetch_calls == ["conn_123"]

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["emailAddress"] == "support@ourcompany.com"


async def test_status_live_backfills_mailbox_address_on_already_active_connection(
    client, mock_db, monkeypatch
):
    """A poll for a connection that was already flipped active before the
    profile-fetch existed (stored doc active, `emailAddress` null) must
    backfill the address the next time a `live=1` poll runs, not just on
    the initial pending -> active transition."""
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "active",
            "emailAddress": None,
        }
    )

    monkeypatch.setattr(
        composio_connect.composio_client,
        "get_connection_status",
        lambda connection_id: {"status": "ACTIVE", "emailAddress": None},
    )

    async def fake_fetch_mailbox_address(connection_id):
        return "support@ourcompany.com"

    monkeypatch.setattr(
        composio_connect.composio_client, "fetch_mailbox_address", fake_fetch_mailbox_address
    )
    monkeypatch.setattr(composio_connect.composio_client, "ensure_gmail_trigger", lambda cid: None)

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "active", "emailAddress": "support@ourcompany.com"}

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["emailAddress"] == "support@ourcompany.com"


async def test_status_live_mailbox_address_fetch_failure_still_reports_active(
    client, mock_db, monkeypatch
):
    """A failed (or empty) profile fetch must not fail activation — the
    connection stays active with `emailAddress: null` rather than erroring
    or reverting status."""
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "pending",
        }
    )

    monkeypatch.setattr(
        composio_connect.composio_client,
        "get_connection_status",
        lambda connection_id: {"status": "ACTIVE", "emailAddress": None},
    )

    async def fake_fetch_mailbox_address_returns_none(connection_id):
        return None

    monkeypatch.setattr(
        composio_connect.composio_client,
        "fetch_mailbox_address",
        fake_fetch_mailbox_address_returns_none,
    )
    monkeypatch.setattr(composio_connect.composio_client, "ensure_gmail_trigger", lambda cid: None)

    r = await client.get("/composio/status", params={"live": "1"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"status": "active", "emailAddress": None}

    stored = await mock_db.connections.find_one({"workspaceId": "ws1", "provider": "gmail"})
    assert stored["status"] == "active"
    assert stored["emailAddress"] is None
