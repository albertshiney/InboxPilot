"""Tests for Sonnet-based draft generation."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import draft
from app.draft import DraftResult, generate_draft


def _mock_client(text: str):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_create = AsyncMock(return_value=mock_response)
    mock_messages = MagicMock()
    mock_messages.create = mock_create
    mock_client = MagicMock()
    mock_client.messages = mock_messages
    return mock_client, mock_create


def _workspace(**overrides):
    settings = dict(
        autopilot=False,
        confidenceThreshold=85,
        tone="warm and casual",
        signature="- The Acme Team",
        blockedCategories=["refund"],
        customInstructions="Always mention our 30-day guarantee.",
    )
    settings.update(overrides.pop("settings", {}))
    ws = {"name": "Acme Co", "settings": settings}
    ws.update(overrides)
    return ws


@pytest.mark.asyncio
async def test_generate_draft_parses_valid_json_in_code_fence(monkeypatch):
    json_body = (
        '{"reply": "Thanks for reaching out! Your order ships tomorrow.", '
        '"confidence": 92, "category": "shipping", "requires_human": false, '
        '"reasoning": "found shipping info in KB", "sources_used": ["shipping.txt"]}'
    )
    text = f"Here you go:\n```json\n{json_body}\n```"
    mock_client, mock_create = _mock_client(text)
    monkeypatch.setattr(draft, "get_anthropic", lambda: mock_client)

    result = await generate_draft(
        _workspace(),
        [{"from": "customer@example.com", "bodyText": "When will my order arrive?"}],
        [{"text": "Orders ship within 2 days.", "documentName": "shipping.txt", "score": 0.9}],
    )

    assert isinstance(result, DraftResult)
    assert result.reply == "Thanks for reaching out! Your order ships tomorrow."
    assert result.confidence == 92
    assert result.category == "shipping"
    assert result.requires_human is False
    assert result.sources_used == ["shipping.txt"]

    # Verify called with the configured draft model
    assert mock_create.call_args[1]["model"]


@pytest.mark.asyncio
async def test_generate_draft_falls_back_when_output_is_prose(monkeypatch):
    text = "Sure! I'd be happy to help you with your order, just let me know more details."
    mock_client, _ = _mock_client(text)
    monkeypatch.setattr(draft, "get_anthropic", lambda: mock_client)

    result = await generate_draft(_workspace(), [{"from": "c@x.com", "bodyText": "hi"}], [])

    assert result.requires_human is True
    assert result.confidence == 0
    assert result.category == "other"
    assert result.reasoning == "model output unparseable"
    assert result.sources_used == []


@pytest.mark.asyncio
async def test_generate_draft_system_prompt_includes_tone_signature_and_instructions(monkeypatch):
    json_body = (
        '{"reply": "ok", "confidence": 50, "category": "other", '
        '"requires_human": false, "reasoning": "n/a", "sources_used": []}'
    )
    mock_client, mock_create = _mock_client(json_body)
    monkeypatch.setattr(draft, "get_anthropic", lambda: mock_client)

    await generate_draft(_workspace(), [{"from": "c@x.com", "bodyText": "hi"}], [])

    system_prompt = mock_create.call_args[1]["system"]
    assert "warm and casual" in system_prompt
    assert "- The Acme Team" in system_prompt
    assert "Always mention our 30-day guarantee." in system_prompt


@pytest.mark.asyncio
async def test_generate_draft_confidence_is_clamped_to_0_100(monkeypatch):
    json_body = (
        '{"reply": "ok", "confidence": 150, "category": "other", '
        '"requires_human": false, "reasoning": "n/a", "sources_used": []}'
    )
    mock_client, _ = _mock_client(json_body)
    monkeypatch.setattr(draft, "get_anthropic", lambda: mock_client)

    result = await generate_draft(_workspace(), [{"from": "c@x.com", "bodyText": "hi"}], [])
    assert result.confidence == 100
