from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the InboxPilot API, sourced from env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27017"
    internal_api_key: str = ""
    composio_api_key: str = ""
    composio_auth_config_id: str = ""
    composio_webhook_secret: str = ""
    backend_public_url: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    frontend_url: str = "http://localhost:3000"

    draft_model: str = "claude-sonnet-4-6"
    classify_model: str = "claude-haiku-4-5"
    embed_model: str = "text-embedding-3-small"


@lru_cache
def get_settings() -> Settings:
    return Settings()
