from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


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
        :raises InvalidLoginTransactionError: transaction missing/invalid or state mismatch
        :raises LoginRejectedError: the provider rejected the code or the identity
        :raises AuthProviderUnavailableError: the provider is unreachable or erroring
        :raises InfrastructureUnavailableError: user database or token store failed
        """
        ...

    @abstractmethod
    def refresh(self, refresh_token: str | None) -> AuthModel:
        """
        :raises InvalidSessionError: the token is not (or no longer) a valid session
        :raises InfrastructureUnavailableError: user database or token store failed
        """
        ...

    @abstractmethod
    def logout(self, refresh_token: str | None) -> None:
        """A missing or invalid token is a no-op, not an error.

        :raises InfrastructureUnavailableError: the session could not be revoked
        """
        ...
