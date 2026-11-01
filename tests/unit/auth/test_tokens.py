import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pydantic import SecretStr, ValidationError

from auth.tokens import InvalidTokenError, JsonWebToken
from settings import get_settings


def _ed25519_pair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


TEST_ALGORITHM = "HS256"
TEST_PRIVATE_KEY = SecretStr(
    "test-secret-that-is-at-least-64-bytes-long-so-pyjwt-does-not-throw-warnings"
)
TEST_PRIVATE_KEY_RAW = TEST_PRIVATE_KEY.get_secret_value()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.get_secret_value()
TEST_ISSUER = "test-issuer"
TEST_AUDIENCE = "test-audience"
TEST_ACCESS_TTL = 10  # minutes
TEST_REFRESH_TTL = 31  # days


@pytest.fixture(autouse=True)
def pinned_settings(monkeypatch):
    """set settings for tests"""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", TEST_ALGORITHM)
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", TEST_PUBLIC_KEY)
    monkeypatch.setattr(settings, "JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "JWT_ACCESS_TOKEN_TTL", TEST_ACCESS_TTL)
    monkeypatch.setattr(settings, "JWT_REFRESH_TOKEN_TTL", TEST_REFRESH_TTL)


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture(params=["access", "refresh"])
def token_type(request) -> str:
    """Runs the test once per token type."""
    return request.param


def decode_raw(token: str) -> dict:
    """Decode without going through JsonWebToken.decode(), to inspect claims directly."""
    return jwt.decode(
        token,
        TEST_PUBLIC_KEY,
        algorithms=[TEST_ALGORITHM],
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
        "jti": str(uuid.uuid4()),
        "fid": str(uuid.uuid4()),
        "token_type": "access",
    }
    claims.update(overrides)
    return claims


def _sign(claims: dict) -> str:
    return jwt.encode(claims, TEST_PRIVATE_KEY_RAW, algorithm=TEST_ALGORITHM)


class TestHandBuiltClaimsAreValid:
    """Positive control for the forged-token tests below. Each of those expects
    InvalidTokenError, so if `_claims` stopped producing a valid token (say a
    new required claim was added), they would all keep passing for the wrong
    reason. This test fails instead."""

    def test_hand_built_token_is_accepted(self, user_id, token_type):
        decoded = JsonWebToken.decode(_sign(_claims(user_id, token_type=token_type)), token_type)

        assert decoded.sub == user_id
        assert decoded.token_type == token_type


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
        assert uuid.UUID(payload["jti"])  # present and a valid UUID string
        assert uuid.UUID(payload["fid"])

    def test_validity_is_respected(self, user_id):
        before = datetime.now(UTC)
        token = JsonWebToken.create(user_id, "access", timedelta(minutes=1)).encode()
        payload = decode_raw(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        delta = exp - before
        assert timedelta(seconds=55) <= delta <= timedelta(seconds=65)

    def test_two_calls_for_same_user_produce_different_tokens(self, user_id):
        """Unique jti means tokens never collide, even within the same second."""
        t1 = JsonWebToken.create(user_id, "access", timedelta(minutes=10))
        t2 = JsonWebToken.create(user_id, "access", timedelta(minutes=10))

        assert t1.jti != t2.jti
        assert t1.encode() != t2.encode()

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

    def test_without_family_id_starts_a_new_family(self, user_id):
        t1 = JsonWebToken.create(user_id, "refresh", timedelta(minutes=10))
        t2 = JsonWebToken.create(user_id, "refresh", timedelta(minutes=10))

        assert t1.fid != t2.fid

    def test_given_family_id_is_used(self, user_id):
        fid = uuid.uuid4()
        token = JsonWebToken.create(user_id, "refresh", timedelta(minutes=10), family_id=fid)

        assert token.fid == fid
        assert decode_raw(token.encode())["fid"] == str(fid)


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

    def test_given_family_id_is_used(self, user_id):
        fid = uuid.uuid4()
        assert JsonWebToken.access(user_id, family_id=fid).fid == fid


class TestRefreshToken:
    def test_contains_expected_claims(self, user_id):
        payload = decode_raw(JsonWebToken.refresh(user_id).encode())

        assert payload["sub"] == str(user_id)
        assert payload["token_type"] == "refresh"

    def test_default_validity_matches_settings_ttl(self, user_id):
        before = datetime.now(UTC)
        payload = decode_raw(JsonWebToken.refresh(user_id).encode())
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

        expected = before + timedelta(days=TEST_REFRESH_TTL)
        assert abs((exp - expected).total_seconds()) < 10

    def test_refresh_token_is_distinguishable_from_access_token(self, user_id):
        access = decode_raw(JsonWebToken.access(user_id).encode())
        refresh = decode_raw(JsonWebToken.refresh(user_id).encode())
        assert access["token_type"] != refresh["token_type"]

    def test_given_family_id_is_used(self, user_id):
        fid = uuid.uuid4()
        assert JsonWebToken.refresh(user_id, family_id=fid).fid == fid


class TestFamily:
    def test_login_starts_a_family_shared_by_the_token_pair(self, user_id):
        """Login pattern: create the refresh token, reuse its fid for the access token."""
        refresh = JsonWebToken.refresh(user_id)
        access = JsonWebToken.access(user_id, family_id=refresh.fid)

        assert access.fid == refresh.fid
        assert access.jti != refresh.jti

    def test_rotation_keeps_fid_but_changes_jti(self, user_id):
        first = JsonWebToken.refresh(user_id)
        rotated = JsonWebToken.refresh(user_id, family_id=first.fid)

        assert rotated.fid == first.fid
        assert rotated.jti != first.jti

    def test_separate_logins_get_separate_families(self, user_id):
        assert JsonWebToken.refresh(user_id).fid != JsonWebToken.refresh(user_id).fid


class TestDecodeHappyPath:
    def test_decodes_valid_access_token(self, user_id):
        decoded = JsonWebToken.decode(JsonWebToken.access(user_id).encode(), "access")
        assert decoded.sub == user_id
        assert decoded.token_type == "access"

    def test_decodes_valid_refresh_token(self, user_id):
        decoded = JsonWebToken.decode(JsonWebToken.refresh(user_id).encode(), "refresh")
        assert decoded.token_type == "refresh"

    def test_round_trip_preserves_all_claims(self, user_id, token_type):
        original = JsonWebToken.create(user_id, token_type, timedelta(minutes=10))
        decoded = JsonWebToken.decode(original.encode(), token_type)
        assert decoded == original

    def test_round_trip_preserves_jti_and_fid(self, user_id, token_type):
        original = JsonWebToken.create(
            user_id, token_type, timedelta(minutes=10), family_id=uuid.uuid4()
        )
        decoded = JsonWebToken.decode(original.encode(), token_type)

        assert decoded.jti == original.jti
        assert decoded.fid == original.fid


class TestDecodeExpectedType:
    """expected_type is required and any other token type is rejected."""

    def test_refresh_token_rejected_as_access(self, user_id):
        token = JsonWebToken.refresh(user_id).encode()
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(token, expected_type="access")

    def test_access_token_rejected_as_refresh(self, user_id):
        token = JsonWebToken.access(user_id).encode()
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(token, expected_type="refresh")

    def test_expected_type_is_required(self, user_id):
        token = JsonWebToken.access(user_id).encode()
        with pytest.raises(TypeError):
            JsonWebToken.decode(token)  # type: ignore[call-arg]

    def test_invalid_token_still_rejected_with_expected_type(self, token_type):
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode("not.a.jwt", expected_type=token_type)


class TestDecodeTamperResistance:
    def test_expired_token_rejected(self, user_id, token_type):
        token = JsonWebToken.create(user_id, token_type, timedelta(minutes=-1)).encode()
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(token, token_type)

    def test_token_signed_with_wrong_secret_rejected(self, user_id, token_type):
        forged = jwt.encode(
            _claims(user_id, token_type=token_type),
            "a-completely-different-secret-of-sufficient-length",
            algorithm=TEST_ALGORITHM,
        )
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    def test_tampered_payload_rejected(self, user_id, token_type):
        """Flip the payload without re-signing -> must fail."""
        token = JsonWebToken.create(user_id, token_type, timedelta(minutes=10)).encode()
        header_b64, payload_b64, sig_b64 = token.split(".")

        corrupted_payload = payload_b64[:-4] + ("AAAA" if payload_b64[-4:] != "AAAA" else "BBBB")
        tampered = f"{header_b64}.{corrupted_payload}.{sig_b64}"

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(tampered, token_type)

    def test_alg_none_forgery_rejected(self, user_id, token_type):
        """
        Classic 'alg: none' attack. The forged token is built by hand the way
        a real attacker would - valid base64/JSON with the signature segment
        left empty.
        """

        header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = b64url(json.dumps(_claims(user_id, token_type=token_type)).encode())
        forged = f"{header}.{payload}."  # empty signature segment

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    def test_garbage_string_rejected(self, token_type):
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode("not.a.jwt", token_type)

    def test_empty_string_rejected(self, token_type):
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode("", token_type)

    def test_token_signed_with_different_algorithm_rejected(self, user_id, token_type):
        """decode() pins ALGORITHM=HS256 - an HS512 token must not be accepted."""
        forged = jwt.encode(
            _claims(user_id, token_type=token_type), TEST_PRIVATE_KEY_RAW, algorithm="HS512"
        )
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    @pytest.mark.parametrize(
        "claim", ["iss", "sub", "aud", "iat", "exp", "jti", "fid", "token_type"]
    )
    def test_missing_required_claim_rejected(self, user_id, token_type, claim):
        """
        A correctly-signed token missing any required claim must be rejected
        as InvalidTokenError, not leak a raw PyJWT/pydantic error past
        decode()'s error boundary.
        """
        incomplete = {
            k: v for k, v in _claims(user_id, token_type=token_type).items() if k != claim
        }

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(_sign(incomplete), token_type)

    def test_wrong_issuer_rejected(self, user_id, token_type):
        forged = _sign(_claims(user_id, token_type=token_type, iss="some-other-issuer"))
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    def test_wrong_audience_rejected(self, user_id, token_type):
        forged = _sign(_claims(user_id, token_type=token_type, aud="some-other-audience"))
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    @pytest.mark.parametrize("claim", ["jti", "fid"])
    def test_non_uuid_id_claim_rejected(self, user_id, token_type, claim):
        forged = _sign(_claims(user_id, token_type=token_type, **{claim: "not-a-uuid"}))
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)


class TestEdDSA:
    @pytest.fixture(autouse=True)
    def eddsa_settings(self, monkeypatch):
        # runs after the module-level autouse fixture, so these values win
        self.private, self.public = _ed25519_pair()
        settings = get_settings()
        monkeypatch.setattr(settings, "JWT_ALGORITHM", "EdDSA")
        monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", SecretStr(self.private))
        monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", self.public)

    def test_round_trip(self, user_id, token_type):
        original = JsonWebToken.create(user_id, token_type, timedelta(minutes=10))
        assert JsonWebToken.decode(original.encode(), token_type) == original

    def test_header_algorithm_is_eddsa(self, user_id):
        header = jwt.get_unverified_header(JsonWebToken.access(user_id).encode())
        assert header["alg"] == "EdDSA"

    def test_token_signed_with_other_key_rejected(self, user_id, token_type):
        other_private, _ = _ed25519_pair()
        forged = jwt.encode(
            _claims(user_id, token_type=token_type), other_private, algorithm="EdDSA"
        )
        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)

    def test_hs256_signed_with_public_key_rejected(self, user_id, token_type):
        """Algorithm confusion: the public key is public, so an attacker can use
        it as an HMAC secret. Built by hand because PyJWT refuses PEM keys for HMAC."""
        header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload = b64url(json.dumps(_claims(user_id, token_type=token_type)).encode())
        signing_input = f"{header}.{payload}".encode()
        sig = hmac.new(self.public.encode(), signing_input, hashlib.sha256).digest()
        forged = f"{header}.{payload}.{b64url(sig)}"

        with pytest.raises(InvalidTokenError):
            JsonWebToken.decode(forged, token_type)
