"""Reference-deployment API load gate for live Uvicorn and PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import statistics
import time
from collections.abc import Callable
from uuid import uuid4

import httpx
import uvicorn

from app.auth.security import hash_password
from app.db.models.identity import User
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Measured request rounds; p95 is calculated over every sample.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Uvicorn workers in the reference API deployment.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a disposable Uvicorn process for a self-contained live network gate.",
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


async def run(
    base_url: str,
    concurrency: int,
    rounds: int,
) -> dict[str, float | int | bool]:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if rounds < 1:
        raise ValueError("rounds must be positive")
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
        reads: list[float] = []
        writes: list[float] = []
        for _ in range(rounds):
            reads.extend(
                await timed_requests(
                    client,
                    "GET",
                    "/api/v1/usage/quota",
                    concurrency,
                    expected_status=200,
                )
            )
            writes.extend(
                await timed_requests(
                    client,
                    "POST",
                    "/api/v1/projects",
                    concurrency,
                    payload=project_payload,
                    expected_status=201,
                )
            )
    read_p95 = p95(reads)
    write_p95 = p95(writes)
    return {
        "concurrency": concurrency,
        "rounds": rounds,
        "read_samples": len(reads),
        "write_samples": len(writes),
        "read_p95_ms": round(read_p95, 3),
        "write_p95_ms": round(write_p95, 3),
        "passed": read_p95 < 300 and write_p95 < 600,
    }


async def run_with_optional_server(
    base_url: str,
    concurrency: int,
    rounds: int,
    workers: int,
    *,
    serve: bool,
) -> dict[str, float | int | bool]:
    if workers < 1:
        raise ValueError("workers must be positive")
    if not serve:
        return await run(base_url, concurrency, rounds)
    parsed = httpx.URL(base_url)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.port is None:
        raise ValueError("--serve requires an explicit localhost port.")
    process = multiprocessing.get_context("spawn").Process(
        target=serve_app,
        args=(str(parsed.host), parsed.port, workers),
    )
    process.start()
    try:
        await wait_until_ready(base_url, process)
        result = await run(base_url, concurrency, rounds)
        result["server_workers"] = workers
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)


def serve_app(host: str, port: int, workers: int) -> None:
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level="warning",
        access_log=False,
    )


async def wait_until_ready(
    base_url: str,
    process: multiprocessing.Process,
) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=1) as client:
        for _ in range(200):
            if not process.is_alive():
                raise RuntimeError(
                    f"Reference Uvicorn process exited with code {process.exitcode}."
                )
            try:
                response = await client.get("/api/v1/health/live")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
    raise RuntimeError("Reference Uvicorn process did not become ready.")


def main() -> int:
    args = parse_args()
    result = asyncio.run(
        run_with_optional_server(
            args.base_url,
            args.concurrency,
            args.rounds,
            args.workers,
            serve=args.serve,
        )
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
