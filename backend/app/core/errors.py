from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class ErrorItem(BaseModel):
    field: str | None = None
    code: str
    message: str


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str
    errors: list[ErrorItem] = Field(default_factory=list)
    request_id: str


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        problem = ProblemDetail(
            title="Request failed",
            status=exc.status_code,
            code="http_error",
            detail=str(exc.detail),
            request_id=_request_id(request),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            ErrorItem(
                field=".".join(str(part) for part in item["loc"]),
                code=item["type"],
                message=item["msg"],
            )
            for item in exc.errors()
        ]
        problem = ProblemDetail(
            title="Validation failed",
            status=422,
            code="validation_error",
            detail="One or more request values are invalid.",
            errors=errors,
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=422, content=problem.model_dump())
