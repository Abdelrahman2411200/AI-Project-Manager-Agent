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
    app_version: str = "0.12.0"
    api_prefix: str = "/api/v1"
    database_url: str = Field(default="sqlite:///./project_manager.db", min_length=1)
    database_pool_size: int = Field(default=20, ge=1, le=100)
    database_max_overflow: int = Field(default=30, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    api_thread_limit: int = Field(default=100, ge=40, le=500)
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
    ai_rate_limit_requests: int = Field(default=10, ge=1, le=1_000)
    ai_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    request_max_body_bytes: int = Field(default=1_048_576, ge=16_384, le=10_485_760)
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    pdf_render_timeout_seconds: int = Field(default=60, ge=5, le=120)
    pdf_max_bytes: int = Field(default=10_485_760, ge=65_536, le=52_428_800)
    pdf_max_concurrency: int = Field(default=2, ge=1, le=8)
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-5.6-terra", min_length=1, max_length=120)
    openai_timeout_seconds: float = Field(default=90.0, ge=1.0, le=300.0)
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_verbosity: Literal["low", "medium", "high"] = "low"
    planning_run_default_token_budget: int = Field(default=50_000, ge=1_000, le=200_000)
    user_daily_run_limit: int = Field(default=10, ge=1, le=1_000)
    user_daily_token_budget: int = Field(default=200_000, ge=1_000, le=10_000_000)
    model_input_price_per_million: float = Field(default=2.50, ge=0, le=1_000)
    model_cached_input_price_per_million: float = Field(default=0.25, ge=0, le=1_000)
    model_output_price_per_million: float = Field(default=15.00, ge=0, le=1_000)
    daily_model_cost_budget_usd: float = Field(default=50.0, gt=0, le=100_000)
    queue_age_alert_seconds: int = Field(default=300, ge=30, le=86_400)
    provider_failure_alert_ratio: float = Field(default=0.20, ge=0, le=1)
    daily_cost_alert_ratio: float = Field(default=0.80, ge=0, le=1)
    otel_service_name: str = Field(default="ai-project-manager-api", min_length=3, max_length=80)
    otel_exporter_otlp_endpoint: str | None = None
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
        if self.user_daily_token_budget < self.planning_run_default_token_budget:
            raise ValueError(
                "USER_DAILY_TOKEN_BUDGET cannot be lower than the default planning run budget."
            )
        return self

    @property
    def cors_origin_strings(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.cors_origins]


@lru_cache
def get_settings() -> Settings:
    return Settings()
