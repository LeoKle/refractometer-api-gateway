import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from auth.guards import get_admin, get_user
from auth.tokens import InvalidTokenError, JsonWebToken
from users.user import User


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None):
        self._by_id = {u.id: u for u in (users or [])}

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)


@pytest.fixture
def regular_user() -> User:
    return User(email="alice@example.com", name="Alice", admin=False, access=True)


@pytest.fixture
def admin_user() -> User:
    return User(email="bob@example.com", name="Bob", admin=True, access=True)


@pytest.fixture
def no_access_user() -> User:
    return User(email="carol@example.com", name="Carol", admin=False, access=False)


class TestGetUserMissingToken:
    def test_no_cookie_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])

        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=None)

        assert exc_info.value.status_code == 401

    def test_401_response_includes_www_authenticate_header(self, regular_user):
        repo = FakeUserRepository([regular_user])

        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=None)

        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"


class TestGetUserInvalidToken:
    def test_invalid_token_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])

        with (
            patch.object(
                JsonWebToken,
                "decode",
                side_effect=InvalidTokenError,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            get_user(
                user_repository=repo,
                access_token="some-invalid-token",
            )

        assert exc_info.value.status_code == 401

    def test_refresh_token_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])

        refresh_token = JsonWebToken(
            iss="test-issuer",
            sub=regular_user.id,
            aud="test-audience",
            iat=1,
            exp=2,
            token_type="refresh",
            jti=uuid.uuid4(),
        )

        with (
            patch.object(
                JsonWebToken,
                "decode",
                return_value=refresh_token,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            get_user(
                user_repository=repo,
                access_token="some-token",
            )

        assert exc_info.value.status_code == 401


class TestGetUserAuthorization:
    def test_user_not_found_raises_401(self, regular_user):
        repo = FakeUserRepository([])

        token = JsonWebToken(
            iss="test-issuer",
            sub=regular_user.id,
            aud="test-audience",
            iat=1,
            exp=2,
            token_type="access",
            jti=uuid.uuid4(),
        )

        with (
            patch.object(
                JsonWebToken,
                "decode",
                return_value=token,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            get_user(
                user_repository=repo,
                access_token="some-token",
            )

        assert exc_info.value.status_code == 401

    def test_user_without_access_flag_raises_403(self, no_access_user):
        repo = FakeUserRepository([no_access_user])

        token = JsonWebToken(
            iss="test-issuer",
            sub=no_access_user.id,
            aud="test-audience",
            iat=1,
            exp=2,
            token_type="access",
            jti=uuid.uuid4(),
        )

        with (
            patch.object(
                JsonWebToken,
                "decode",
                return_value=token,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            get_user(
                user_repository=repo,
                access_token="some-token",
            )

        assert exc_info.value.status_code == 403

    def test_valid_token_and_authorized_user_returns_user(self, regular_user):
        repo = FakeUserRepository([regular_user])

        token = JsonWebToken(
            iss="test-issuer",
            sub=regular_user.id,
            aud="test-audience",
            iat=1,
            exp=2,
            token_type="access",
            jti=uuid.uuid4(),
        )

        with patch.object(
            JsonWebToken,
            "decode",
            return_value=token,
        ):
            result = get_user(
                user_repository=repo,
                access_token="some-token",
            )

        assert result.id == regular_user.id
        assert result.email == regular_user.email

    def test_admin_user_with_access_returns_user(self, admin_user):
        repo = FakeUserRepository([admin_user])

        token = JsonWebToken(
            iss="test-issuer",
            sub=admin_user.id,
            aud="test-audience",
            iat=1,
            exp=2,
            token_type="access",
            jti=uuid.uuid4(),
        )

        with patch.object(
            JsonWebToken,
            "decode",
            return_value=token,
        ):
            result = get_user(
                user_repository=repo,
                access_token="some-token",
            )

        assert result.id == admin_user.id
        assert result.admin is True


class TestGetAdmin:
    def test_non_admin_raises_403(self, regular_user):
        with pytest.raises(HTTPException) as exc_info:
            get_admin(user=regular_user)

        assert exc_info.value.status_code == 403

    def test_admin_user_is_returned(self, admin_user):
        result = get_admin(user=admin_user)

        assert result.id == admin_user.id
        assert result.admin is True
