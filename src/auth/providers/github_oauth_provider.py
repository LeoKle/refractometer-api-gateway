from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError

from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthExchangeError,
    OAuthProviderInterface,
    OAuthUnavailableError,
    OAuthUserDataError,
    UserData,
)
from auth.oauth_transaction import PKCECodeChallenge
from settings import get_settings

REQUEST_TIMEOUT = 10.0


class GithubUserResponse(BaseModel):
    """the required data from /user"""

    id: int
    name: str | None


class GitHubEmailObject(BaseModel):
    """a single entry from /user/emails"""

    email: str
    primary: bool
    verified: bool


class GitHubTokenResponse(BaseModel):
    """a successful response from the token endpoint"""

    token_type: str
    access_token: str
    expires_in: int | None = None
    refresh_token: str | None = None


_EMAIL_LIST = TypeAdapter(list[GitHubEmailObject])


class GitHubOAuthProvider(OAuthProviderInterface):
    def __init__(self):
        settings = get_settings()
        self.TOKEN_URL = "https://github.com/login/oauth/access_token"
        self.client_id = settings.OAUTH_CLIENT_ID
        self.client_secret: SecretStr = settings.OAUTH_CLIENT_SECRET
        self.redirect_uri = settings.OAUTH_REDIRECT_URL
        self.scopes = settings.OAUTH_SCOPES
        self.oauth_url = settings.OAUTH_URL

    def get_redirect_url(
        self,
        state: str,
        code_challenge: PKCECodeChallenge,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "response_type": "code",
            "state": state,
            "code_challenge": code_challenge.code_challenge,
            "code_challenge_method": code_challenge.code_challenge_method,
        }

        query_string = urlencode(params)

        return f"{self.oauth_url}/oauth/authorize?{query_string}"

    def exchange_code(self, code: str, code_verifier: str) -> AuthResponseData:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret.get_secret_value(),
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
        }

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.post(
                    self.TOKEN_URL, data=payload, headers={"Accept": "application/json"}
                )
        except httpx.HTTPError as err:
            msg = "Could not reach GitHub to exchange code"
            raise OAuthUnavailableError(msg) from err

        if response.is_server_error:
            msg = f"GitHub failed the code exchange (status {response.status_code})"
            raise OAuthUnavailableError(msg)

        try:
            data = response.json()
        except ValueError as err:
            msg = f"GitHub returned a non-JSON response (status {response.status_code})"
            raise OAuthExchangeError(msg) from err

        # RFC 6749 section 5.2 error responses come as 400 with an "error" member;
        # GitHub additionally sends them with status 200.
        if isinstance(data, dict) and "error" in data:
            msg = (
                f"GitHub rejected the code exchange: {data.get('error_description', data['error'])}"
            )
            raise OAuthExchangeError(msg)

        if not response.is_success:
            msg = f"GitHub rejected the code exchange (status {response.status_code})"
            raise OAuthExchangeError(msg)

        try:
            token = GitHubTokenResponse.model_validate(data)
        except ValidationError as err:
            msg = f"GitHub's token response was missing an expected field: {err}"
            raise OAuthExchangeError(msg) from err

        return AuthResponseData(
            token_type=token.token_type,
            access_token=token.access_token,
            expires_in=token.expires_in,
            refresh_token=token.refresh_token,
        )

    def get_user_data(self, access_token: str) -> UserData:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            raw_user = self._get_json(client, "https://api.github.com/user", headers)
            raw_emails = self._get_json(client, "https://api.github.com/user/emails", headers)

        try:
            user = GithubUserResponse.model_validate(raw_user)
            emails = _EMAIL_LIST.validate_python(raw_emails)
        except ValidationError as err:
            msg = f"Unexpected shape from GitHub's user API: {err}"
            raise OAuthUserDataError(msg) from err

        email = next((e.email for e in emails if e.primary and e.verified), None)

        if email is None:
            msg = "GitHub account has no verified primary email visible to this app"
            raise OAuthUserDataError(msg)

        return UserData(
            provider_id=str(user.id),
            email=email,
            name=user.name,
            raw={"user": raw_user, "emails": raw_emails},
        )

    @staticmethod
    def _get_json(client: httpx.Client, url: str, headers: dict[str, str]) -> object:
        try:
            response = client.get(url, headers=headers)
        except httpx.HTTPError as err:
            msg = f"Could not reach GitHub ({url})"
            raise OAuthUnavailableError(msg) from err

        if response.is_server_error:
            msg = f"GitHub failed the user data request (status {response.status_code})"
            raise OAuthUnavailableError(msg)

        if not response.is_success:
            msg = f"GitHub rejected the user data request (status {response.status_code})"
            raise OAuthUserDataError(msg)

        try:
            return response.json()
        except ValueError as err:
            msg = "GitHub returned a non-JSON response"
            raise OAuthUserDataError(msg) from err
