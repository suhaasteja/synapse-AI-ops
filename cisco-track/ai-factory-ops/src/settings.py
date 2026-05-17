"""Application settings loaded from environment and .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for LLM routing and explanation."""

    gemini_api_key: str | None = None
    google_api_key: str | None = None
    openai_api_key: str | None = None

    aifops_router_model: str = "gpt-4o-mini"
    aifops_explainer_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
