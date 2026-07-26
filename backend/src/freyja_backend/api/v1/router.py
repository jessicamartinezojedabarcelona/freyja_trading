from fastapi import APIRouter

from freyja_backend.api.v1.endpoints import auth, capabilities, catalog, execution_contexts, health

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(catalog.router)
router.include_router(capabilities.router)
router.include_router(execution_contexts.router)
