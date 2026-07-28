"""Bounded requests, abuse throttling, timeouts, and browser security headers."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque
from collections.abc import MutableMapping
from http.cookies import SimpleCookie
from threading import Lock
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

SECURITY_HEADERS = {
    b"content-security-policy": (
        b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=()",
    b"referrer-policy": b"no-referrer",
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"cross-origin-resource-policy": b"same-site",
}


class FixedWindowLimiter:
    """Process-local defense-in-depth limiter; the edge remains the global enforcement tier."""

    def __init__(self) -> None:
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check_and_record(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0])))
            events.append(now)
        return None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


ai_request_limiter = FixedWindowLimiter()


class RequestHardeningMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = self._request_id(scope)
        state = scope.setdefault("state", {})
        if isinstance(state, MutableMapping):
            state["request_id"] = request_id
        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.settings.request_max_body_bytes:
            await self._problem(
                scope,
                receive,
                send,
                request_id=request_id,
                status=413,
                code="request_too_large",
                detail="Request body exceeds the configured size limit.",
            )
            return
        retry_after = self._rate_limit(scope)
        if retry_after is not None:
            await self._problem(
                scope,
                receive,
                send,
                request_id=request_id,
                status=429,
                code="rate_limit_exceeded",
                detail="Too many AI workflow requests. Retry later.",
                headers={"Retry-After": str(retry_after)},
            )
            return

        bytes_received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                bytes_received += len(message.get("body", b""))
                if bytes_received > self.settings.request_max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def hardened_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name not in existing:
                        headers.append((name, value))
                if self.settings.app_env == "production":
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        try:
            async with asyncio.timeout(self._processing_timeout(scope)):
                await self.app(scope, limited_receive, hardened_send)
        except TimeoutError:
            if not response_started:
                await self._problem(
                    scope,
                    receive,
                    send,
                    request_id=request_id,
                    status=504,
                    code="request_timeout",
                    detail="The request exceeded the configured processing timeout.",
                )
        except RequestBodyTooLarge:
            if not response_started:
                await self._problem(
                    scope,
                    receive,
                    send,
                    request_id=request_id,
                    status=413,
                    code="request_too_large",
                    detail="Request body exceeds the configured size limit.",
                )

    def _rate_limit(self, scope: Scope) -> int | None:
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method != "POST" or not (path.endswith("/planning-runs") or path.endswith("/reports")):
            return None
        client = scope.get("client")
        address = client[0] if client else "unknown"
        cookie_value = self._session_cookie(scope)
        actor = hashlib.sha256(cookie_value.encode()).hexdigest()[:24] if cookie_value else "public"
        return ai_request_limiter.check_and_record(
            f"{path}:{address}:{actor}",
            limit=self.settings.ai_rate_limit_requests,
            window_seconds=self.settings.ai_rate_limit_window_seconds,
        )

    def _processing_timeout(self, scope: Scope) -> float:
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method == "GET" and "/reports/" in path and path.endswith("/export.pdf"):
            return max(
                self.settings.request_timeout_seconds,
                float(self.settings.pdf_render_timeout_seconds + 5),
            )
        return self.settings.request_timeout_seconds

    def _session_cookie(self, scope: Scope) -> str | None:
        headers = dict(scope.get("headers", []))
        raw = headers.get(b"cookie", b"").decode("latin-1")
        cookie = SimpleCookie()
        cookie.load(raw)
        item = cookie.get(self.settings.session_cookie_name)
        return item.value if item is not None else None

    @staticmethod
    def _request_id(scope: Scope) -> str:
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        return supplied[:128] if supplied else str(uuid4())

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        raw = dict(scope.get("headers", [])).get(b"content-length")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    async def _problem(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        request_id: str,
        status: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse(
            status_code=status,
            content={
                "type": "about:blank",
                "title": "Request failed",
                "status": status,
                "code": code,
                "detail": detail,
                "errors": [],
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id, **(headers or {})},
        )
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name.decode(), value.decode())
        await response(scope, receive, send)


class RequestBodyTooLarge(Exception):
    pass
