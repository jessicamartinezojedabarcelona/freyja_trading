from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from freyja_backend.api.deps import DatabaseReady
from freyja_backend.core.config import Environment, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: Environment


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Liveness only: reports the process is up, never touches the database.
    Deliberately cannot fail because of an external dependency."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
def get_readiness(database_ready: DatabaseReady) -> ReadinessResponse:
    """Readiness: fails closed (503) if PostgreSQL is not reachable. This is
    the endpoint a deploy platform should point its health check at, so a
    broken database connection blocks traffic from switching to a bad
    instance instead of serving requests that would fail anyway. Never
    reveals connection details, driver errors, or credentials."""
    if not database_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not_ready")
    return ReadinessResponse(status="ready")
