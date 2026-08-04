import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from users.user import User
from users.user_repository import SQLUserRepository

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
    with pytest.raises(ValueError):
        repo.update(user)


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
