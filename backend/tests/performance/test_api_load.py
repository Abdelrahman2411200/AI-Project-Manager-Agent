import asyncio
import statistics
import time

import httpx

from app.main import app


async def _request_latencies(method: str, path: str, count: int) -> list[float]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        async def one() -> float:
            started = time.perf_counter()
            response = await client.request(method, path)
            assert response.status_code in {200, 401}
            return (time.perf_counter() - started) * 1_000

        return await asyncio.gather(*(one() for _ in range(count)))


def _p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def test_in_process_security_and_routing_overhead_at_fifty_concurrent() -> None:
    # SQLite is explicitly single-worker and cannot prove concurrent persistence.
    # This gate isolates ASGI/security/routing overhead; reference_api_load.py runs
    # authenticated reads and real writes against live Uvicorn and PostgreSQL.
    reads = asyncio.run(_request_latencies("GET", "/api/v1/health/live", 50))
    writes = asyncio.run(_request_latencies("POST", "/api/v1/projects", 50))
    assert _p95(reads) < 300
    assert _p95(writes) < 600
