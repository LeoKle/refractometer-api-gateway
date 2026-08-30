import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import JWTError, jwt
from pydantic import SecretStr

from auth.generate_jwt import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from settings import get_settings
from users.user import User

TEST_SECRET = SecretStr("supersecret")
TEST_SECRET_RAW = TEST_SECRET.get_secret_value()


@pytest.fixture(autouse=True)
def pinned_secret(monkeypatch):
    """Every test in this file runs against a known, fixed secret."""
    monkeypatch.setattr(get_settings(), "JWT_SECRET_KEY", TEST_SECRET)


@pytest.fixture
def user() -> User:
    return User(
        id=uuid.uuid4(),
        email="alice@example.com",
        name="Alice",
        admin=False,
        access=True,
    )


def decode_raw(token: str) -> dict:
    """Decode without going through decode_token(), to inspect claims directly."""
    return jwt.decode(token, TEST_SECRET_RAW, algorithms=[ALGORITHM])


class TestCreateAccessToken:
    def test_contains_expected_claims(self, user):
        token = create_access_token(user)
        payload = decode_raw(token)

        assert payload["user_id"] == str(user.id)
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_does_not_leak_admin_or_access_flags_into_claims(self, user):
        token = create_access_token(user)
        payload = decode_raw(token)

        assert "admin" not in payload
        assert "access" not in payload

    def test_default_validity_is_ten_minutes(self, user):
        before = datetime.now(UTC)
        token = create_access_token(user)
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        delta = exp - before
        assert timedelta(minutes=9, seconds=55) <= delta <= timedelta(minutes=10, seconds=5)

    def test_custom_validity_is_respected(self, user):
        before = datetime.now(UTC)
        token = create_access_token(user, validity_minutes=1)
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        delta = exp - before
        assert timedelta(seconds=55) <= delta <= timedelta(seconds=65)

    def test_two_calls_for_same_user_produce_different_tokens(self, user):
        """exp timestamp differs at minimum, so tokens shouldn't collide."""
        token1 = create_access_token(user)
        time.sleep(1.1)
        token2 = create_access_token(user)
        assert token1 != token2

    def test_different_users_get_different_user_ids(self):
        user_a = User(email="a@example.com", name="A")
        user_b = User(email="b@example.com", name="B")

        payload_a = decode_raw(create_access_token(user_a))
        payload_b = decode_raw(create_access_token(user_b))

        assert payload_a["user_id"] != payload_b["user_id"]
        assert payload_a["user_id"] == str(user_a.id)
        assert payload_b["user_id"] == str(user_b.id)


class TestCreateRefreshToken:
    def test_contains_expected_claims(self, user):
        token = create_refresh_token(user)
        payload = decode_raw(token)

        assert payload["user_id"] == str(user.id)
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_default_validity_is_31_days(self, user):
        before = datetime.now(UTC)
        token = create_refresh_token(user)
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        expected = before + timedelta(days=31)
        assert abs((exp - expected).total_seconds()) < 10

    def test_custom_validity_is_respected(self, user):
        before = datetime.now(UTC)
        token = create_refresh_token(user, validity_minutes=60)
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        delta = exp - before
        assert timedelta(minutes=59, seconds=55) <= delta <= timedelta(minutes=60, seconds=5)

    def test_refresh_token_is_distinguishable_from_access_token(self, user):
        access = decode_raw(create_access_token(user))
        refresh = decode_raw(create_refresh_token(user))
        assert access["type"] != refresh["type"]


class TestDecodeTokenHappyPath:
    def test_decodes_valid_access_token(self, user):
        token = create_access_token(user)
        payload = decode_token(token)
        assert payload["user_id"] == str(user.id)
        assert payload["type"] == "access"

    def test_decodes_valid_refresh_token(self, user):
        token = create_refresh_token(user)
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_expected_type_matching_access_passes(self, user):
        token = create_access_token(user)
        payload = decode_token(token, expected_type="access")
        assert payload["type"] == "access"

    def test_expected_type_matching_refresh_passes(self, user):
        token = create_refresh_token(user)
        payload = decode_token(token, expected_type="refresh")
        assert payload["type"] == "refresh"

    def test_expected_type_none_skips_check(self, user):
        """expected_type=None (the default) should accept any valid token type."""
        access = create_access_token(user)
        refresh = create_refresh_token(user)
        assert decode_token(access)["type"] == "access"
        assert decode_token(refresh)["type"] == "refresh"


class TestDecodeTokenTypeEnforcement:
    def test_refresh_token_rejected_when_access_expected(self, user):
        token = create_refresh_token(user)
        with pytest.raises(JWTError):
            decode_token(token, expected_type="access")

    def test_access_token_rejected_when_refresh_expected(self, user):
        token = create_access_token(user)
        with pytest.raises(JWTError):
            decode_token(token, expected_type="refresh")

    def test_error_message_names_both_types(self, user):
        token = create_refresh_token(user)
        with pytest.raises(JWTError, match=r"access.*refresh|refresh.*access"):
            decode_token(token, expected_type="access")

    def test_missing_type_claim_rejected_when_type_expected(self, user):
        forged = jwt.encode(
            {
                "user_id": str(user.id),
                "exp": datetime.now(UTC) + timedelta(minutes=10),
                # no "type" claim at all
            },
            TEST_SECRET_RAW,
            algorithm=ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_token(forged, expected_type="access")


class TestDecodeTokenTamperResistance:
    def test_expired_token_rejected(self, user):
        token = create_access_token(user, validity_minutes=-1)
        with pytest.raises(JWTError):
            decode_token(token)

    def test_token_signed_with_wrong_secret_rejected(self, user):
        forged = jwt.encode(
            {
                "user_id": str(user.id),
                "exp": datetime.now(UTC) + timedelta(minutes=10),
                "type": "access",
            },
            "a-completely-different-secret",
            algorithm=ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_token(forged)

    def test_tampered_payload_rejected(self, user):
        """Flip the user_id in the token body without re-signing -> must fail."""
        token = create_access_token(user)
        header_b64, payload_b64, sig_b64 = token.split(".")

        # Corrupt the payload segment (breaks both base64 content and signature match).
        corrupted_payload = payload_b64[:-4] + ("AAAA" if payload_b64[-4:] != "AAAA" else "BBBB")
        tampered = f"{header_b64}.{corrupted_payload}.{sig_b64}"

        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_alg_none_forgery_rejected(self, user):
        """
        Classic 'alg: none' attack - decode_token pins ALGORITHM=HS256, so
        this must fail. Note: python-jose refuses to *encode* alg=none
        tokens (raises JWSError at construction time), so the forged token
        has to be built by hand the way a real attacker would - a token
        signed with nothing is still valid base64/JSON, it just skips the
        signature segment entirely.
        """
        import base64
        import json

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = b64url(
            json.dumps({
                "user_id": str(user.id),
                "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
                "type": "access",
            }).encode()
        )
        forged = f"{header}.{payload}."  # empty signature segment

        with pytest.raises(JWTError):
            decode_token(forged)

    def test_garbage_string_rejected(self):
        with pytest.raises(JWTError):
            decode_token("not.a.jwt")

    def test_empty_string_rejected(self):
        with pytest.raises(JWTError):
            decode_token("")

    def test_token_signed_with_different_algorithm_rejected(self, user):
        """
        If someone ever generates a token with e.g. HS512, decode_token
        (pinned to HS256 via ALGORITHM) must not silently accept it.
        """
        forged = jwt.encode(
            {
                "user_id": str(user.id),
                "exp": datetime.now(UTC) + timedelta(minutes=10),
                "type": "access",
            },
            TEST_SECRET_RAW,
            algorithm="HS512",
        )
        with pytest.raises(JWTError):
            decode_token(forged)
