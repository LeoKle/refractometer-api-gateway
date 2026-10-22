from fastapi import APIRouter

from auth.auth_router import auth_router

from .image.image_controller import image_router
from .result.result_controller import result_router

main_router = APIRouter(prefix="/api")
main_router.include_router(auth_router)
main_router.include_router(image_router)
main_router.include_router(result_router)
