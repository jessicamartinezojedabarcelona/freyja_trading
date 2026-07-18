from fastapi import FastAPI

from freyja_backend.api.v1.router import router as api_v1_router
from freyja_backend.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
