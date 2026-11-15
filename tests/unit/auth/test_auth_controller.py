from unittest.mock import create_autospec

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from api.app import app, container
from auth.exceptions import (
    AuthProviderUnavailableError,
    InfrastructureUnavailableError,
    InvalidLoginTransactionError,
    InvalidSessionError,
    LoginRejectedError,
)
from auth.interfaces.auth_service_interface import AuthModel, AuthServiceInterface, LoginResult
from settings import get_settings

LEAK = "internal error / detail that must not reach the client"


@pytest.fixture
def auth_service():
    service = create_autospec(AuthServiceInterface, instance=True)
    with container.auth_service.override(providers.Object(service)):
        yield service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False, follow_redirects=False)


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def cleared(response, name: str) -> bool:
    return any(
        h.startswith(f'{name}=""') and "Max-Age=0" in h for h in set_cookie_headers(response)
    )


class TestCallback:
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (InvalidLoginTransactionError, 400, "Login failed"),
            (LoginRejectedError, 400, "Authentication failed"),
            (AuthProviderUnavailableError, 503, "Login provider unavailable"),
            (InfrastructureUnavailableError, 503, "Service temporarily unavailable"),
        ],
    )
    def test_service_errors(self, client, auth_service, error, status_code, detail):
        auth_service.complete_login.side_effect = error(LEAK)

        response = client.get("/api/v1/auth/callback", params={"code": "c", "state": "s"})

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert set_cookie_headers(response) == []

    def test_unexpected_errors_are_not_mapped(self, client, auth_service):
        auth_service.complete_login.side_effect = RuntimeError(LEAK)

        response = client.get("/api/v1/auth/callback", params={"code": "c", "state": "s"})

        assert response.status_code == 500
        assert LEAK not in response.text

    def test_success_sets_session_cookies_and_redirects(self, client, auth_service):
        auth_service.complete_login.return_value = LoginResult(
            access_token="a", refresh_token="r", redirect_to="/dashboard"
        )
        settings = get_settings()
        client.cookies.set(settings.COOKIE_NAME_OAUTH_TRANSACTION, "tx")

        response = client.get("/api/v1/auth/callback", params={"code": "c", "state": "s"})

        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard"
        auth_service.complete_login.assert_called_once_with("c", "s", "tx")
        assert response.cookies.get(settings.COOKIE_NAME_ACCESS) == "a"
        assert response.cookies.get(settings.COOKIE_NAME_REFRESH) == "r"
        assert cleared(response, settings.COOKIE_NAME_OAUTH_TRANSACTION)


class TestRefresh:
    @pytest.mark.parametrize(
        ("error", "status_code", "detail"),
        [
            (InvalidSessionError, 401, "Unable to refresh tokens"),
            (InfrastructureUnavailableError, 503, "Service temporarily unavailable"),
        ],
    )
    def test_service_errors(self, client, auth_service, error, status_code, detail):
        auth_service.refresh.side_effect = error(LEAK)

        response = client.post("/api/v1/auth/refresh")

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}
        assert set_cookie_headers(response) == []

    def test_success_rotates_session_cookies(self, client, auth_service):
        auth_service.refresh.return_value = AuthModel(access="a2", refresh="r2")
        settings = get_settings()
        client.cookies.set(settings.COOKIE_NAME_REFRESH, "r1")

        response = client.post("/api/v1/auth/refresh")

        assert response.status_code == 200
        auth_service.refresh.assert_called_once_with("r1")
        assert response.cookies.get(settings.COOKIE_NAME_ACCESS) == "a2"
        assert response.cookies.get(settings.COOKIE_NAME_REFRESH) == "r2"


class TestLogout:
    def test_success_clears_session_cookies(self, client, auth_service):
        settings = get_settings()

        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        assert cleared(response, settings.COOKIE_NAME_ACCESS)
        assert cleared(response, settings.COOKIE_NAME_REFRESH)

    def test_outage_keeps_cookies_so_the_client_can_retry(self, client, auth_service):
        auth_service.logout.side_effect = InfrastructureUnavailableError(LEAK)

        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 503
        assert response.json() == {"detail": "Service temporarily unavailable"}
        assert set_cookie_headers(response) == []
