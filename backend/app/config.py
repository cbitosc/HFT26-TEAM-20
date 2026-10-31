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
    # Per-execution caps. Exceeding either fails the run (LLM_CALL_BUDGET_EXCEEDED / LLM_TOKEN_BUDGET_EXCEEDED)
    # and keeps everything recorded so far. A normal run makes at most 5 calls.
    llm_max_calls_per_execution: int = Field(default=6, ge=1, le=50)
    llm_max_total_tokens_per_execution: int = Field(default=40_000, ge=1000, le=1_000_000)
    # LLM calls (Generator and Critic). Temperature is fixed at 0 in code, not configurable.
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # extra attempts after the first
    llm_backoff_seconds: float = Field(default=1.0, ge=0, le=30)  # doubles each retry
    llm_max_tokens: int = Field(default=2048, ge=64, le=8192)
    generator_max_code_chars: int = Field(default=20_000, ge=100, le=200_000)

    # Candidate-code evaluation (see docs/EVALUATION_ENGINE.md). Running candidate code in a
    # subprocess is NOT a security sandbox.
    evaluation_timeout_seconds: float = Field(default=10.0, gt=0, le=120)  # one interpreter run
    evaluation_total_timeout_seconds: float = Field(default=60.0, gt=0, le=600)  # whole evaluation
    # None = decide from app_env: allowed in development/test, refused in production unless set true.
    allow_unsandboxed_evaluation: bool | None = None

    # Encryption at rest for uploaded hidden tests (app.sealing). A Fernet key, urlsafe-base64 of 32
    # bytes. In production a missing key means uploads are refused; dev/test generate the key file below.
    hidden_suite_key: SecretStr | None = None
    hidden_suite_key_file: str = Field(default_factory=lambda: str(BACKEND_DIR / ".hidden_suite_key"))
    # Browser origins allowed to call the API (comma-separated). No wildcard; credentials stay off.
    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        return self.featherless_api_key is not None and bool(self.featherless_api_key.get_secret_value().strip())

    @property
    def evaluation_execution_allowed(self) -> bool:
        if self.allow_unsandboxed_evaluation is not None:
            return self.allow_unsandboxed_evaluation
        return self.app_env != "production"

    @field_validator("featherless_api_key", "featherless_critic_model", "allow_unsandboxed_evaluation",
                     "hidden_suite_key", mode="before")
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
