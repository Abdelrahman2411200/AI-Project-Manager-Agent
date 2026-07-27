import asyncio

import httpx
from starlette.types import Receive, Scope, Send

from app.core.config import Settings
from app.security.middleware import RequestHardeningMiddleware


async def _slow_app(scope: Scope, receive: Receive, send: Send) -> None:
    await asyncio.sleep(1.1)


def test_injected_handler_stall_returns_safe_correlated_timeout() -> None:
    settings = Settings(request_timeout_seconds=1, _env_file=None)
    hardened = RequestHardeningMiddleware(_slow_app, settings)

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=hardened)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/stalled",
                headers={"X-Request-ID": "failure-injection-timeout"},
            )

    response = asyncio.run(request())
    assert response.status_code == 504
    assert response.json() == {
        "type": "about:blank",
        "title": "Request failed",
        "status": 504,
        "code": "request_timeout",
        "detail": "The request exceeded the configured processing timeout.",
        "errors": [],
        "request_id": "failure-injection-timeout",
    }
    assert response.headers["X-Request-ID"] == "failure-injection-timeout"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
