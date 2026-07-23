from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
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
    app_version: str = "0.3.0"
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
