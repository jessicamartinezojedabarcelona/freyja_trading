from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from freyja_backend.core.config import Environment, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: Environment


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
