import uuid
from abc import ABC, abstractmethod

from users.user import User


class UserRepositoryError(Exception):
    """Base for every failure of the user repository."""


class UserRepositoryUnavailableError(UserRepositoryError):
    """Transient: the database is unreachable, timed out, dropped the
    connection, ran out of pooled connections, or aborted the transaction
    (deadlock, serialization failure). The same call may succeed when retried."""


class UserAlreadyExistsError(UserRepositoryError):
    """A user with the same unique key (id, or email once it is unique) exists."""


class UserNotFoundError(UserRepositoryError):
    """The user an operation requires does not exist."""


class UserRepositoryInterface(ABC):
    """Every method raises ``UserRepositoryUnavailableError`` on transient
    failures and ``UserRepositoryError`` on any other database failure, in
    addition to the errors listed per method."""

    @abstractmethod
    def get_by_id(self, id: uuid.UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def create(self, user: User) -> User:
        """:raises UserAlreadyExistsError: a user with the same unique key exists"""
        ...

    @abstractmethod
    def update(self, user: User) -> User:
        """:raises UserNotFoundError: no user with ``user.id`` exists"""
        ...

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> None:
        """Idempotent: deleting a missing user is not an error."""
        ...
