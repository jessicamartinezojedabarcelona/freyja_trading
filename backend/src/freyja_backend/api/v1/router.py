from fastapi import APIRouter

from freyja_backend.api.v1.endpoints import auth, health

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
