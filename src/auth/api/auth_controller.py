from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from auth.api.auth_responses import UserInfoResponse
from auth.guards import get_user
from auth.interfaces.auth_service_interface import (
    AuthenticationError,
    AuthModel,
    AuthProviderUnavailableError,
    AuthServiceInterface,
    InvalidLoginTransactionError,
    InvalidSessionError,
    LoginResult,
)
from auth.oauth_transaction import (
    TRANSACTION_TTL_MINUTES,
)
from containers.dependencies import DependencyContainer
from settings import get_settings
from users.user import User
from users.user_repository_interface import UserRepositoryInterface

router = APIRouter(prefix="/auth")

TRANSACTION_COOKIE_PATH = "/api/v1/auth"


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """Helper to set both auth cookies consistently."""
    cookie_defaults = {
        "httponly": True,
        "secure": get_settings().COOKIES_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(get_settings().COOKIE_NAME_ACCESS, access, **cookie_defaults)
    response.set_cookie(get_settings().COOKIE_NAME_REFRESH, refresh, **cookie_defaults)


def _set_transaction_cookie(response: Response, transaction: str) -> None:
    response.set_cookie(
        get_settings().COOKIE_NAME_OAUTH_TRANSACTION,
        transaction,
        httponly=True,
        secure=get_settings().COOKIES_SECURE,
        samesite="lax",
        path=TRANSACTION_COOKIE_PATH,
        max_age=TRANSACTION_TTL_MINUTES * 60,
    )


def _clear_transaction_cookie(response: Response) -> None:
    response.delete_cookie(
        get_settings().COOKIE_NAME_OAUTH_TRANSACTION, path=TRANSACTION_COOKIE_PATH
    )


@router.get("/login")
@inject
def login(
    auth_service: Annotated[
        AuthServiceInterface,
        Depends(Provide[DependencyContainer.auth_service]),
    ],
    redirect_to: str | None = None,
):
    login_start = auth_service.start_login(redirect_to)

    response = RedirectResponse(login_start.url)
    _set_transaction_cookie(response, login_start.transaction)

    return response


@router.get("/callback")
@inject
def auth_callback(
    code: str,
    auth_service: Annotated[
        AuthServiceInterface,
        Depends(Provide[DependencyContainer.auth_service]),
    ],
    state: str | None = None,
    oauth_transaction: Annotated[
        str | None, Cookie(alias=get_settings().COOKIE_NAME_OAUTH_TRANSACTION)
    ] = None,
):
    try:
        login_result: LoginResult = auth_service.complete_login(code, state, oauth_transaction)
    except InvalidLoginTransactionError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login failed",
        ) from None
    except AuthProviderUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login provider unavailable",
        ) from None
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication failed",
        ) from None

    response = RedirectResponse(login_result.redirect_to)

    _set_auth_cookies(response, login_result.access_token, login_result.refresh_token)
    _clear_transaction_cookie(response)

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
    auth_service: Annotated[
        AuthServiceInterface,
        Depends(Provide[DependencyContainer.auth_service]),
    ],
    refresh_token: Annotated[str | None, Cookie(alias=get_settings().COOKIE_NAME_REFRESH)] = None,
):
    try:
        tokens: AuthModel = auth_service.refresh(refresh_token)
    except InvalidSessionError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to refresh tokens"
        ) from None

    _set_auth_cookies(
        response,
        tokens.access,
        tokens.refresh,
    )


@router.post("/logout")
@inject
def logout(
    response: Response,
    auth_service: Annotated[
        AuthServiceInterface, Depends(Provide[DependencyContainer.auth_service])
    ],
    refresh_token: Annotated[str | None, Cookie(alias=get_settings().COOKIE_NAME_REFRESH)] = None,
):
    auth_service.logout(refresh_token)
    response.delete_cookie(get_settings().COOKIE_NAME_ACCESS, path="/")
    response.delete_cookie(get_settings().COOKIE_NAME_REFRESH, path="/")
