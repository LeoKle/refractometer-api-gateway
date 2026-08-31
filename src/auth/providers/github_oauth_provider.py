from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthExchangeError,
    OAuthNetworkError,
    OAuthProviderInterface,
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
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as err:
            msg = f"GitHub rejected the code exchange (status {err.response.status_code})"
            raise OAuthExchangeError(msg) from err
        except httpx.HTTPError as err:
            msg = "Could not reach GitHub to exchange code"
            raise OAuthNetworkError(msg) from err
        except ValueError as err:  # response.json() failed to parse
            msg = "GitHub returned a non-JSON response"
            raise OAuthExchangeError(msg) from err

        if "error" in data:
            msg = (
                f"GitHub rejected the code exchange: {data.get('error_description', data['error'])}"
            )
            raise OAuthExchangeError(msg)

        try:
            return AuthResponseData(
                token_type=data["token_type"],
                access_token=data["access_token"],
                expires_in=data.get("expires_in"),
                refresh_token=data.get("refresh_token"),
            )
        except (KeyError, ValidationError) as err:
            msg = f"GitHub's token response was missing an expected field: {err}"
            raise OAuthExchangeError(msg) from err

    def get_user_data(self, access_token: str) -> UserData:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                user_response = client.get("https://api.github.com/user", headers=headers)
                user_response.raise_for_status()
                raw_user = user_response.json()

                email_response = client.get("https://api.github.com/user/emails", headers=headers)
                email_response.raise_for_status()
                raw_emails = email_response.json()
        except httpx.HTTPStatusError as err:
            msg = f"GitHub rejected the user data request (status {err.response.status_code})"
            raise OAuthUserDataError(msg) from err
        except httpx.HTTPError as err:
            msg = "Could not reach GitHub to fetch user data"
            raise OAuthNetworkError(msg) from err
        except ValueError as err:
            msg = "GitHub returned a non-JSON response"
            raise OAuthUserDataError(msg) from err

        try:
            user = GithubUserResponse(**raw_user)
            emails = [GitHubEmailObject(**e) for e in raw_emails]
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
