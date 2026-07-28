import asyncio

import httpx
from starlette.types import Receive, Scope, Send

from app.core.config import Settings
from app.security.middleware import RequestHardeningMiddleware


async def _slow_app(scope: Scope, receive: Receive, send: Send) -> None:
    await asyncio.sleep(1.1)


async def _slow_success_app(scope: Scope, receive: Receive, send: Send) -> None:
    await asyncio.sleep(1.1)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"%PDF-test"})


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


def test_pdf_export_receives_renderer_timeout_plus_response_grace() -> None:
    settings = Settings(
        request_timeout_seconds=1,
        pdf_render_timeout_seconds=5,
        _env_file=None,
    )
    hardened = RequestHardeningMiddleware(_slow_success_app, settings)

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=hardened)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/api/v1/reports/00000000-0000-4000-8000-000000000001/export.pdf"
            )

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.content == b"%PDF-test"
