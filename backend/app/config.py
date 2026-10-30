"""Central application settings.

All model IDs and provider settings live here and are overridable through environment
variables or `backend/.env`. Nothing else in the application hardcodes a model ID.
The Featherless API key is optional in this milestone and is never logged or exposed.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _default_database_url() -> str:
    return f"sqlite:///{(BACKEND_DIR / 'data' / 'autoevolve.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default_factory=_default_database_url)

    # Optional until the AI milestone. SecretStr keeps the value out of repr()/logs.
    featherless_api_key: SecretStr | None = None
    featherless_base_url: str = "https://api.featherless.ai/v1"
    # Provisional Generator choice (Prompt 05). Configurable, not frozen.
    featherless_generator_model: str = "Qwen/Qwen2.5-7B-Instruct"
    # No Critic model is approved, so there is deliberately no default.
    featherless_critic_model: str | None = None
    api_timeout_seconds: float = Field(default=60.0, gt=0, le=600)

    @field_validator("featherless_api_key", "featherless_critic_model", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _sqlite_only(cls, value: str) -> str:
        if not value.startswith("sqlite"):
            raise ValueError("DATABASE_URL must be a sqlite URL in this milestone")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
