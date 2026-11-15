"""Attacks on the session: refresh token theft and replay, token confusion,
forged / tampered / expired JWTs and stale identities."""

import base64
import hashlib
import hmac
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import jwt
import pytest

from auth.oauth_transaction import create_transaction, encode_transaction
from auth.redis_refresh_token_repository import KEY_PREFIX
from auth.tokens import JsonWebToken
from tests.integration.auth.conftest import (
    LOGOUT,
    REFRESH,
    USER,
    cookie_names,
    grant_access,
    logged_in,
    login,
    plant_cookie,
)
from users.user import User

pytestmark = pytest.mark.integration


def b64url(raw: bytes | dict) -> str:
    if isinstance(raw, dict):
        raw = json.dumps(raw, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def claims_for(user_id: uuid.UUID, token_type: str = "access", **overrides) -> dict:
    token = JsonWebToken.create(user_id, "access", expires_in=timedelta(minutes=5))
    claims = token.model_dump(mode="json")
    claims["token_type"] = token_type
    claims.update(overrides)
    return claims


def use_access(client, token: str) -> int:
    plant_cookie(client, cookie_names()[0], token)
    return client.get(USER).status_code


def use_refresh(client, token: str) -> int:
    plant_cookie(client, cookie_names()[1], token)
    return client.post(REFRESH).status_code


@pytest.fixture
def approved(user_repo) -> User:
    """An approved user who exists in the database (no login needed)."""
    return user_repo.create(User(email="bob@example.com", name="Bob", access=True))


# --------------------------------------------------------------------------- refresh token theft


class TestRefreshTokenReuse:
    def test_replaying_a_rotated_token_revokes_the_whole_family(
        self, client, make_client, github, alice, user_repo, redis_client
    ):
        """Classic stolen refresh token: the attacker and the victim both hold
        the same token. Whoever uses it second triggers reuse detection, and
        every token of that login (including the newest) becomes useless."""
        _, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        stolen = client.cookies[refresh_name]
        fid = JsonWebToken.decode(stolen, "refresh").fid

        assert client.post(REFRESH).status_code == 200  # victim rotates
        legit_latest = client.cookies[refresh_name]

        attacker = make_client()
        assert use_refresh(attacker, stolen) == 401  # replay detected
        assert redis_client.get(f"{KEY_PREFIX}:family:{fid}") is None

        assert client.post(REFRESH).status_code == 401  # victim is logged out too
        assert use_refresh(make_client(), legit_latest) == 401

    def test_attacker_rotating_first_locks_out_attacker_once_victim_returns(
        self, client, make_client, github, alice, user_repo
    ):
        _, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        attacker = make_client()

        assert use_refresh(attacker, client.cookies[refresh_name]) == 200  # attacker wins race
        assert client.post(REFRESH).status_code == 401  # victim's (now stale) token: reuse
        assert attacker.post(REFRESH).status_code == 401  # attacker's chain is dead too

    def test_reuse_only_kills_the_affected_family(
        self, client, make_client, github, alice, user_repo
    ):
        _, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        laptop = make_client()
        login(laptop, github, alice)
        stale = client.cookies[refresh_name]
        client.post(REFRESH)

        assert use_refresh(make_client(), stale) == 401

        assert laptop.post(REFRESH).status_code == 200

    def test_concurrent_refresh_with_same_token_succeeds_at_most_once(
        self, client, make_client, github, alice, user_repo
    ):
        """The Lua rotate script must be atomic: N parallel refreshes with one
        token may not mint N valid sessions."""
        _, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        token = client.cookies[refresh_name]
        workers = 8
        clients = [make_client() for _ in range(workers)]
        barrier = threading.Barrier(workers)

        def race(c):
            plant_cookie(c, refresh_name, token)
            barrier.wait()
            return c.post(REFRESH).status_code

        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(race, clients))

        assert results.count(200) <= 1
        assert set(results) <= {200, 401}
        # Whatever happened, the family is compromised and must not survive
        # a second use of the original token.
        assert use_refresh(make_client(), token) == 401

    def test_validly_signed_but_unregistered_refresh_token(self, client, approved):
        """The store, not the signature, is authoritative for refresh tokens: a
        token minted with the right key but never started (e.g. leaked
        signing key, or a token from before a Redis flush) is refused."""
        forged = JsonWebToken.refresh(approved.id).encode()

        assert use_refresh(client, forged) == 401


# --------------------------------------------------------------------------- token confusion


class TestTokenConfusion:
    def test_access_token_as_refresh_token(self, client, make_client, github, alice, user_repo):
        access_name, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        genuine_refresh = client.cookies[refresh_name]

        assert use_refresh(make_client(), client.cookies[access_name]) == 401
        # The access token shares the family id with the refresh token. If it
        # reached the store it would look like a replay and revoke the family,
        # letting anyone holding an access token end the session.
        assert client.cookies[refresh_name] == genuine_refresh
        assert client.post(REFRESH).status_code == 200

    def test_refresh_token_as_access_token(self, client, github, alice, user_repo):
        _, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)

        assert use_access(client, client.cookies[refresh_name]) == 401

    def test_transaction_token_as_access_or_refresh(self, client):
        tx, _ = create_transaction("/")
        token = encode_transaction(tx)

        assert use_access(client, token) == 401
        assert use_refresh(client, token) == 401

    @pytest.mark.parametrize("token_type", ["admin", "id", ""])
    def test_unknown_token_type(self, client, approved, signing_keys, token_type):
        claims = claims_for(approved.id, token_type=token_type)
        token = jwt.encode(claims, signing_keys.private_pem, algorithm="EdDSA")

        assert use_access(client, token) == 401


# --------------------------------------------------------------------------- forged JWTs


class TestForgedAccessTokens:
    def test_genuine_token_baseline(self, client, approved):
        assert use_access(client, JsonWebToken.access(approved.id).encode()) == 200

    def test_alg_none(self, client, approved):
        claims = claims_for(approved.id)
        token = f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(claims)}."

        assert use_access(client, token) == 401

    @pytest.mark.parametrize("alg", ["HS256", "HS512"])
    def test_algorithm_confusion_public_key_as_hmac_secret(
        self, client, approved, signing_keys, alg
    ):
        """CVE-2015-9235 style: sign with HMAC using the (public!) verification
        key as the secret, hoping the verifier honours the token's alg."""
        digest = {"HS256": hashlib.sha256, "HS512": hashlib.sha512}[alg]
        header = b64url({"alg": alg, "typ": "JWT"})
        payload = b64url(claims_for(approved.id))
        signing_input = f"{header}.{payload}".encode()
        signature = hmac.new(signing_keys.public_pem.encode(), signing_input, digest).digest()
        token = f"{header}.{payload}.{b64url(signature)}"

        assert use_access(client, token) == 401

    def test_signed_with_foreign_key(self, client, approved, attacker_keys):
        token = jwt.encode(claims_for(approved.id), attacker_keys.private_pem, algorithm="EdDSA")

        assert use_access(client, token) == 401

    def test_embedded_jwk_header_is_ignored(self, client, approved, attacker_keys):
        """Attacker-supplied verification key in the header (jwk / jku)."""
        token = jwt.encode(
            claims_for(approved.id),
            attacker_keys.private_pem,
            algorithm="EdDSA",
            headers={"jku": "https://evil.example/jwks.json", "kid": "../../dev/null"},
        )

        assert use_access(client, token) == 401

    def test_tampered_subject_privilege_escalation(self, client, user_repo, approved):
        """Swap sub for the admin's id in a genuine token, keep the signature."""
        admin = user_repo.create(
            User(email="root@example.com", name="Root", access=True, admin=True)
        )
        header, _, signature = JsonWebToken.access(approved.id).encode().split(".")
        tampered = f"{header}.{b64url(claims_for(approved.id, sub=str(admin.id)))}.{signature}"

        assert use_access(client, tampered) == 401

    def test_signature_stripped(self, client, approved):
        header, payload, _ = JsonWebToken.access(approved.id).encode().split(".")

        assert use_access(client, f"{header}.{payload}.") == 401

    @pytest.mark.parametrize(
        "override",
        [
            {"aud": "some-other-service"},
            {"iss": "https://evil.example"},
            {"exp": int(time.time()) - 1},
        ],
        ids=["wrong-audience", "wrong-issuer", "expired"],
    )
    def test_correctly_signed_but_invalid_claims(self, client, approved, signing_keys, override):
        token = jwt.encode(
            claims_for(approved.id, **override), signing_keys.private_pem, algorithm="EdDSA"
        )

        assert use_access(client, token) == 401

    @pytest.mark.parametrize("missing", ["exp", "jti", "fid", "iat", "sub", "aud", "iss"])
    def test_missing_required_claim(self, client, approved, signing_keys, missing):
        claims = claims_for(approved.id)
        del claims[missing]
        token = jwt.encode(claims, signing_keys.private_pem, algorithm="EdDSA")

        assert use_access(client, token) == 401

    def test_expired_refresh_token(self, client, approved, signing_keys, refresh_repo):
        token = JsonWebToken.refresh(approved.id)
        refresh_repo.start(token)  # registered, so only expiry can stop it
        expired = token.model_copy(update={"exp": int(time.time()) - 1})
        encoded = jwt.encode(
            expired.model_dump(mode="json"), signing_keys.private_pem, algorithm="EdDSA"
        )

        assert use_refresh(client, encoded) == 401

    @pytest.mark.parametrize(
        "garbage",
        ["", "null", "a.b.c", "e30.e30.e30", "%F0%9F%98%88", "x" * 4096],
        ids=["empty", "null", "dots", "empty-json", "percent-encoded", "oversized"],
    )
    def test_garbage_cookies(self, client, garbage):
        assert use_access(client, garbage) == 401
        assert use_refresh(client, garbage) == 401


# --------------------------------------------------------------------------- stale identities


class TestStaleIdentity:
    def test_deleted_user_loses_access_and_refresh(self, client, github, alice, user_repo):
        user = logged_in(client, github, alice, user_repo)

        user_repo.delete(user.id)

        assert client.get(USER).status_code == 401
        assert client.post(REFRESH).status_code == 401

    def test_revoked_access_takes_effect_immediately(self, client, github, alice, user_repo):
        user = logged_in(client, github, alice, user_repo)

        user.access = False
        user_repo.update(user)

        assert client.get(USER).status_code == 403
        assert client.post(REFRESH).status_code == 401

    def test_regranting_access_resurrects_a_refused_session(self, client, github, alice, user_repo):
        """Documents current behaviour: a refused refresh neither rotates nor
        revokes, so the family stays live and a later re-grant re-enables the
        old session."""
        user = logged_in(client, github, alice, user_repo)
        user.access = False
        user_repo.update(user)
        assert client.post(REFRESH).status_code == 401

        grant_access(user_repo, alice.primary_email)

        # The refresh cookie was not cleared by the 401, and the family is
        # still live, so the old session comes back. If that is undesired,
        # revoke the user's families when access is withdrawn.
        assert client.post(REFRESH).status_code == 200

    def test_access_token_outlives_logout_until_expiry(self, client, github, alice, user_repo):
        """By design: access tokens are stateless (JWT_ACCESS_TOKEN_TTL, 10 min
        by default). Logout kills the refresh family, but a copied access
        token keeps working until it expires."""
        access_name, _, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        copied_access = client.cookies[access_name]

        client.post(LOGOUT)

        assert client.post(REFRESH).status_code == 401
        assert use_access(client, copied_access) == 200
