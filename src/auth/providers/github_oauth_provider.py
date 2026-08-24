from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, SecretStr

from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthProviderInterface,
    UserData,
)
from settings import settings


class GithubUserResponse(BaseModel):
    """the required data from /user"""

    id: int
    name: str | None


class GithubEmailResponse(BaseModel):
    """the required data from /user/email"""

    class EmailObject(BaseModel):
        email: str
        primary: bool
        verified: bool


class GitHubOAuthProvider(OAuthProviderInterface):
    def __init__(self):
        self.TOKEN_URL = "https://github.com/login/oauth/access_token"
        self.client_id = settings.OAUTH_CLIENT_ID
        self.client_secret: SecretStr = settings.OAUTH_CLIENT_SECRET
        self.redirect_uri = settings.OAUTH_REDIRECT_URL
        self.scopes = settings.OAUTH_SCOPES
        self.oauth_url = settings.OAUTH_URL

    def get_redirect_url(self, state: str | None) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "response_type": "code",
        }

        if state:
            params["state"] = state

        query_string = urlencode(params)

        return f"{self.oauth_url}/oauth/authorize?{query_string}"

    def exchange_code(self, code: str) -> AuthResponseData:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret.get_secret_value(),
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "code": code,
            "grant_type": "authorization_code",
        }

        with httpx.Client() as client:
            response = client.post(
                self.TOKEN_URL, data=payload, headers={"Accept": "application/json"}
            )
            response.raise_for_status()

        data = response.json()

        return AuthResponseData(
            token_type=data["token_type"],
            access_token=data["access_token"],
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
        )

    def get_user_data(self, access_token: str) -> UserData:
        with httpx.Client() as client:
            user_response = client.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            user_response.raise_for_status()

            user = GithubUserResponse(**user_response.json())

            email_response = client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            email_response.raise_for_status()
            raw_emails = email_response.json()
            emails = [GithubEmailResponse.EmailObject(**e) for e in raw_emails]

        verified_emails = [e for e in emails if e.verified]

        email = next((e.email for e in verified_emails if e.primary), None)

        user_data = UserData(
            provider_id=str(user.id),
            email=email,
            name=user.name,
            raw={"user": user.model_dump(), "emails": raw_emails},
        )

        return user_data
