import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_defaults_are_safe_for_local_use() -> None:
    settings = Settings(
        app_env="development",
        database_url="sqlite:///./local.db",
        cors_origins=["http://localhost:5173"],
        _env_file=None,
    )

    assert settings.app_env == "development"
    assert settings.database_url.startswith("sqlite")
    assert settings.cors_origin_strings == ["http://localhost:5173"]
    assert settings.openai_model == "gpt-5.6-terra"
    assert settings.openai_api_key is None
    assert settings.app_version == "0.12.0"
    assert settings.request_max_body_bytes == 1_048_576
    assert settings.database_pool_size + settings.database_max_overflow == 50
    assert settings.api_thread_limit == 100


def test_blank_openai_key_is_unconfigured() -> None:
    settings = Settings(openai_api_key="   ", _env_file=None)
    assert settings.openai_api_key is None


def test_production_rejects_local_database_configuration() -> None:
    with pytest.raises(ValidationError, match="Production requires a PostgreSQL DATABASE_URL"):
        Settings(app_env="production", database_url="sqlite:///./unsafe.db", _env_file=None)
