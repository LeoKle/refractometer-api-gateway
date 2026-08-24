from fastapi import APIRouter

from auth.auth_router import auth_router

main_router = APIRouter(prefix="/api")
main_router.include_router(auth_router)
