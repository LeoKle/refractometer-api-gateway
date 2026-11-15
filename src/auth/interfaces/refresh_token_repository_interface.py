import uuid
from abc import ABC, abstractmethod
from enum import StrEnum

from auth.tokens import JsonWebToken


class RefreshTokenRepositoryError(Exception):
    """Base for every failure of the refresh token repository."""


class RefreshTokenRepositoryUnavailableError(RefreshTokenRepositoryError):
    """the repository is unreachable, timed out, out of connections,
    still loading, failing over (read-only, cluster down) or out of memory.
    The same operation may succeed when retried later."""


class RefreshTokenRotationResult(StrEnum):
    OK = "ok"
    """The presented token was the family's current one and has been replaced."""

    REUSE = "reuse"
    """The family exists but the presented token is not its current one: it was
    already rotated away, so it is a replay. The family has been revoked."""

    UNKNOWN = "unknown"
    """No such family: expired, logged out, revoked, or never issued."""


class RefreshTokenRepositoryInterface(ABC):
    @abstractmethod
    def start(self, refresh_token: JsonWebToken) -> None:
        """Register the first refresh token of a new family (call at login)."""
        ...

    @abstractmethod
    def rotate(self, presented: JsonWebToken, new: JsonWebToken) -> RefreshTokenRotationResult:
        """Atomically replace `presented` with `new` as the family's valid token.

        Must be atomic so that two concurrent requests with the same token
        cannot both succeed. Reuse of a stale token revokes the whole family.
        """
        ...

    @abstractmethod
    def revoke_family(self, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
        """Revoke one session (logout on this device). Idempotent."""
        ...

    @abstractmethod
    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every session of a user (logout everywhere). Idempotent."""
        ...
