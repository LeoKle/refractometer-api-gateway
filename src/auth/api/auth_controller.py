import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from jose import JWTError

from auth.api.auth_responses import UserInfoResponse
from auth.generate_jwt import create_access_token, create_refresh_token, decode_token
from auth.guards import get_user
from auth.interfaces.auth_service_interface import AuthModel, AuthServiceInterface
from containers.dependencies import DependencyContainer
from settings import settings
from users.user import User
from users.user_repository_interface import UserRepositoryInterface

router = APIRouter(prefix="/auth")


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """Helper to set both auth cookies consistently."""
    cookie_defaults = {
        "httponly": True,
        "secure": settings.COOKIES_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(settings.COOKIE_NAME_ACCESS, access, **cookie_defaults)
    response.set_cookie(settings.COOKIE_NAME_REFRESH, refresh, **cookie_defaults)


@router.get("/login")
@inject
def login(
    auth_service: Annotated[
        AuthServiceInterface,
        Depends(Provide[DependencyContainer.auth_service]),
    ],
    state: str | None = None,
):
    url = auth_service.get_redirect_url(state)
    return RedirectResponse(url)


@router.get("/callback")
@inject
def auth_callback(
    code: str,
    response: Response,
    auth_service: Annotated[
        AuthServiceInterface,
        Depends(Provide[DependencyContainer.auth_service]),
    ],
    state: str | None = None,
):
    token: AuthModel = auth_service.authenticate(code)

    response = RedirectResponse(state) if state else RedirectResponse("/")

    _set_auth_cookies(response, token.access, token.refresh)

    return response


@router.get("/user")
def get_user_endpoint(
    user: Annotated[User, Depends(get_user)],
) -> UserInfoResponse:
    return UserInfoResponse(
        user_id=str(user.id), name=user.name, access=user.access, admin=user.admin
    )


@router.post(
    "/refresh",
)
@inject
def auth_refresh(
    response: Response,
    user_repository: Annotated[
        UserRepositoryInterface,
        Depends(Provide[DependencyContainer.user_repository]),
    ],
    refresh_token: Annotated[str | None, Cookie(alias=settings.COOKIE_NAME_REFRESH)] = None,
):
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from e

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        ) from None

    user = user_repository.get_by_id(user_uuid)

    if not user.access:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access")

    _set_auth_cookies(response, create_access_token(user), create_refresh_token(user))


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.COOKIE_NAME_ACCESS, path="/")
    response.delete_cookie(settings.COOKIE_NAME_REFRESH, path="/")
