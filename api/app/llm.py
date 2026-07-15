"""LLM client accessors (Anthropic and OpenAI) with lazy initialization and caching."""
from typing import Optional

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from .config import get_settings

# Module-level caches for SDK clients
_anthropic_client: Optional[AsyncAnthropic] = None
_openai_client: Optional[AsyncOpenAI] = None


def get_anthropic() -> AsyncAnthropic:
    """Get or create cached Anthropic async client."""
    global _anthropic_client
    if _anthropic_client is None:
        settings = get_settings()
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def get_openai() -> AsyncOpenAI:
    """Get or create cached OpenAI async client."""
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


def reset_clients():
    """Reset cached clients (for testing)."""
    global _anthropic_client, _openai_client
    _anthropic_client = None
    _openai_client = None
