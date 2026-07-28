"""Guarded reset and deterministic seed command for development/demo databases."""

from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import engine
from app.demo.seed import reset_and_seed_demo

CONFIRMATION = "RESET-DEMO-DATA"
ALLOWED_ENVIRONMENTS = frozenset({"development", "demo", "test"})


def _database_label(database_url: str) -> str:
    parsed = make_url(database_url)
    return (parsed.database or "").casefold()


def assert_demo_reset_allowed(
    *,
    app_env: str,
    database_url: str,
    confirmation: str,
) -> None:
    if confirmation != CONFIRMATION:
        raise RuntimeError(f"Refusing reset: pass --confirm {CONFIRMATION}.")
    if app_env not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            f"Refusing reset: APP_ENV must be development, demo, or test; received {app_env!r}."
        )
    database_label = _database_label(database_url)
    if app_env != "test" and "demo" not in database_label:
        raise RuntimeError(
            "Refusing reset: the database name/path must contain 'demo' outside APP_ENV=test."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Destructively reset a dedicated demo database and load eight fixtures."
    )
    parser.add_argument("--confirm", default="", help=f"Required literal: {CONFIRMATION}")
    parser.add_argument(
        "--password-env",
        default="DEMO_OWNER_PASSWORD",
        help="Environment variable containing the synthetic demo owner's password.",
    )
    arguments = parser.parse_args()
    settings = get_settings()
    try:
        assert_demo_reset_allowed(
            app_env=settings.app_env,
            database_url=settings.database_url,
            confirmation=arguments.confirm,
        )
        password = os.environ.get(arguments.password_env, "")
        if not password:
            raise RuntimeError(
                f"Refusing seed: {arguments.password_env} must contain the demo password."
            )
        summary = reset_and_seed_demo(engine, password=password)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(summary.as_dict(), default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
