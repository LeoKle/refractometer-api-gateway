from abc import ABC, abstractmethod

from pydantic import BaseModel

from auth.oauth_transaction import OAuthTransaction


class AuthenticationError(Exception):
    """Raised when authentication fails for a reason the caller can't retry
    by itself (bad code, provider rejected the account, etc.)."""


class AuthProviderUnavailableError(AuthenticationError):
    """The OAuth provider couldn't be reached or is erroring. Distinct from
    AuthenticationError so callers can map this to 503 instead of 400/401."""


class AuthModel(BaseModel):
    access: str
    refresh: str


class AuthServiceInterface(ABC):
    @abstractmethod
    def start_login(self, redirect_to: str | None) -> tuple[str, OAuthTransaction]: ...

    @abstractmethod
    def authenticate(self, code: str, code_verifier: str) -> AuthModel: ...
