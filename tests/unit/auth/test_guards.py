import uuid

import pytest
from fastapi import HTTPException

from auth.generate_jwt import create_access_token, create_refresh_token
from auth.guards import get_admin, get_user
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


class TestGetUserMissingOrMalformedToken:
    def test_no_cookie_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=None)
        assert exc_info.value.status_code == 401

    def test_garbage_token_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token="not-a-real-jwt")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self, regular_user):
        repo = FakeUserRepository([regular_user])
        expired = create_access_token(regular_user, validity_minutes=-1)
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=expired)
        assert exc_info.value.status_code == 401

    def test_401_response_includes_www_authenticate_header(self, regular_user):
        repo = FakeUserRepository([regular_user])
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=None)
        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"


class TestGetUserTokenTypeEnforcement:
    """
    The guard must only accept access tokens, never refresh tokens - even
    though a refresh token is validly signed and unexpired, it's the wrong
    credential for this purpose.
    """

    def test_refresh_token_rejected(self, regular_user):
        repo = FakeUserRepository([regular_user])
        refresh_token = create_refresh_token(regular_user)
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=refresh_token)
        assert exc_info.value.status_code == 401


class TestGetUserPayloadValidation:
    def test_token_without_sub_claim_raises_401(self, regular_user):
        """
        decode_token succeeds (valid signature, valid type) but the
        `sub` claim itself is missing - guards against a token that's
        structurally valid but semantically incomplete.
        """
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        from auth.generate_jwt import ALGORITHM
        from settings import get_settings

        token = jwt.encode(
            {
                "type": "access",
                "exp": datetime.now(UTC) + timedelta(minutes=10),
                # no sub
            },
            get_settings().JWT_SECRET_KEY.get_secret_value(),
            algorithm=ALGORITHM,
        )
        repo = FakeUserRepository([regular_user])
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=token)
        assert exc_info.value.status_code == 401

    def test_malformed_sub_raises(self, regular_user):
        """sub claim present but not a valid UUID -> uuid.UUID() raises ValueError."""
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        from auth.generate_jwt import ALGORITHM
        from settings import get_settings

        token = jwt.encode(
            {
                "sub": "not-a-uuid",
                "type": "access",
                "exp": datetime.now(UTC) + timedelta(minutes=10),
            },
            get_settings().JWT_SECRET_KEY.get_secret_value(),
            algorithm=ALGORITHM,
        )
        repo = FakeUserRepository([regular_user])
        with pytest.raises(ValueError):
            get_user(user_repository=repo, access_token=token)


class TestGetUserAuthorization:
    def test_user_not_found_in_db_raises_500(self, regular_user):
        """Token is valid but the user has since been deleted from the DB."""
        repo = FakeUserRepository([])  # empty - sub won't resolve
        token = create_access_token(regular_user)
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=token)
        assert exc_info.value.status_code == 500

    def test_user_without_access_flag_raises_403(self, no_access_user):
        repo = FakeUserRepository([no_access_user])
        token = create_access_token(no_access_user)
        with pytest.raises(HTTPException) as exc_info:
            get_user(user_repository=repo, access_token=token)
        assert exc_info.value.status_code == 403

    def test_valid_token_and_authorized_user_returns_user(self, regular_user):
        repo = FakeUserRepository([regular_user])
        token = create_access_token(regular_user)
        result = get_user(user_repository=repo, access_token=token)
        assert result.id == regular_user.id
        assert result.email == regular_user.email

    def test_admin_user_with_access_returns_user(self, admin_user):
        repo = FakeUserRepository([admin_user])
        token = create_access_token(admin_user)
        result = get_user(user_repository=repo, access_token=token)
        assert result.id == admin_user.id
        assert result.admin is True


class TestGetAdmin:
    def test_non_admin_raises_403(self, regular_user):
        with pytest.raises(HTTPException) as exc_info:
            get_admin(user=regular_user)
        assert exc_info.value.status_code == 403

    def test_admin_user_is_returned(self, admin_user):
        result = get_admin(user=admin_user)
        assert result is not None, (
            "get_admin() returned None for a valid admin user - missing "
            "`return user` on the success path."
        )
        assert result.id == admin_user.id
        assert result.admin is True
