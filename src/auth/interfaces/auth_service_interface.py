from abc import ABC, abstractmethod

from pydantic import BaseModel

from auth.oauth_transaction import OAuthTransaction


class AuthModel(BaseModel):
    access: str
    refresh: str


class AuthServiceInterface(ABC):
    @abstractmethod
    def start_login(self, redirect_to: str | None) -> tuple[str, OAuthTransaction]: ...

    @abstractmethod
    def authenticate(self, code: str) -> AuthModel: ...
