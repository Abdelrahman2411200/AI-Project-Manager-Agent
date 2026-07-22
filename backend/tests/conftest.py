import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CORS_ORIGINS"] = '["http://testserver"]'
os.environ["SESSION_HASH_SECRET"] = "test-session-secret-at-least-32-characters"

import pytest
from sqlalchemy import delete

from app.auth.security import login_rate_limiter
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    login_rate_limiter.clear()
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))
