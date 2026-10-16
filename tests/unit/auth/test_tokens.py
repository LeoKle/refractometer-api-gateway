import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from auth.tokens import ALGORITHM, InvalidTokenError, JsonWebToken
from settings import get_settings

TEST_SECRET = SecretStr(
    "test-secret-that-is-at-least-64-bytes-long-so-pyjwt-does-not-throw-warnings"
)
TEST_SECRET_RAW = TEST_SECRET.get_secret_value()
TEST_ISSUER = "test-issuer"
TEST_AUDIENCE = "test-audience"
TEST_ACCESS_TTL = 10  # minutes
TEST_REFRESH_TTL = 31  # days


@pytest.fixture(autouse=True)
def pinned_settings(monkeypatch):
    """set settings for tests"""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(settings, "JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "JWT_ACCESS_TOKEN_TTL", TEST_ACCESS_TTL)
    monkeypatch.setattr(settings, "JWT_REFRESH_TOKEN_TTL", TEST_REFRESH_TTL)


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def decode_raw(token: str) -> dict:
    """Decode without going through JsonWebToken.decode(), to inspect claims directly."""
    return jwt.decode(
        token,
        TEST_SECRET_RAW,
        algorithms=[ALGORITHM],
        audience=TEST_AUDIENCE,
    )


def _claims(user_id: uuid.UUID, **overrides) -> dict:
    """A structurally valid claim set, for hand-building forged tokens."""
    now = datetime.now(UTC)
    claims = {
        "iss": TEST_ISSUER,
        "sub": str(user_id),
        "aud": TEST_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "token_type": "access",
    }
    claims.update(overrides)
    return claims


class TestCreate:
    def test_contains_expected_claims(self, user_id):
        token = JsonWebToken.create(user_id, "access", timedelta(minutes=10)).encode()
        payload = decode_raw(token)

        assert payload["sub"] == str(user_id)
        assert payload["token_type"] == "access"
        assert payload["iss"] == TEST_ISSUER
        assert payload["aud"] == TEST_AUDIENCE
        assert "iat" in payload
        assert "exp" in payload

    def test_validity_is_respected(self, user_id):
        before = datetime.now(UTC)
        token = JsonWebToken.create(user_id, "access", timedelta(minutes=1)).encode()
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        delta = exp - before
        assert timedelta(seconds=55) <= delta <= timedelta(seconds=65)

    def test_two_calls_for_same_user_produce_different_tokens(self, user_id):
        """exp/iat differ at minimum, so tokens shouldn't collide."""
        token1 = JsonWebToken.create(user_id, "access", timedelta(minutes=10)).encode()
        time.sleep(1.1)
        token2 = JsonWebToken.create(user_id, "access", timedelta(minutes=10)).encode()
        assert token1 != token2

    def test_different_users_get_different_subs(self):
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        payload_a = decode_raw(
            JsonWebToken.create(user_a, "access", timedelta(minutes=10)).encode()
        )
        payload_b = decode_raw(
            JsonWebToken.create(user_b, "access", timedelta(minutes=10)).encode()
        )

        assert payload_a["sub"] != payload_b["sub"]
        assert payload_a["sub"] == str(user_a)
        assert payload_b["sub"] == str(user_b)

    def test_invalid_token_type_literal_rejected(self, user_id):
        """token_type is Literal["access", "refresh"] - anything else must fail validation."""
        with pytest.raises(ValidationError):
            JsonWebToken.create(user_id, "bogus", timedelta(minutes=10))


class TestAccessToken:
    def test_contains_expected_claims(self, user_id):
        payload = decode_raw(JsonWebToken.access(user_id).encode())

        assert payload["sub"] == str(user_id)
        assert payload["token_type"] == "access"

    def test_default_validity_matches_settings_ttl(self, user_id):
        before = datetime.now(UTC)
        payload = decode_raw(JsonWebToken.access(user_id).encode())
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        expected = before + timedelta(minutes=TEST_ACCESS_TTL)
        assert abs((exp - expected).total_seconds()) < 5


class TestRefreshToken:
    def test_contains_expected_claims(self, user_id):
        payload = decode_raw(JsonWebToken.refresh(user_id).encode())

        assert payload["sub"] == str(user_id)
        assert payload["token_type"] == "refresh"

    def test_default_validity_matches_settings_ttl(self, user_id):
        before = datetime.now(UTC)
        payload = decode_raw(JsonWebToken.refresh(user_id).encode())
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        expected = before + timedelta(minutes=TEST_REFRESH_TTL)
        assert abs((exp - expected).total_seconds()) < 10

    def test_refresh_token_is_distinguishable_from_access_token(self, user_id):
        access = decode_raw(JsonWebToken.access(user_id).encode())
        refresh = decode_raw(JsonWebToken.refresh(user_id).encode())
        assert access["token_type"] != refresh["token_type"]


class TestDecodeHappyPath:
    def test_decodes_valid_access_token(self, user_id):
        decoded = JsonWebToken.decode(JsonWebToken.access(user_id).encode())
        assert decoded.sub == user_id
        assert decoded.token_type == "access"

    def test_decodes_valid_refresh_token(self, user_id):
        decoded = JsonWebToken.decode(JsonWebToken.refresh(user_id).encode())
        assert decoded.token_type == "refresh"

    def test_round_trip_preserves_all_claims(self, user_id):
        original = JsonWebToken.access(user_id)
        decoded = JsonWebToken.decode(original.encode())
        assert decoded == original


class TestDecodeTypeIsCallerResponsibility:
    """decode() no longer takes an expected_type - it accepts any valid token
    regardless of type, so callers must check `.token_type` themselves."""

    def test_decode_succeeds_for_any_valid_type(self, user_id):
        access = JsonWebToken.decode(JsonWebToken.access(user_id).encode())
        refresh = JsonWebToken.decode(JsonWebToken.refresh(user_id).encode())

        assert access.token_type == "access"
        assert refresh.token_type == "refresh"


class TestDecodeTamperResistance:
    def test_expired_token_rejected(self, user_id):
        token = JsonWebToken.create(user_id, "access", timedelta(minutes=-1)).encode()
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(token)

    def test_token_signed_with_wrong_secret_rejected(self, user_id):
        forged = jwt.encode(
            _claims(user_id),
            "a-completely-different-secret-that-is-also-32-bytes-long",
            algorithm=ALGORITHM,
        )
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged)

    def test_tampered_payload_rejected(self, user_id):
        """Flip the payload without re-signing -> must fail."""
        token = JsonWebToken.access(user_id).encode()
        header_b64, payload_b64, sig_b64 = token.split(".")

        corrupted_payload = payload_b64[:-4] + ("AAAA" if payload_b64[-4:] != "AAAA" else "BBBB")
        tampered = f"{header_b64}.{corrupted_payload}.{sig_b64}"

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(tampered)

    def test_alg_none_forgery_rejected(self, user_id):
        """
        Classic 'alg: none' attack. python-jose refuses to *encode* alg=none
        tokens, so the forged token is built by hand the way a real attacker
        would - valid base64/JSON with the signature segment left empty.
        """
        import base64
        import json

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = b64url(json.dumps(_claims(user_id)).encode())
        forged = f"{header}.{payload}."  # empty signature segment

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged)

    def test_garbage_string_rejected(self):
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode("not.a.jwt")

    def test_empty_string_rejected(self):
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode("")

    def test_token_signed_with_different_algorithm_rejected(self, user_id):
        """decode() pins ALGORITHM=HS256 - an HS512 token must not be accepted."""
        forged = jwt.encode(_claims(user_id), TEST_SECRET_RAW, algorithm="HS512")
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged)

    def test_missing_required_claim_rejected(self, user_id):
        """
        A correctly-signed token that's missing a required claim (here: sub)
        must still be rejected as InvalidTokenError, not leak a raw pydantic
        ValidationError past decode()'s error boundary.
        """
        incomplete = {k: v for k, v in _claims(user_id).items() if k != "sub"}
        forged = jwt.encode(incomplete, TEST_SECRET_RAW, algorithm=ALGORITHM)

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged)
