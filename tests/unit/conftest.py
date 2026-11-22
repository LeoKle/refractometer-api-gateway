import os

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from api.app import app, container
from auth.guards import get_user
from tests.mocks.mock_user_repository import MockUserRepository
from users.user import User

os.environ.setdefault("ENV", "test")

LEAK = "internal error / detail that must not reach the client"


@pytest.fixture
def user() -> User:
    return User(email="user@example.com", name="User", access=True)


@pytest.fixture
def client(user: User):
    """Authenticated client: the auth guard is replaced by a fixed user."""
    app.dependency_overrides[get_user] = lambda: user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_user, None)


@pytest.fixture
def anonymous_client():
    """Client that runs the real auth guard without credentials."""
    with container.user_repository.override(providers.Object(MockUserRepository())):
        yield TestClient(app, raise_server_exceptions=False)
