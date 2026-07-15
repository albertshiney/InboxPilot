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
