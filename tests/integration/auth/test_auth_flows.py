"""Happy paths through the real stack: login, session use, rotation, logout."""

import jwt
import pytest

from auth.oauth_transaction import decode_transaction
from auth.redis_refresh_token_repository import KEY_PREFIX
from auth.tokens import JsonWebToken
from tests.integration.auth.conftest import (
    CALLBACK_PATH,
    CLIENT_ID,
    LOGIN,
    LOGOUT,
    REFRESH,
    USER,
    callback,
    cookie_names,
    grant_access,
    logged_in,
    login,
    plant_cookie,
    query,
    set_cookie_headers,
    start_login,
)
from tests.integration.auth.fake_github import s256

pytestmark = pytest.mark.integration


class TestLoginStart:
    def test_redirects_to_github_with_pkce_s256_and_state(self, client):
        response = client.get(LOGIN)

        assert response.status_code == 307
        location = response.headers["location"]
        assert location.startswith("https://github.com/oauth/authorize?")

        params = query(location)
        assert params["client_id"] == CLIENT_ID
        assert params["redirect_uri"] == "http://testserver" + CALLBACK_PATH
        assert params["response_type"] == "code"
        assert params["code_challenge_method"] == "S256"
        assert len(params["state"]) >= 32
        # base64url(sha256) without padding
        assert len(params["code_challenge"]) == 43
        assert "=" not in params["code_challenge"]

    def test_transaction_cookie_is_scoped_and_carries_matching_secrets(self, client):
        _, _, tx_name = cookie_names()

        response = client.get(LOGIN)

        header = set_cookie_headers(response)[tx_name]
        assert "HttpOnly" in header
        assert "Path=/api/v1/auth" in header
        assert "Max-Age=600" in header
        assert "samesite=lax" in header.lower()

        tx = decode_transaction(client.cookies[tx_name])
        params = query(response.headers["location"])
        assert tx.state == params["state"]
        assert s256(tx.code_verifier) == params["code_challenge"]
        assert 43 <= len(tx.code_verifier) <= 128

    def test_each_login_gets_fresh_state_and_verifier(self, client, make_client):
        first = query(start_login(client))
        second = query(start_login(make_client()))

        assert first["state"] != second["state"]
        assert first["code_challenge"] != second["code_challenge"]


class TestLoginCallback:
    def test_full_login_creates_user_and_session(
        self, client, github, alice, user_repo, redis_client
    ):
        access_name, refresh_name, tx_name = cookie_names()

        response = login(client, github, alice, redirect_to="/dashboard?tab=2")

        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard?tab=2"

        headers = set_cookie_headers(response)
        for name in (access_name, refresh_name):
            assert "HttpOnly" in headers[name]
            assert "Path=/" in headers[name]
            assert "samesite=strict" in headers[name].lower()
        assert "Max-Age=0" in headers[tx_name]
        assert tx_name not in client.cookies

        # the provider saw the real verifier for the challenge it issued
        assert len(github.token_requests) == 1
        assert github.token_requests[0]["code_verifier"]

        user = user_repo.get_by_email("alice@example.com")
        assert user is not None
        assert user.name == "Alice"
        assert user.access is False  # new accounts need approval

        access = JsonWebToken.decode(client.cookies[access_name], "access")
        refresh = JsonWebToken.decode(client.cookies[refresh_name], "refresh")
        assert access.sub == refresh.sub == user.id
        assert access.fid == refresh.fid
        stored = redis_client.get(f"{KEY_PREFIX}:family:{refresh.fid}")
        assert stored.decode() == str(refresh.jti)

    def test_tokens_are_signed_with_eddsa(self, client, github, alice):
        access_name, _, _ = cookie_names()
        login(client, github, alice)

        header = jwt.get_unverified_header(client.cookies[access_name])
        assert header["alg"] == "EdDSA"

    def test_default_redirect_is_root(self, client, github, alice):
        response = login(client, github, alice)

        assert response.headers["location"] == "/"

    def test_returning_user_is_reused(self, client, make_client, github, alice, user_repo):
        login(client, github, alice)
        first = user_repo.get_by_email("alice@example.com")

        login(make_client(), github, alice)

        assert user_repo.get_by_email("alice@example.com").id == first.id

    def test_new_user_without_access_gets_403(self, client, github, alice):
        login(client, github, alice)

        assert client.get(USER).status_code == 403

    def test_approved_user_can_read_profile(self, client, github, alice, user_repo):
        user = logged_in(client, github, alice, user_repo)

        response = client.get(USER)

        assert response.status_code == 200
        assert response.json() == {
            "user_id": str(user.id),
            "name": "Alice",
            "access": True,
            "admin": False,
        }


class TestRefresh:
    def test_rotation_issues_new_pair_in_same_family(self, client, github, alice, user_repo):
        access_name, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        old_access = JsonWebToken.decode(client.cookies[access_name], "access")
        old_refresh = JsonWebToken.decode(client.cookies[refresh_name], "refresh")

        response = client.post(REFRESH)

        assert response.status_code == 200
        new_access = JsonWebToken.decode(client.cookies[access_name], "access")
        new_refresh = JsonWebToken.decode(client.cookies[refresh_name], "refresh")
        assert new_refresh.jti != old_refresh.jti
        assert new_access.jti != old_access.jti
        assert new_refresh.fid == old_refresh.fid == new_access.fid
        assert client.get(USER).status_code == 200

    def test_many_sequential_rotations(self, client, github, alice, user_repo):
        logged_in(client, github, alice, user_repo)

        for _ in range(5):
            assert client.post(REFRESH).status_code == 200

        assert client.get(USER).status_code == 200

    def test_user_without_access_cannot_refresh(self, client, github, alice):
        login(client, github, alice)

        assert client.post(REFRESH).status_code == 401


class TestLogout:
    def test_logout_clears_cookies_and_revokes_family(
        self, client, github, alice, user_repo, redis_client
    ):
        access_name, refresh_name, _ = cookie_names()
        logged_in(client, github, alice, user_repo)
        refresh_token = client.cookies[refresh_name]
        fid = JsonWebToken.decode(refresh_token, "refresh").fid

        response = client.post(LOGOUT)

        assert response.status_code == 200
        headers = set_cookie_headers(response)
        assert "Max-Age=0" in headers[access_name]
        assert "Max-Age=0" in headers[refresh_name]
        assert redis_client.get(f"{KEY_PREFIX}:family:{fid}") is None

        # the refresh token is dead even if the client kept a copy
        plant_cookie(client, refresh_name, refresh_token)
        assert client.post(REFRESH).status_code == 401

    def test_logout_without_session_is_noop(self, client):
        assert client.post(LOGOUT).status_code == 200

    def test_logout_on_one_device_keeps_the_other(
        self, client, make_client, github, alice, user_repo
    ):
        logged_in(client, github, alice, user_repo)
        phone = make_client()
        login(phone, github, alice)

        assert client.post(LOGOUT).status_code == 200

        assert client.post(REFRESH).status_code == 401
        assert phone.post(REFRESH).status_code == 200

    def test_revoke_all_ends_every_session(
        self, client, make_client, github, alice, user_repo, refresh_repo
    ):
        user = logged_in(client, github, alice, user_repo)
        phone = make_client()
        login(phone, github, alice)

        refresh_repo.revoke_all_for_user(user.id)

        assert client.post(REFRESH).status_code == 401
        assert phone.post(REFRESH).status_code == 401

    def test_user_can_log_in_again_after_logout(self, client, github, alice, user_repo):
        logged_in(client, github, alice, user_repo)
        client.post(LOGOUT)

        response = login(client, github, alice)

        assert response.status_code == 307
        grant_access(user_repo, alice.primary_email)
        assert client.get(USER).status_code == 200
        assert client.post(REFRESH).status_code == 200


def test_callback_needs_the_transaction_cookie_path(client, github, alice):
    """The transaction cookie is path-scoped to /api/v1/auth, so it reaches the
    callback but not the rest of the API."""
    _, _, tx_name = cookie_names()
    authorize_url = start_login(client)
    code, state = github.authorize(authorize_url, alice)

    jar_paths = {c.path for c in client.cookies.jar if c.name == tx_name}
    assert jar_paths == {"/api/v1/auth"}
    assert callback(client, code, state).status_code == 307
