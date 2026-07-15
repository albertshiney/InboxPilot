from conftest import HEADERS


async def test_whoami_no_headers_401(client):
    r = await client.get("/internal/whoami")
    assert r.status_code == 401


async def test_whoami_wrong_key_401(client):
    r = await client.get(
        "/internal/whoami",
        headers={"X-Internal-Key": "wrong-key", "X-Workspace-Id": "ws1"},
    )
    assert r.status_code == 401


async def test_whoami_missing_workspace_400(client):
    r = await client.get(
        "/internal/whoami",
        headers={"X-Internal-Key": "test-internal-key"},
    )
    assert r.status_code == 400


async def test_whoami_ok(client):
    r = await client.get(
        "/internal/whoami",
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"workspaceId": "ws1"}
