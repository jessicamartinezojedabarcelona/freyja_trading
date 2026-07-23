from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from freyja_backend.api.v1.router import router as api_v1_router
from freyja_backend.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    # Added last, so Starlette (which wraps middleware in reverse registration
    # order) makes it the outermost layer: every request — including a CORS
    # preflight OPTIONS, which CORSMiddleware would otherwise answer directly
    # without ever calling further inward — hits the Host check first.
    # Independent of any forwarded-header trust decision (this app does not
    # trust X-Forwarded-* — see get_client_ip in api/deps.py).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
