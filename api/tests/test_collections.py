from app.collections import ensure_indexes


async def test_ensure_indexes_creates_all_expected_indexes(mock_db):
    await ensure_indexes(mock_db)

    # Message dedupe is workspace-scoped so one tenant's Gmail message id
    # cannot suppress another tenant's email with the same id.
    messages_indexes = await mock_db.messages.index_information()
    message_identity_index = messages_indexes["workspaceId_1_gmailMessageId_1"]
    assert message_identity_index["unique"] is True

    threads_indexes = await mock_db.threads.index_information()
    assert "workspaceId_1_status_1_lastMessageAt_1" in threads_indexes
    thread_identity_index = threads_indexes["workspaceId_1_gmailThreadId_1"]
    assert thread_identity_index["unique"] is True

    kb_chunks_indexes = await mock_db.kb_chunks.index_information()
    assert "workspaceId_1_documentId_1" in kb_chunks_indexes

    events_indexes = await mock_db.events.index_information()
    assert "workspaceId_1_ts_1" in events_indexes

    connections_indexes = await mock_db.connections.index_information()
    assert "workspaceId_1" in connections_indexes

    # Auth/ownership uniqueness (the Mongo adapter does not create these).
    users_indexes = await mock_db.users.index_information()
    assert users_indexes["email_1"]["unique"] is True

    sessions_indexes = await mock_db.sessions.index_information()
    assert sessions_indexes["sessionToken_1"]["unique"] is True

    accounts_indexes = await mock_db.accounts.index_information()
    assert accounts_indexes["provider_1_providerAccountId_1"]["unique"] is True

    workspaces_indexes = await mock_db.workspaces.index_information()
    assert workspaces_indexes["ownerId_1"]["unique"] is True
