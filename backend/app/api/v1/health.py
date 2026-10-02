"""Liveness (`/health`) and readiness (`/health/ready`) endpoints."""
from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.redis import check_redis
from app.db.session import check_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(
        status="ok", app=s.app_name, version=s.app_version, environment=s.environment
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    checks = {
        "database": "ok" if await check_database() else "unavailable",
        "redis": "ok" if await check_redis() else "unavailable",
    }
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if ok else "degraded", checks=checks)
