import uuid
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError

from auth.generate_jwt import decode_token
from containers.dependencies import DependencyContainer
from settings import get_settings
from users.user import User
from users.user_repository_interface import UserRepositoryInterface


@inject
def get_user(
    user_repository: Annotated[
        UserRepositoryInterface,
        Depends(Provide(DependencyContainer.user_repository)),
    ],
    access_token: Annotated[str | None, Cookie(alias=get_settings().COOKIE_NAME_ACCESS)] = None,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if access_token is None:
        raise credentials_exception

    try:
        payload = decode_token(access_token, expected_type="access")
    except JWTError as exc:
        raise credentials_exception from exc

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = user_repository.get_by_id(uuid.UUID(user_id))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User not found in database",
        )

    if not user.access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return user


def get_admin(
    user: Annotated[User, Depends(get_user)],
) -> User:
    if not user.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return user
