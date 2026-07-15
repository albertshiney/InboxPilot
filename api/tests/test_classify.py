"""Tests for email classification."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.classify import classify_email
from app import classify


@pytest.mark.asyncio
async def test_classify_email_with_whitespace_output(monkeypatch):
    """Stub returning whitespace around label should be stripped and returned."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=" newsletter ")]

    mock_create = AsyncMock(return_value=mock_response)
    mock_messages = MagicMock()
    mock_messages.create = mock_create

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    monkeypatch.setattr(classify, "get_anthropic", lambda: mock_client)

    result = await classify_email("Test Subject", "Test body content")
    assert result == "newsletter"

    # Verify the mock was called with correct parameters
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5"
    assert call_kwargs["max_tokens"] == 10
    assert call_kwargs["temperature"] == 0

    # Verify subject and body are in the user message
    messages = call_kwargs["messages"]
    user_message = next(m for m in messages if m["role"] == "user")
    assert "Test Subject" in user_message["content"]
    assert "Test body content" in user_message["content"]


@pytest.mark.asyncio
async def test_classify_email_with_invalid_output(monkeypatch):
    """Unknown/garbage output should fall back to support_request."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="banana")]

    mock_create = AsyncMock(return_value=mock_response)
    mock_messages = MagicMock()
    mock_messages.create = mock_create

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    monkeypatch.setattr(classify, "get_anthropic", lambda: mock_client)

    result = await classify_email("Test Subject", "Test body")
    assert result == "support_request"


@pytest.mark.asyncio
async def test_classify_email_truncates_body(monkeypatch):
    """Body should be truncated to 4000 characters."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="support_request")]

    mock_create = AsyncMock(return_value=mock_response)
    mock_messages = MagicMock()
    mock_messages.create = mock_create

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    monkeypatch.setattr(classify, "get_anthropic", lambda: mock_client)

    long_body = "x" * 5000
    await classify_email("Subject", long_body)

    call_kwargs = mock_create.call_args[1]
    messages = call_kwargs["messages"]
    user_message = next(m for m in messages if m["role"] == "user")
    # Body should be truncated to 4000 chars
    assert len(long_body[:4000]) == 4000
    assert long_body[:4000] in user_message["content"]


@pytest.mark.asyncio
async def test_classify_email_valid_labels(monkeypatch):
    """All valid labels should be recognized."""
    labels = ["support_request", "newsletter", "notification", "spam", "auto_reply"]

    for label in labels:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=label)]

        mock_create = AsyncMock(return_value=mock_response)
        mock_messages = MagicMock()
        mock_messages.create = mock_create

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        monkeypatch.setattr(classify, "get_anthropic", lambda mc=mock_client: mc)

        result = await classify_email("Subject", "Body")
        assert result == label
