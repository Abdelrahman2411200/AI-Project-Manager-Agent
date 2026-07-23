from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.execution import router as execution_router
from app.api.v1.plans import router as plans_router
from app.api.v1.projects import router as projects_router
from app.api.v1.runs import router as runs_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(execution_router)
router.include_router(plans_router)
router.include_router(projects_router)
router.include_router(runs_router)
