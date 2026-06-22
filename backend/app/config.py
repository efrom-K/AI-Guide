"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Claude API
    anthropic_api_key: str = ""

    # Model routing (per role)
    model_scorer: str = "claude-haiku-4-5"
    model_narrator: str = "claude-sonnet-4-6"
    model_companion: str = "claude-sonnet-4-6"
    model_landmark: str = "claude-opus-4-8"

    # Geo
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Behaviour
    default_language: str = "ru"
    default_radius_m: float = 80.0
    max_radius_m: float = 500.0

    # State store ("" => in-memory)
    redis_url: str = ""

    # Server
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
