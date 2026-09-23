"""
SkillMesh API — Health Endpoints
GET /health      — Basic liveness check (used by UptimeRobot)
GET /health/db   — Liveness + database connectivity check

These endpoints must NOT expose secrets, credentials, stack traces,
or internal infrastructure details.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import check_db_connection

router = APIRouter(tags=["Health"])
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class HealthDbResponse(HealthResponse):
    database: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns service status. Used by UptimeRobot and load balancers.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="skillmesh-api",
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/health/db",
    response_model=HealthDbResponse,
    summary="Liveness + database check",
    description="Verifies database connectivity in addition to basic liveness.",
)
async def health_db_check() -> HealthDbResponse:
    db_reachable = await check_db_connection()
    db_status = "ok" if db_reachable else "unreachable"
    overall_status = "ok" if db_reachable else "degraded"

    return HealthDbResponse(
        status=overall_status,
        service="skillmesh-api",
        version=settings.app_version,
        environment=settings.environment,
        database=db_status,
    )
