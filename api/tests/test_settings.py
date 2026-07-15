from .conftest import HEADERS

DEFAULT_SETTINGS = {
    "autopilot": False,
    "confidenceThreshold": 85,
    "tone": "friendly",
    "signature": "",
    "blockedCategories": ["refund"],
    "customInstructions": "",
}


async def test_get_settings_creates_defaults_for_unknown_workspace(client, mock_db):
    r = await client.get("/settings", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()

    assert body["name"] == "My workspace"
    assert body["settings"] == DEFAULT_SETTINGS
    assert body["plan"] is None
    assert body["subscriptionStatus"] == "none"
    assert body["trialEndsAt"] is None
    assert body["usage"] == {"emailsProcessedThisMonth": 0}
    assert body["connection"] is None

    # workspace should now exist so a second call returns the same doc, not a
    # freshly-inserted one
    doc = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert doc is not None
    assert doc["settings"]["confidenceThreshold"] == 85


async def test_get_settings_joins_gmail_connection(client, mock_db):
    await mock_db.workspaces.insert_one({"_id": "ws1", "name": "My workspace"})
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "emailAddress": "me@example.com",
            "status": "active",
        }
    )

    r = await client.get("/settings", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["connection"] == {"emailAddress": "me@example.com", "status": "active"}


async def test_patch_settings_updates_tone_field_wise(client, mock_db):
    await client.get("/settings", headers=HEADERS)  # create-on-read

    r = await client.patch("/settings", headers=HEADERS, json={"settings": {"tone": "formal"}})
    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["tone"] == "formal"
    # unrelated fields untouched
    assert body["settings"]["autopilot"] is False
    assert body["settings"]["confidenceThreshold"] == 85
    assert body["settings"]["blockedCategories"] == ["refund"]


async def test_patch_settings_clamps_confidence_threshold_high(client, mock_db):
    await client.get("/settings", headers=HEADERS)

    r = await client.patch(
        "/settings", headers=HEADERS, json={"settings": {"confidenceThreshold": 120}}
    )
    assert r.status_code == 200
    assert r.json()["settings"]["confidenceThreshold"] == 99


async def test_patch_settings_clamps_confidence_threshold_low(client, mock_db):
    await client.get("/settings", headers=HEADERS)

    r = await client.patch(
        "/settings", headers=HEADERS, json={"settings": {"confidenceThreshold": 10}}
    )
    assert r.status_code == 200
    assert r.json()["settings"]["confidenceThreshold"] == 50


async def test_patch_settings_updates_name(client, mock_db):
    await client.get("/settings", headers=HEADERS)

    r = await client.patch("/settings", headers=HEADERS, json={"name": "Acme Support"})
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Support"


async def test_settings_requires_workspace_header(client):
    r = await client.get("/settings", headers={"X-Internal-Key": HEADERS["X-Internal-Key"]})
    assert r.status_code == 400


async def test_settings_requires_valid_internal_key(client):
    r = await client.get("/settings", headers={"X-Workspace-Id": "ws1"})
    assert r.status_code == 401
