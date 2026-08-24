from fastapi import APIRouter

from .api.auth_controller import router

auth_router = APIRouter(prefix="/v1", tags=["Auth"])

auth_router.include_router(router)
