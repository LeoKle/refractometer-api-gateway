import functools
import uuid
from collections.abc import Callable

from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from containers.database import SessionFactory
from users.user import User as UserDomain
from users.user_model import UserModel as UserSQL
from users.user_repository_interface import (
    UserAlreadyExistsError,
    UserNotFoundError,
    UserRepositoryError,
    UserRepositoryInterface,
    UserRepositoryUnavailableError,
)

# SQLSTATE 23505 (PostgreSQL); sqlite3 (used in tests) has no SQLSTATE and
# reports the extended result code name instead.
_UNIQUE_VIOLATION_SQLSTATE = "23505"
_UNIQUE_VIOLATION_SQLITE = {"SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY"}

# Retrying later may succeed. OperationalError covers connection loss and
# timeouts but also aborted transactions (deadlock, serialization failure);
# PoolTimeoutError means every pooled connection was busy.
_TRANSIENT_ERRORS = (OperationalError, InterfaceError, DisconnectionError, PoolTimeoutError)


def _is_unique_violation(err: IntegrityError) -> bool:
    orig = err.orig
    sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if sqlstate is not None:
        return sqlstate == _UNIQUE_VIOLATION_SQLSTATE
    return getattr(orig, "sqlite_errorname", None) in _UNIQUE_VIOLATION_SQLITE


def _translate(err: SQLAlchemyError, operation: str) -> UserRepositoryError:
    """Map a SQLAlchemy exception onto the repository contract's error types."""
    reason = f"User database failed during {operation}: {type(err).__name__}"

    if isinstance(err, IntegrityError) and _is_unique_violation(err):
        return UserAlreadyExistsError(f"User already exists ({operation})")
    if isinstance(err, _TRANSIENT_ERRORS):
        return UserRepositoryUnavailableError(reason)
    if isinstance(err, DBAPIError) and err.connection_invalidated:
        return UserRepositoryUnavailableError(reason)
    # ProgrammingError (schema mismatch, missing privilege), DataError, other
    # IntegrityErrors (NOT NULL, FK), PendingRollbackError, ...
    return UserRepositoryError(reason)


def _translate_db_errors[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """Let no SQLAlchemy exception escape a repository method untranslated."""

    @functools.wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except SQLAlchemyError as err:
            raise _translate(err, method.__name__) from err

    return wrapper


class SQLUserRepository(UserRepositoryInterface):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    @_translate_db_errors
    def get_by_id(self, id: uuid.UUID) -> UserDomain | None:
        with self.session_factory() as session:
            row = session.get(UserSQL, id)
            return self._to_domain(row) if row else None

    @_translate_db_errors
    def get_by_email(self, email: str) -> UserDomain | None:
        with self.session_factory() as session:
            row = session.query(UserSQL).filter(UserSQL.email == email).first()
            return self._to_domain(row) if row else None

    @_translate_db_errors
    def create(self, user: UserDomain) -> UserDomain:
        with self.session_factory() as session:
            row = self._to_sql(user)
            session.add(row)
            session.commit()
            return self._to_domain(row)

    @_translate_db_errors
    def update(self, user: UserDomain) -> UserDomain:
        with self.session_factory() as session:
            row = session.get(UserSQL, user.id)
            if not row:
                msg = f"user {user.id} not found"
                raise UserNotFoundError(msg)
            row.admin = user.admin
            row.access = user.access
            session.commit()
            return self._to_domain(row)

    @_translate_db_errors
    def delete(self, user_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            row = session.get(UserSQL, user_id)
            if row:
                session.delete(row)
                session.commit()

    @staticmethod
    def _to_domain(row: UserDomain) -> UserDomain:
        return UserDomain(
            id=row.id,
            email=row.email,
            name=row.name,
            admin=row.admin,
            access=row.access,
        )

    @staticmethod
    def _to_sql(user: UserDomain) -> UserDomain:
        return UserSQL(
            id=user.id,
            email=user.email,
            name=user.name,
            admin=user.admin,
            access=user.access,
        )
