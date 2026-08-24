from abc import ABC, abstractmethod

from pydantic import BaseModel


class AuthModel(BaseModel):
    access: str
    refresh: str


class AuthServiceInterface(ABC):
    @abstractmethod
    def get_redirect_url(self, state: str | None) -> str: ...

    @abstractmethod
    def authenticate(self, code: str) -> AuthModel: ...
