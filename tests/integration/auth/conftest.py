import os

os.environ.setdefault("ENV", "test")

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import fakeredis
import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dependency_injector import providers
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis import Redis
from sqlmodel import SQLModel

from api.app import app, container
from auth.redis_refresh_token_repository import RedisRefreshTokenRepository
from containers.database import Database
from settings import get_settings
from tests.integration.auth.fake_github import FakeGitHub, GitHubAccount
from users.user import User
from users.user_model import (
    UserModel,  # ruff: ignore[unused-import]  (ensure the table is registered)
)
from users.user_repository import SQLUserRepository

BASE_URL = "http://testserver"
COOKIE_DOMAIN = "testserver.local"  # how the cookie jar records the TestClient host
CALLBACK_PATH = "/api/v1/auth/callback"
CLIENT_ID = "integration-client-id"
CLIENT_SECRET = "integration-client-secret"

LOGIN = "/api/v1/auth/login"
CALLBACK = CALLBACK_PATH
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
USER = "/api/v1/auth/user"


# keys / settings


@dataclass(frozen=True)
class KeyPair:
    private_pem: str
    public_pem: str


def _ed25519_pair() -> KeyPair:
    key = Ed25519PrivateKey.generate()
    return KeyPair(
        private_pem=key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        public_pem=key
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode(),
    )


@pytest.fixture(scope="session")
def signing_keys() -> KeyPair:
    return _ed25519_pair()


@pytest.fixture(scope="session")
def attacker_keys() -> KeyPair:
    """A well-formed key the gateway does not trust."""
    return _ed25519_pair()


@pytest.fixture(autouse=True)
def settings(monkeypatch, signing_keys):
    s = get_settings()
    monkeypatch.setattr(s, "JWT_ALGORITHM", "EdDSA")
    monkeypatch.setattr(s, "JWT_PRIVATE_KEY", SecretStr(signing_keys.private_pem))
    monkeypatch.setattr(s, "JWT_PUBLIC_KEY", signing_keys.public_pem)
    monkeypatch.setattr(s, "OAUTH_URL", "https://github.com")
    monkeypatch.setattr(s, "OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(s, "OAUTH_CLIENT_SECRET", SecretStr(CLIENT_SECRET))
    monkeypatch.setattr(s, "OAUTH_REDIRECT_URL", BASE_URL + CALLBACK_PATH)
    monkeypatch.setattr(s, "OAUTH_SCOPES", "read:user user:email")
    return s


# infrastructure


@pytest.fixture
def database(tmp_path) -> Iterator[Database]:
    url = os.environ.get("INTEGRATION_DATABASE_URL", f"sqlite:///{tmp_path / 'gateway.db'}")
    db = Database(url)
    engine = db._engine
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield db
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def redis_server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture
def redis_client(redis_server) -> Iterator[Redis]:
    url = os.environ.get("INTEGRATION_REDIS_URL")
    client = Redis.from_url(url) if url else fakeredis.FakeRedis(server=redis_server)
    client.flushdb()
    yield client
    if url:
        client.flushdb()
    client.close()


@pytest.fixture(autouse=True)
def wired_container(database, redis_client) -> Iterator[None]:
    """Point the production container at the test infrastructure. Every other
    provider (auth service, repositories, OAuth provider) stays real."""
    with (
        container.db.override(providers.Object(database)),
        container.redis_client.override(providers.Object(redis_client)),
    ):
        yield


@pytest.fixture
def github() -> Iterator[FakeGitHub]:
    fake = FakeGitHub(CLIENT_ID, CLIENT_SECRET, BASE_URL + CALLBACK_PATH)
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        fake.install(router)
        router.route(host="testserver").pass_through()
        yield fake


# app access


@pytest.fixture
def client(github) -> Iterator[TestClient]:
    with TestClient(
        app, base_url=BASE_URL, follow_redirects=False, raise_server_exceptions=False
    ) as c:
        yield c


@pytest.fixture
def make_client(github):
    """Additional, independent browsers (separate cookie jars)."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        c = TestClient(
            app, base_url=BASE_URL, follow_redirects=False, raise_server_exceptions=False
        )
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.close()


@pytest.fixture
def user_repo() -> SQLUserRepository:
    return container.user_repository()


@pytest.fixture
def refresh_repo() -> RedisRefreshTokenRepository:
    return container.refresh_token_repository()


@pytest.fixture
def alice() -> GitHubAccount:
    return GitHubAccount.with_email(1001, "alice", "alice@example.com")


@pytest.fixture
def mallory() -> GitHubAccount:
    return GitHubAccount.with_email(6666, "mallory", "mallory@evil.example")


# flow helpers


def cookie_names() -> tuple[str, str, str]:
    s = get_settings()
    return s.COOKIE_NAME_ACCESS, s.COOKIE_NAME_REFRESH, s.COOKIE_NAME_OAUTH_TRANSACTION


def set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    """cookie name -> full Set-Cookie header"""
    return {h.split("=", 1)[0]: h for h in response.headers.get_list("set-cookie")}


def plant_cookie(client: TestClient, name: str, value: str, path: str = "/") -> None:
    """Replace whatever the browser holds under `name` with `value`, the way an
    attacker (or a replaying client) would. Only one cookie of that name remains,
    so the server cannot fall back to a genuine one."""
    for cookie in [c for c in client.cookies.jar if c.name == name]:
        client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    client.cookies.set(name, value, domain=COOKIE_DOMAIN, path=path)


def plant_transaction(client: TestClient, value: str) -> None:
    plant_cookie(client, cookie_names()[2], value, path="/api/v1/auth")


def query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def start_login(client: TestClient, redirect_to: str | None = None) -> str:
    """GET /login; returns the GitHub authorize URL. The transaction cookie
    lands in the client's cookie jar."""
    params = {"redirect_to": redirect_to} if redirect_to is not None else {}
    response = client.get(LOGIN, params=params)
    assert response.status_code == 307, response.text
    return response.headers["location"]


def callback(client: TestClient, code: str, state: str | None) -> httpx.Response:
    params = {"code": code}
    if state is not None:
        params["state"] = state
    return client.get(CALLBACK, params=params)


def login(
    client: TestClient,
    github: FakeGitHub,
    account: GitHubAccount,
    redirect_to: str | None = None,
) -> httpx.Response:
    """The full browser round trip: gateway -> GitHub -> gateway."""
    authorize_url = start_login(client, redirect_to)
    code, state = github.authorize(authorize_url, account)
    return callback(client, code, state)


def grant_access(user_repo: SQLUserRepository, email: str, *, admin: bool = False) -> User:
    user = user_repo.get_by_email(email)
    assert user is not None, f"{email} was never created"
    user.access = True
    user.admin = admin
    return user_repo.update(user)


def logged_in(client: TestClient, github: FakeGitHub, account: GitHubAccount, user_repo) -> User:
    """Log in and grant access, so /user answers 200."""
    response = login(client, github, account)
    assert response.status_code == 307, response.text
    return grant_access(user_repo, account.primary_email)
