import secrets
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
from auth.oauth_transaction import (
    TRANSACTION_TTL_MINUTES,
    OAuthTransaction,
    decode_transaction,
    encode_transaction,
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


def _set_transaction_cookie(response: Response, transaction: OAuthTransaction) -> None:
    response.set_cookie(
        get_settings().COOKIE_NAME_OAUTH_TRANSACTION,
        encode_transaction(transaction),
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
    url, transaction = auth_service.start_login(redirect_to)

    response = RedirectResponse(url)
    _set_transaction_cookie(response, transaction)

    return response


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
    oauth_transaction: Annotated[
        str | None, Cookie(alias=get_settings().COOKIE_NAME_OAUTH_TRANSACTION)
    ] = None,
):
    if oauth_transaction is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth transaction",
        )

    transaction = decode_transaction(oauth_transaction)

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth transaction",
        )

    if not state or not secrets.compare_digest(state, transaction.state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    token: AuthModel = auth_service.authenticate(code, transaction.code_verifier)

    response = RedirectResponse(transaction.redirect_to)

    _set_auth_cookies(response, token.access, token.refresh)
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
    refresh_token: Annotated[str | None, Cookie(alias=get_settings().COOKIE_NAME_REFRESH)] = None,
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

    user_id = payload.get("sub")

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
    response.delete_cookie(get_settings().COOKIE_NAME_ACCESS, path="/")
    response.delete_cookie(get_settings().COOKIE_NAME_REFRESH, path="/")
