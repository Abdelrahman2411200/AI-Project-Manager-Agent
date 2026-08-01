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
    assert settings.ai_provider == "ollama"
    assert settings.ollama_model == "gemma3:4b"
    assert settings.ollama_base_url_string == "http://127.0.0.1:11434"
    assert settings.planning_ai_configured is True
    assert settings.planning_model == "gemma3:4b"
    assert settings.openai_api_key is None
    assert settings.app_version == "0.13.0"
    assert settings.request_max_body_bytes == 1_048_576
    assert settings.database_pool_size + settings.database_max_overflow == 50
    assert settings.api_thread_limit == 100


def test_blank_openai_key_is_unconfigured() -> None:
    settings = Settings(ai_provider="openai", openai_api_key="   ", _env_file=None)
    assert settings.openai_api_key is None
    assert settings.planning_ai_configured is False


def test_production_rejects_local_database_configuration() -> None:
    with pytest.raises(ValidationError, match="Production requires a PostgreSQL DATABASE_URL"):
        Settings(app_env="production", database_url="sqlite:///./unsafe.db", _env_file=None)
