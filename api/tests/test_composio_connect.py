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
