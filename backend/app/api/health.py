from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import check_database_connection

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]
    service: str
    version: str
    environment: str
    checks: dict[str, Literal["ok"]]


@router.get("/live", response_model=HealthResponse, summary="Process liveness")
async def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        checks={"process": "ok"},
    )


@router.get("/ready", response_model=HealthResponse, summary="Service readiness")
async def readiness(request: Request) -> HealthResponse:
    if not getattr(request.app.state, "is_ready", False) or not check_database_connection():
        raise HTTPException(status_code=503, detail="Service startup is not complete.")
    settings = get_settings()
    return HealthResponse(
        status="ready",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        checks={"configuration": "ok", "database": "ok"},
    )
