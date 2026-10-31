from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class AuthenticationError(Exception):
    """Raised when authentication fails for a reason the caller can't retry
    by itself (bad code, provider rejected the account, etc.)."""


class AuthProviderUnavailableError(AuthenticationError):
    """The OAuth provider couldn't be reached or is erroring. Distinct from
    AuthenticationError so callers can map this to 503 instead of 400/401."""


class InvalidLoginTransactionError(AuthenticationError): ...


class InvalidSessionError(AuthenticationError): ...


class AuthModel(BaseModel):
    access: str
    refresh: str


class LoginStart(BaseModel):
    url: str = Field(..., description="the URL the user has to complete the authorization on")
    transaction: str = Field(
        ...,
        description="a signed JWT containing CSRF state, PKCE code verifier "
        "and frontend page to redirect to",
    )


class LoginResult(BaseModel):
    access_token: str
    refresh_token: str
    redirect_to: str = Field(..., description="The frontend page to redirect to")


class AuthServiceInterface(ABC):
    @abstractmethod
    def start_login(self, redirect_to: str | None) -> LoginStart: ...

    @abstractmethod
    def complete_login(self, code: str, state: str | None, transaction: str | None) -> LoginResult:
        """
        :param str code: The authorization code from the OAuthProvider
        :param str state: The CSRF state
        :param str | None transaction: The transaction JWT
        """
        ...
