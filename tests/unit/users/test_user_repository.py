import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import (
    DataError,
    DisconnectionError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    PendingRollbackError,
    ProgrammingError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from users.user import User
from users.user_repository import SQLUserRepository
from users.user_repository_interface import (
    UserAlreadyExistsError,
    UserNotFoundError,
    UserRepositoryError,
    UserRepositoryUnavailableError,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def session():
    from users.user_model import UserModel as UserSQL  # ruff: ignore[unused-import]

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session

    yield factory

    engine.dispose()


@pytest.fixture()
def repo(session):
    return SQLUserRepository(session)


@pytest.fixture()
def sample_user() -> User:
    return User(
        email="octocat@github.com",
        name="Octocat",
        admin=False,
        access=True,
    )


def test_get_by_id_returns_none_if_not_found(repo):
    assert repo.get_by_id(uuid.uuid4()) is None


def test_get_by_email_returns_none_if_not_found(repo):
    assert repo.get_by_email("does@not.exist") is None


def test_create_and_get_by_id(repo, sample_user):
    repo.create(sample_user)

    loaded = repo.get_by_id(sample_user.id)
    assert loaded is not None
    assert loaded.id == sample_user.id
    assert loaded.email == sample_user.email
    assert loaded.admin == sample_user.admin
    assert loaded.access == sample_user.access


def test_create_and_get_by_email(repo, sample_user):
    repo.create(sample_user)

    loaded = repo.get_by_email(sample_user.email)
    assert loaded is not None
    assert loaded.id == sample_user.id


def test_create_user_with_defaults(repo):
    user = User(email="default@example.com", name="Default")

    repo.create(user)

    loaded = repo.get_by_id(user.id)
    assert loaded is not None
    assert loaded.admin is False
    assert loaded.access is False


def test_create_admin_user(repo):
    user = User(email="admin@example.com", name="Admin", admin=True, access=True)

    repo.create(user)

    loaded = repo.get_by_id(user.id)
    assert loaded is not None
    assert loaded.admin is True
    assert loaded.access is True


def test_update_user(repo, sample_user):
    repo.create(sample_user)

    updated = User(
        id=sample_user.id,
        email=sample_user.email,
        name="Updated",
        admin=True,
        access=False,
    )
    repo.update(updated)

    loaded = repo.get_by_id(sample_user.id)
    assert loaded.admin is True
    assert loaded.access is False


def test_update_raises_if_not_found(repo):
    user = User(
        id=uuid.uuid4(),
        email="ghost@example.com",
        name="ghost",
    )
    with pytest.raises(UserNotFoundError):
        repo.update(user)


def test_create_with_an_existing_id_raises_already_exists(repo, sample_user):
    repo.create(sample_user)

    with pytest.raises(UserAlreadyExistsError) as exc:
        repo.create(sample_user)

    assert isinstance(exc.value.__cause__, IntegrityError)


def test_delete_user(repo, sample_user):
    repo.create(sample_user)
    repo.delete(sample_user.id)

    assert repo.get_by_id(sample_user.id) is None


def test_delete_does_nothing_if_not_found(repo):
    repo.delete(uuid.uuid4())  # assert no raise


def test_update_does_not_change_email(repo, sample_user):
    repo.create(sample_user)

    updated = User(
        id=sample_user.id,
        email="newemail@example.com",
        name="Octocat",
        admin=True,
        access=True,
    )
    repo.update(updated)

    loaded = repo.get_by_id(sample_user.id)
    assert loaded.email == sample_user.email


def test_create_returns_domain_user(repo, sample_user):
    result = repo.create(sample_user)

    assert isinstance(result, User)
    assert result.id == sample_user.id
    assert result.email == sample_user.email


def test_update_returns_domain_user(repo, sample_user):
    repo.create(sample_user)

    updated = User(
        id=sample_user.id,
        email=sample_user.email,
        name="Octocat",
        admin=True,
        access=True,
    )
    result = repo.update(updated)

    assert isinstance(result, User)
    assert result.admin is True


class _FakeDriverError(Exception):
    """Stands in for a DBAPI exception (``err.orig``) carrying a SQLSTATE."""

    def __init__(self, pgcode: str | None = None):
        super().__init__()
        self.pgcode = pgcode


def _raising_repo(error: Exception) -> SQLUserRepository:
    @contextmanager
    def factory():
        raise error
        yield  # pragma: no cover

    return SQLUserRepository(factory)


def _dbapi(cls, pgcode: str | None = None, **kwargs):
    statement = "SELECT 1"
    return cls(statement, {}, _FakeDriverError(pgcode), **kwargs)


class TestErrorTranslation:
    """SQLAlchemy errors must not leak, and must be classified, so callers can
    tell "retry later" from "already exists" from "needs a fix"."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            pytest.param(
                _dbapi(OperationalError), UserRepositoryUnavailableError, id="operational"
            ),
            pytest.param(_dbapi(InterfaceError), UserRepositoryUnavailableError, id="interface"),
            pytest.param(DisconnectionError(), UserRepositoryUnavailableError, id="disconnect"),
            pytest.param(PoolTimeoutError(), UserRepositoryUnavailableError, id="pool-exhausted"),
            pytest.param(
                _dbapi(ProgrammingError, connection_invalidated=True),
                UserRepositoryUnavailableError,
                id="connection-invalidated",
            ),
            pytest.param(
                _dbapi(IntegrityError, pgcode="23505"), UserAlreadyExistsError, id="unique"
            ),
            pytest.param(
                _dbapi(IntegrityError, pgcode="23502"), UserRepositoryError, id="not-null"
            ),
            pytest.param(_dbapi(ProgrammingError), UserRepositoryError, id="programming"),
            pytest.param(_dbapi(DataError), UserRepositoryError, id="data"),
            pytest.param(PendingRollbackError(), UserRepositoryError, id="pending-rollback"),
        ],
    )
    def test_classification(self, sample_user, error, expected):
        with pytest.raises(UserRepositoryError) as exc:
            _raising_repo(error).create(sample_user)

        assert type(exc.value) is expected
        assert exc.value.__cause__ is error

    @pytest.mark.parametrize(
        "call",
        [
            lambda repo, u: repo.get_by_id(u.id),
            lambda repo, u: repo.get_by_email(u.email),
            lambda repo, u: repo.create(u),
            lambda repo, u: repo.update(u),
            lambda repo, u: repo.delete(u.id),
        ],
        ids=["get_by_id", "get_by_email", "create", "update", "delete"],
    )
    def test_every_method_translates(self, sample_user, call):
        with pytest.raises(UserRepositoryUnavailableError):
            call(_raising_repo(_dbapi(OperationalError)), sample_user)

    def test_non_database_errors_are_not_translated(self, sample_user):
        """Only SQLAlchemy errors are the repository's to classify; bugs stay bugs."""
        with pytest.raises(KeyError):
            _raising_repo(KeyError("bug")).get_by_id(sample_user.id)
