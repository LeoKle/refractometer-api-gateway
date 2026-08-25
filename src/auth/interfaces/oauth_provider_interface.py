from abc import ABC, abstractmethod
from dataclasses import dataclass

from auth.oauth_transaction import PKCECodeChallenge


@dataclass
class AuthResponseData:
    token_type: str
    access_token: str
    expires_in: int | None
    refresh_token: str | None


@dataclass
class UserData:
    provider_id: str  # unique within that provider
    email: str
    name: str | None
    raw: dict  # full response, for anything provider-specific


class OAuthProviderInterface(ABC):
    @abstractmethod
    def get_redirect_url(
        self,
        state: str,
        code_challenge: PKCECodeChallenge,
    ) -> str: ...

    @abstractmethod
    def exchange_code(self, code: str, code_verifier: str) -> AuthResponseData: ...

    @abstractmethod
    def get_user_data(self, access_token: str) -> UserData: ...
