"""Deterministic, non-production university demonstration data."""

from app.demo.seed import (
    DEMO_EMAIL,
    DEMO_FIXTURE_NAMES,
    DemoSeedSummary,
    load_demo_fixtures,
    reset_and_seed_demo,
    seed_demo_data,
)

__all__ = [
    "DEMO_EMAIL",
    "DEMO_FIXTURE_NAMES",
    "DemoSeedSummary",
    "load_demo_fixtures",
    "reset_and_seed_demo",
    "seed_demo_data",
]
