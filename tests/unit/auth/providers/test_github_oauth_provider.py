import httpx
import pytest

from auth.interfaces.oauth_provider_interface import (
    OAuthExchangeError,
    OAuthNetworkError,
    OAuthUserDataError,
)
from auth.oauth_transaction import PKCECodeChallenge
from auth.providers.github_oauth_provider import GitHubOAuthProvider
from settings import get_settings

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
EMAILS_URL = "https://api.github.com/user/emails"

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def pinned_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(
        settings, "OAUTH_CLIENT_SECRET", __import__("pydantic").SecretStr("test-secret")
    )
    monkeypatch.setattr(settings, "OAUTH_REDIRECT_URL", "https://app.example.com/callback")
    monkeypatch.setattr(settings, "OAUTH_SCOPES", "read:user user:email")
    monkeypatch.setattr(settings, "OAUTH_URL", "https://github.com")


@pytest.fixture
def provider() -> GitHubOAuthProvider:
    return GitHubOAuthProvider()


def valid_token_response() -> dict:
    return {
        "token_type": "bearer",
        "access_token": "gho_abc123",
        "expires_in": 28800,
        "refresh_token": "ghr_xyz789",
    }


def user_payload(id_: int = 1, name: str | None = "Alice") -> dict:
    return {"id": id_, "name": name}


def emails_payload() -> list[dict]:
    return [
        {"email": "old@example.com", "primary": False, "verified": True},
        {"email": "alice@example.com", "primary": True, "verified": True},
        {"email": "unverified@example.com", "primary": False, "verified": False},
    ]


class TestGetRedirectUrl:
    def test_includes_all_required_params(self, provider):
        code_challenge = PKCECodeChallenge(code_challenge="abc123", code_challenge_method="S256")

        url = provider.get_redirect_url(state="random-state", code_challenge=code_challenge)

        assert url.startswith("https://github.com/oauth/authorize?")
        assert "client_id=test-client-id" in url
        assert "state=random-state" in url
        assert "code_challenge=abc123" in url
        assert "code_challenge_method=S256" in url
        assert "response_type=code" in url

    def test_redirect_uri_is_url_encoded(self, provider):
        code_challenge = PKCECodeChallenge(code_challenge="x", code_challenge_method="S256")
        url = provider.get_redirect_url(state="s", code_challenge=code_challenge)
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in url


class TestExchangeCode:
    def test_success_returns_auth_response_data(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json=valid_token_response())
        )

        result = provider.exchange_code(code="abc", code_verifier="verifier")

        assert result.token_type == "bearer"
        assert result.access_token == "gho_abc123"
        assert result.expires_in == 28800
        assert result.refresh_token == "ghr_xyz789"

    def test_optional_fields_default_to_none(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"token_type": "bearer", "access_token": "gho_abc123"}
            )
        )

        result = provider.exchange_code(code="abc", code_verifier="verifier")

        assert result.expires_in is None
        assert result.refresh_token is None

    def test_4xx_status_raises_exchange_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))

        with pytest.raises(OAuthExchangeError):
            provider.exchange_code(code="bad-code", code_verifier="verifier")

    def test_5xx_status_raises_exchange_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(OAuthExchangeError):
            provider.exchange_code(code="abc", code_verifier="verifier")

    def test_connection_failure_raises_network_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(OAuthNetworkError):
            provider.exchange_code(code="abc", code_verifier="verifier")

    def test_timeout_raises_network_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(OAuthNetworkError):
            provider.exchange_code(code="abc", code_verifier="verifier")

    def test_non_json_response_raises_exchange_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, content=b"not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(OAuthExchangeError):
            provider.exchange_code(code="abc", code_verifier="verifier")

    def test_github_200_ok_error_body_raises_exchange_error(self, provider, respx_mock):
        """GitHub's OAuth quirk: a rejected/expired code still comes back as HTTP 200."""
        respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "error": "bad_verification_code",
                    "error_description": "The code passed is incorrect or expired.",
                },
            )
        )

        with pytest.raises(OAuthExchangeError, match="bad_verification_code|incorrect or expired"):  # ruff: ignore[pytest-raises-ambiguous-pattern]
            provider.exchange_code(code="expired-code", code_verifier="verifier")

    def test_missing_access_token_field_raises_exchange_error(self, provider, respx_mock):
        respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"token_type": "bearer"})
        )

        with pytest.raises(OAuthExchangeError):
            provider.exchange_code(code="abc", code_verifier="verifier")

    def test_sends_expected_payload(self, provider, respx_mock):
        route = respx_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json=valid_token_response())
        )

        provider.exchange_code(code="the-code", code_verifier="the-verifier")

        request = route.calls.last.request
        sent = dict(x.split("=") for x in request.content.decode().split("&"))
        assert sent["code"] == "the-code"
        assert sent["code_verifier"] == "the-verifier"
        assert sent["grant_type"] == "authorization_code"
        assert sent["client_id"] == "test-client-id"


class TestGetUserData:
    def _mock_success(self, respx_mock, user=None, emails=None):
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json=user or user_payload()))
        respx_mock.get(EMAILS_URL).mock(
            return_value=httpx.Response(
                200, json=emails if emails is not None else emails_payload()
            )
        )

    def test_success_returns_verified_primary_email(self, provider, respx_mock):
        self._mock_success(respx_mock)

        result = provider.get_user_data(access_token="gho_abc123")

        assert result.provider_id == "1"
        assert result.email == "alice@example.com"
        assert result.name == "Alice"
        assert result.raw["user"]["id"] == 1

    def test_ignores_unverified_or_non_primary_emails(self, provider, respx_mock):
        self._mock_success(
            respx_mock,
            emails=[
                {"email": "primary-unverified@example.com", "primary": True, "verified": False},
                {"email": "secondary-verified@example.com", "primary": False, "verified": True},
            ],
        )

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="gho_abc123")

    def test_no_verified_primary_email_raises_user_data_error(self, provider, respx_mock):
        self._mock_success(respx_mock, emails=[])

        with pytest.raises(OAuthUserDataError, match="verified primary email"):
            provider.get_user_data(access_token="gho_abc123")

    def test_null_name_is_allowed(self, provider, respx_mock):
        self._mock_success(respx_mock, user=user_payload(name=None))

        result = provider.get_user_data(access_token="gho_abc123")

        assert result.name is None

    def test_user_endpoint_4xx_raises_user_data_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(401))

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="bad-token")

    def test_emails_endpoint_4xx_raises_user_data_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json=user_payload()))
        respx_mock.get(EMAILS_URL).mock(return_value=httpx.Response(403))

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="gho_abc123")

    def test_connection_failure_raises_network_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(OAuthNetworkError):
            provider.get_user_data(access_token="gho_abc123")

    def test_connection_failure_on_emails_call_raises_network_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json=user_payload()))
        respx_mock.get(EMAILS_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(OAuthNetworkError):
            provider.get_user_data(access_token="gho_abc123")

    def test_non_json_response_raises_user_data_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(
            return_value=httpx.Response(
                200, content=b"not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="gho_abc123")

    def test_malformed_user_shape_raises_user_data_error(self, provider, respx_mock):
        """id missing entirely - fails GithubUserResponse validation."""
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json={"name": "Alice"}))
        respx_mock.get(EMAILS_URL).mock(return_value=httpx.Response(200, json=emails_payload()))

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="gho_abc123")

    def test_malformed_email_entry_raises_user_data_error(self, provider, respx_mock):
        respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json=user_payload()))
        respx_mock.get(EMAILS_URL).mock(
            return_value=httpx.Response(
                200, json=[{"email": "x@example.com"}]
            )  # missing primary/verified
        )

        with pytest.raises(OAuthUserDataError):
            provider.get_user_data(access_token="gho_abc123")

    def test_sends_bearer_token(self, provider, respx_mock):
        route = respx_mock.get(USER_URL).mock(return_value=httpx.Response(200, json=user_payload()))
        respx_mock.get(EMAILS_URL).mock(return_value=httpx.Response(200, json=emails_payload()))

        provider.get_user_data(access_token="gho_secret")

        assert route.calls.last.request.headers["Authorization"] == "Bearer gho_secret"

    def test_raw_field_preserves_both_responses(self, provider, respx_mock):
        emails = emails_payload()
        self._mock_success(respx_mock, emails=emails)

        result = provider.get_user_data(access_token="gho_abc123")

        assert result.raw["emails"] == emails
        assert "id" in result.raw["user"]
