from app.collections import ensure_indexes


async def test_ensure_indexes_creates_all_expected_indexes(mock_db):
    await ensure_indexes(mock_db)

    messages_indexes = await mock_db.messages.index_information()
    gmail_message_id_index = messages_indexes["gmailMessageId_1"]
    assert gmail_message_id_index["unique"] is True

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
