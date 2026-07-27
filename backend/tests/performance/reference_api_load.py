"""Reference-deployment API load gate for live Uvicorn and PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections.abc import Callable
from uuid import uuid4

import httpx
import uvicorn

from app.auth.security import hash_password
from app.db.models.identity import User
from app.db.session import SessionLocal
from app.main import app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start an in-process Uvicorn server for a self-contained live network gate.",
    )
    return parser.parse_args()


def seed_owner() -> tuple[str, str]:
    email = f"load-{uuid4()}@example.com"
    password = f"Load-test-{uuid4()}!"
    with SessionLocal() as session:
        session.add(User(email=email, password_hash=hash_password(password)))
        session.commit()
    return email, password


async def timed_requests(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    concurrency: int,
    *,
    payload: Callable[[int], dict[str, object]] | None = None,
    expected_status: int,
) -> list[float]:
    async def one(index: int) -> float:
        started = time.perf_counter()
        response = await client.request(
            method,
            path,
            json=payload(index) if payload is not None else None,
        )
        if response.status_code != expected_status:
            raise RuntimeError(
                f"{method} {path} returned {response.status_code}: {response.text[:200]}"
            )
        return (time.perf_counter() - started) * 1_000

    return await asyncio.gather(*(one(index) for index in range(concurrency)))


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def project_payload(index: int) -> dict[str, object]:
    return {
        "name": f"Reference load project {index}",
        "goal": "Measure an authenticated PostgreSQL write under reference concurrency.",
        "timezone": "Africa/Cairo",
    }


async def run(base_url: str, concurrency: int) -> dict[str, float | int | bool]:
    email, password = seed_owner()
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        login = await client.post(
            "/api/v1/auth/session",
            json={"email": email, "password": password},
            headers={"Origin": base_url},
        )
        if login.status_code != 200:
            raise RuntimeError(f"Load owner login failed: {login.status_code} {login.text}")
        client.headers.update(
            {
                "Origin": base_url,
                "X-CSRF-Token": str(login.json()["csrf_token"]),
            }
        )
        # Establish the reference deployment's connection/thread pools before
        # the measured steady-state window. Cold-start readiness is monitored
        # separately from the API latency SLO.
        await timed_requests(
            client,
            "GET",
            "/api/v1/usage/quota",
            concurrency,
            expected_status=200,
        )
        warmup = await client.post("/api/v1/projects", json=project_payload(-1))
        if warmup.status_code != 201:
            raise RuntimeError(
                f"Load warm-up write failed: {warmup.status_code} {warmup.text[:200]}"
            )
        reads = await timed_requests(
            client,
            "GET",
            "/api/v1/usage/quota",
            concurrency,
            expected_status=200,
        )
        writes = await timed_requests(
            client,
            "POST",
            "/api/v1/projects",
            concurrency,
            payload=project_payload,
            expected_status=201,
        )
    read_p95 = p95(reads)
    write_p95 = p95(writes)
    return {
        "concurrency": concurrency,
        "read_p95_ms": round(read_p95, 3),
        "write_p95_ms": round(write_p95, 3),
        "passed": read_p95 < 300 and write_p95 < 600,
    }


async def run_with_optional_server(
    base_url: str,
    concurrency: int,
    *,
    serve: bool,
) -> dict[str, float | int | bool]:
    if not serve:
        return await run(base_url, concurrency)
    parsed = httpx.URL(base_url)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.port is None:
        raise ValueError("--serve requires an explicit localhost port.")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=str(parsed.host),
            port=parsed.port,
            log_level="warning",
            access_log=False,
        )
    )
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError("Reference Uvicorn server stopped before becoming ready.")
            await asyncio.sleep(0.05)
        if not server.started:
            raise RuntimeError("Reference Uvicorn server did not become ready.")
        return await run(base_url, concurrency)
    finally:
        server.should_exit = True
        await server_task


def main() -> int:
    args = parse_args()
    result = asyncio.run(
        run_with_optional_server(
            args.base_url,
            args.concurrency,
            serve=args.serve,
        )
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
