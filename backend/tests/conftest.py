import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CORS_ORIGINS"] = '["http://testserver"]'
os.environ["SESSION_HASH_SECRET"] = "test-session-secret-at-least-32-characters"

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, update

from app.auth.security import login_rate_limiter
from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine
from app.security.middleware import ai_request_limiter


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    login_rate_limiter.clear()
    ai_request_limiter.clear()
    yield
    with engine.begin() as connection:
        plan_versions = Base.metadata.tables.get("plan_versions")
        if plan_versions is not None:
            connection.execute(update(plan_versions).values(based_on_id=None))
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))


@pytest.fixture(autouse=True)
def configured_test_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "openai")
    monkeypatch.setattr(
        get_settings(),
        "openai_api_key",
        SecretStr("test-provider-key"),
    )
