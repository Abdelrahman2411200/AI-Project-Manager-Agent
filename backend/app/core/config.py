from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Project Manager API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_version: str = "0.6.0"
    api_prefix: str = "/api/v1"
    database_url: str = Field(default="sqlite:///./project_manager.db", min_length=1)
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    session_hash_secret: SecretStr = SecretStr("development-only-session-secret")
    session_ttl_hours: int = Field(default=24 * 7, ge=1, le=24 * 30)
    session_cookie_name: str = "apm_session"
    csrf_cookie_name: str = "apm_csrf"
    cookie_secure: bool = False
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-5.6-terra", min_length=1, max_length=120)
    openai_timeout_seconds: float = Field(default=90.0, ge=1.0, le=300.0)
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_verbosity: Literal["low", "medium", "high"] = "low"
    planning_run_default_token_budget: int = Field(default=50_000, ge=1_000, le=200_000)
    job_heartbeat_seconds: int = Field(default=15, ge=1, le=60)
    job_lease_seconds: int = Field(default=90, ge=10, le=600)
    job_poll_seconds: float = Field(default=1.0, ge=0.1, le=30.0)

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def empty_openai_key_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_production_database(self) -> "Settings":
        if self.app_env == "production" and not self.database_url.startswith("postgresql"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL.")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("Production requires secure session cookies.")
        if self.app_env == "production" and (
            self.session_hash_secret.get_secret_value() == "development-only-session-secret"
            or len(self.session_hash_secret.get_secret_value()) < 32
        ):
            raise ValueError("Production requires a unique SESSION_HASH_SECRET of 32+ characters.")
        return self

    @property
    def cors_origin_strings(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.cors_origins]


@lru_cache
def get_settings() -> Settings:
    return Settings()
