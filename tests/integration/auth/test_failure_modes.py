"""Outages of the things auth depends on. The contract (auth/exceptions.py):
a dependency failure is a 503, never a 401, never touches the client's
cookies, and never leaks internals."""

from contextlib import contextmanager

import pytest
from dependency_injector import providers
from pydantic import SecretStr
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from api.app import container
from containers.database import Database
from tests.integration.auth.conftest import (
    LOGOUT,
    REFRESH,
    USER,
    callback,
    cookie_names,
    logged_in,
    login,
    set_cookie_headers,
    start_login,
)

pytestmark = pytest.mark.integration


@contextmanager
def redis_down():
    """A real client against a closed port: redis-py raises the genuine
    ConnectionError, so the repository's error translation is exercised.
    Retries are off to keep the test fast (redis-py retries 3x with backoff by
    default, ~4 s per request)."""
    dead = Redis(
        host="127.0.0.1",
        port=1,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        retry=Retry(NoBackoff(), 0),
    )
    with container.redis_client.override(providers.Object(dead)):
        yield
    dead.close()


@contextmanager
def database_down(tmp_path):
    """SQLite that cannot open its file raises a genuine OperationalError."""
    dead = Database(f"sqlite:///{tmp_path / 'missing-dir' / 'nope.db'}")
    with container.db.override(providers.Object(dead)):
        yield


def assert_unavailable_without_cookie_changes(response, detail: str) -> None:
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": detail}
    access_name, refresh_name, _ = cookie_names()
    headers = set_cookie_headers(response)
    assert access_name not in headers
    assert refresh_name not in headers


GENERIC = "Service temporarily unavailable"


class TestTokenStoreOutage:
    def test_refresh_is_503_and_session_survives(self, client, github, alice, user_repo):
        logged_in(client, github, alice, user_repo)

        with redis_down():
            response = client.post(REFRESH)

        assert_unavailable_without_cookie_changes(response, GENERIC)
        assert client.post(REFRESH).status_code == 200  # same token works after recovery

    def test_logout_is_503_and_keeps_cookies_for_retry(self, client, github, alice, user_repo):
        logged_in(client, github, alice, user_repo)

        with redis_down():
            response = client.post(LOGOUT)

        assert_unavailable_without_cookie_changes(response, GENERIC)
        assert client.post(LOGOUT).status_code == 200
        assert client.post(REFRESH).status_code == 401

    def test_login_callback_is_503(self, client, github, alice):
        code, state = github.authorize(start_login(client), alice)

        with redis_down():
            response = callback(client, code, state)

        assert_unavailable_without_cookie_changes(response, GENERIC)

    def test_access_token_keeps_working(self, client, github, alice, user_repo):
        """/user does not touch Redis."""
        logged_in(client, github, alice, user_repo)

        with redis_down():
            assert client.get(USER).status_code == 200


class TestDatabaseOutage:
    def test_login_callback_is_503(self, client, github, alice, tmp_path):
        code, state = github.authorize(start_login(client), alice)

        with database_down(tmp_path):
            response = callback(client, code, state)

        assert_unavailable_without_cookie_changes(response, GENERIC)

    def test_refresh_is_503_and_session_survives(self, client, github, alice, user_repo, tmp_path):
        logged_in(client, github, alice, user_repo)

        with database_down(tmp_path):
            response = client.post(REFRESH)

        assert_unavailable_without_cookie_changes(response, GENERIC)
        assert client.post(REFRESH).status_code == 200

    def test_user_endpoint_is_503(self, client, github, alice, user_repo, tmp_path):
        logged_in(client, github, alice, user_repo)

        with database_down(tmp_path):
            response = client.get(USER)

        assert response.status_code == 503

    def test_user_endpoint_outage_is_never_401(self, client, github, alice, user_repo, tmp_path):
        """Whatever the status, an outage must not look like 'logged out'."""
        logged_in(client, github, alice, user_repo)

        with database_down(tmp_path):
            response = client.get(USER)

        assert response.status_code != 401
        assert "OperationalError" not in response.text
        assert "sqlite" not in response.text.lower()


class TestProviderOutage:
    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_token_endpoint_5xx(self, client, github, alice, status):
        code, state = github.authorize(start_login(client), alice)
        github.token_endpoint_status = status

        response = callback(client, code, state)

        assert_unavailable_without_cookie_changes(response, "Login provider unavailable")

    def test_provider_unreachable(self, client, github, alice):
        code, state = github.authorize(start_login(client), alice)
        github.unreachable = True

        response = callback(client, code, state)

        assert_unavailable_without_cookie_changes(response, "Login provider unavailable")

    def test_user_api_5xx(self, client, github, alice, user_repo):
        code, state = github.authorize(start_login(client), alice)
        github.user_api_status = 502

        response = callback(client, code, state)

        assert_unavailable_without_cookie_changes(response, "Login provider unavailable")
        assert user_repo.get_by_email(alice.primary_email) is None

    def test_wrong_client_secret_is_a_rejection_not_an_outage(
        self, client, github, alice, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "OAUTH_CLIENT_SECRET", SecretStr("rotated-away"))
        code, state = github.authorize(start_login(client), alice)

        response = callback(client, code, state)

        assert response.status_code == 400
        assert response.json() == {"detail": "Authentication failed"}
        assert "rotated-away" not in response.text

    def test_existing_sessions_survive_a_provider_outage(self, client, github, alice, user_repo):
        logged_in(client, github, alice, user_repo)
        github.unreachable = True

        assert client.get(USER).status_code == 200
        assert client.post(REFRESH).status_code == 200


def test_rejections_leak_nothing(client, github, alice):
    """Error bodies are the fixed detail strings only."""
    code, _ = github.authorize(start_login(client), alice)

    response = callback(client, code, "forged-state")

    assert response.json() == {"detail": "Login failed"}
    login_ok = login(client, github, alice)
    assert login_ok.status_code == 307
