from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(v1_router)


@api_router.get("", tags=["system"], summary="API index")
async def api_index() -> dict[str, str]:
    return {
        "service": "AI Project Manager API",
        "documentation": "/docs",
        "health": "/api/v1/health/ready",
    }
