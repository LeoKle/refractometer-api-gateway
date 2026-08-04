import uuid
from abc import ABC, abstractmethod

from users.user import User


class UserRepositoryInterface(ABC):
    @abstractmethod
    def get_by_id(self, id: uuid.UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def create(self, user: User) -> User: ...

    @abstractmethod
    def update(self, user: User) -> User: ...

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> None: ...
