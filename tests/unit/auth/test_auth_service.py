import base64
import hashlib
import logging
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import create_autospec

import jwt
import pytest
from pydantic import SecretStr

from auth.auth_service import AuthService  # adjust to wherever AuthService lives
from auth.exceptions import (
    AuthError,
    AuthProviderUnavailableError,
    InfrastructureUnavailableError,
    InvalidLoginTransactionError,
    InvalidSessionError,
    LoginRejectedError,
)
from auth.interfaces.auth_service_interface import AuthModel, LoginResult
from auth.interfaces.oauth_provider_interface import (
    OAuthExchangeError,
    OAuthProviderInterface,
    OAuthUnavailableError,
    OAuthUserDataError,
)
from auth.interfaces.refresh_token_repository_interface import (
    RefreshTokenRepositoryError,
    RefreshTokenRepositoryUnavailableError,
)
from auth.oauth_transaction import OAuthTransaction, decode_transaction, encode_transaction
from auth.tokens import JsonWebToken
from settings import get_settings
from tests.mocks.mock_refresh_token_repository import MockRefreshTokenRepository
from tests.mocks.mock_user_repository import MockUserRepository
from users.user import User
from users.user_repository_interface import (
    UserAlreadyExistsError,
    UserRepositoryError,
    UserRepositoryUnavailableError,
)

pytestmark = pytest.mark.unit


TEST_ALGORITHM = "HS256"
TEST_PRIVATE_KEY = SecretStr(
    "test-secret-that-is-at-least-64-bytes-long-so-pyjwt-does-not-throw-warnings"
)
TEST_PRIVATE_KEY_RAW = TEST_PRIVATE_KEY.get_secret_value()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.get_secret_value()
TEST_ISSUER = "test-issuer"
TEST_AUDIENCE = "test-audience"
TEST_ACCESS_TTL = 10  # minutes
TEST_REFRESH_TTL = 31  # days
USER_EMAIL = "user@example.com"
AUTH_CODE = "secret-auth-code-xyz"


@pytest.fixture(autouse=True)
def pinned_settings(monkeypatch):
    """set settings for tests"""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", TEST_ALGORITHM)
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", TEST_PUBLIC_KEY)
    monkeypatch.setattr(settings, "JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "JWT_ACCESS_TOKEN_TTL", TEST_ACCESS_TTL)
    monkeypatch.setattr(settings, "JWT_REFRESH_TOKEN_TTL", TEST_REFRESH_TTL)


class FailingRefreshTokenRepository(MockRefreshTokenRepository):
    """Behaves like a store that is down, per the repository contract."""

    def __init__(self, error: Exception | None = None):
        super().__init__()
        self.error = error or RefreshTokenRepositoryUnavailableError("store is down")

    def start(self, token):
        raise self.error

    def rotate(self, presented, new):
        raise self.error

    def revoke_family(self, user_id, family_id):
        raise self.error


class FailingUserRepository(MockUserRepository):
    """Behaves like a failing database, per the repository contract."""

    def __init__(self, error: Exception | None = None):
        super().__init__()
        self.error = error or UserRepositoryUnavailableError("db is down")

    def get_by_id(self, id):
        raise self.error

    def get_by_email(self, email):
        raise self.error


class RacingUserRepository(MockUserRepository):
    """Another request creates the same user between our read and our insert."""

    def __init__(self, winner: User | None):
        super().__init__()
        self.winner = winner

    def create(self, user):
        if self.winner is not None:
            self.users[self.winner.id] = self.winner
        msg = "duplicate email"
        raise UserAlreadyExistsError(msg)


def make_user(*, access: bool = True, email: str = USER_EMAIL, id: uuid.UUID | None = None) -> User:
    return User(id=id or uuid.uuid4(), email=email, name="Test User", admin=False, access=access)


@pytest.fixture
def provider():
    p = create_autospec(OAuthProviderInterface, instance=True)
    p.get_redirect_url.return_value = "https://provider.example/authorize?x=1"
    # The service only reads .access_token / .email / .name from these results
    p.exchange_code.return_value = SimpleNamespace(access_token="provider-access-token")
    p.get_user_data.return_value = SimpleNamespace(email=USER_EMAIL, name="Test User")
    return p


@pytest.fixture
def user_repo() -> MockUserRepository:
    return MockUserRepository()


@pytest.fixture
def refresh_repo() -> MockRefreshTokenRepository:
    return MockRefreshTokenRepository()


@pytest.fixture
def service(provider, user_repo, refresh_repo) -> AuthService:
    return AuthService(
        oauth_provider=provider,
        user_repo=user_repo,
        refresh_token_repo=refresh_repo,
    )


@pytest.fixture
def user(user_repo) -> User:
    return user_repo.create(make_user())


def make_transaction(redirect_to: str = "/dashboard") -> OAuthTransaction:
    return OAuthTransaction(
        state="state-123", code_verifier="verifier-abc", redirect_to=redirect_to
    )


def login(service: AuthService, redirect_to: str = "/dashboard") -> LoginResult:
    transaction = make_transaction(redirect_to)
    return service.complete_login(AUTH_CODE, transaction.state, encode_transaction(transaction))


@pytest.fixture
def session(service, user) -> LoginResult:
    """A completed login for an existing user."""
    return login(service)


def decode(token: str, token_type: str) -> JsonWebToken:
    return JsonWebToken.decode(token, token_type)


class TestStartLogin:
    def test_returns_the_providers_authorization_url(self, service, provider):
        result = service.start_login("/dashboard")

        assert result.url == provider.get_redirect_url.return_value

    def test_transaction_matches_what_was_sent_to_the_provider(self, service, provider):
        result = service.start_login("/dashboard")
        state, code_challenge = provider.get_redirect_url.call_args.args

        transaction = decode_transaction(result.transaction)

        assert transaction is not None
        assert transaction.state == state
        assert transaction.redirect_to == "/dashboard"

        digest = hashlib.sha256(transaction.code_verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        assert code_challenge.code_challenge == expected_challenge
        assert code_challenge.code_challenge_method == "S256"

    @pytest.mark.parametrize(
        "unsafe", ["https://evil.example", "//evil.example", "javascript:alert(1)", "\\evil"]
    )
    def test_unsafe_redirect_target_is_replaced(self, service, unsafe):
        result = service.start_login(unsafe)

        assert decode_transaction(result.transaction).redirect_to == "/"

    def test_each_login_gets_a_fresh_state(self, service):
        a = decode_transaction(service.start_login(None).transaction)
        b = decode_transaction(service.start_login(None).transaction)

        assert a.state != b.state
        assert a.code_verifier != b.code_verifier


class TestCompleteLoginSuccess:
    def test_returns_valid_tokens_for_the_user(self, session, user):
        access = decode(session.access_token, "access")
        refresh = decode(session.refresh_token, "refresh")

        assert access.sub == user.id
        assert refresh.sub == user.id

    def test_redirects_to_the_requested_page(self, service, user):
        result = login(service, redirect_to="/settings")

        assert result.redirect_to == "/settings"

    def test_access_and_refresh_token_share_a_family(self, session):
        access = decode(session.access_token, "access")
        refresh = decode(session.refresh_token, "refresh")

        assert access.fid == refresh.fid
        assert access.jti != refresh.jti

    def test_the_refresh_token_family_is_registered(self, session, refresh_repo):
        refresh = decode(session.refresh_token, "refresh")

        assert refresh.fid in refresh_repo.families

    def test_each_login_starts_its_own_family(self, service, user):
        first = decode(login(service).refresh_token, "refresh")
        second = decode(login(service).refresh_token, "refresh")

        assert first.fid != second.fid

    def test_code_exchange_uses_the_verifier_from_the_transaction(self, service, provider, user):
        login(service)

        provider.exchange_code.assert_called_once_with(AUTH_CODE, "verifier-abc")

    def test_user_data_is_fetched_with_the_providers_access_token(self, service, provider, user):
        login(service)

        provider.get_user_data.assert_called_once_with("provider-access-token")

    def test_unknown_user_is_created(self, service, provider, user_repo):
        provider.get_user_data.return_value = SimpleNamespace(
            email="new@example.com", name="New Person"
        )

        result = login(service)

        created = user_repo.get_by_email("new@example.com")
        assert created is not None
        assert created.name == "New Person"
        assert decode(result.access_token, "access").sub == created.id

    def test_existing_user_is_not_duplicated(self, service, user_repo, user):
        login(service)
        login(service)

        assert len(user_repo.users) == 1


class TestCompleteLoginTransactionErrors:
    def test_missing_transaction(self, service, provider):
        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, "state-123", None)

        provider.exchange_code.assert_not_called()

    def test_garbage_transaction(self, service, provider):
        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, "state-123", "not.a.jwt")

        provider.exchange_code.assert_not_called()

    def test_transaction_signed_with_another_secret(self, service, provider):
        transaction = make_transaction()
        forged = jwt.encode(
            {**transaction.model_dump(), "type": "oauth_transaction", "exp": 4102444800},
            "another-secret-that-is-also-long-enough-to-avoid-key-length-warnings",
            algorithm="HS256",
        )

        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, transaction.state, forged)

        provider.exchange_code.assert_not_called()

    def test_session_token_is_not_accepted_as_a_transaction(self, service, provider, user):
        """Both are signed with the same key; a refresh JWT must not pass as a transaction."""
        refresh = JsonWebToken.refresh(user.id).encode()

        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, "state-123", refresh)

        provider.exchange_code.assert_not_called()

    @pytest.mark.parametrize("state", [None, "", "wrong-state"])
    def test_missing_or_wrong_state(self, service, provider, state):
        transaction = make_transaction()

        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, state, encode_transaction(transaction))

        provider.exchange_code.assert_not_called()

    def test_failed_transaction_check_issues_nothing(self, service, user_repo, refresh_repo):
        with pytest.raises(InvalidLoginTransactionError):
            service.complete_login(AUTH_CODE, "wrong-state", encode_transaction(make_transaction()))

        assert user_repo.users == {}
        assert refresh_repo.families == {}

    def test_logs_never_contain_the_code_or_the_transaction(self, service, caplog):
        caplog.set_level(logging.DEBUG)
        transaction = encode_transaction(make_transaction())

        for state, tx in [("wrong-state", transaction), ("state-123", "garbage"), ("s", None)]:
            with pytest.raises(InvalidLoginTransactionError):
                service.complete_login(AUTH_CODE, state, tx)

        assert AUTH_CODE not in caplog.text
        assert transaction not in caplog.text
        assert "verifier-abc" not in caplog.text


class TestCompleteLoginProviderErrors:
    def test_network_error_during_code_exchange(self, service, provider):
        provider.exchange_code.side_effect = OAuthUnavailableError()

        with pytest.raises(AuthProviderUnavailableError):
            login(service)

    def test_rejected_code_exchange(self, service, provider):
        provider.exchange_code.side_effect = OAuthExchangeError()

        with pytest.raises(LoginRejectedError):
            login(service)

    def test_network_error_during_user_data_fetch(self, service, provider):
        provider.get_user_data.side_effect = OAuthUnavailableError()

        with pytest.raises(AuthProviderUnavailableError):
            login(service)

    def test_rejected_user_data(self, service, provider):
        provider.get_user_data.side_effect = OAuthUserDataError()

        with pytest.raises(LoginRejectedError):
            login(service)

    def test_provider_error_is_chained(self, service, provider):
        """The original provider error stays available for logs/debugging."""
        original = OAuthExchangeError("bad_verification_code")
        provider.exchange_code.side_effect = original

        with pytest.raises(LoginRejectedError) as exc:
            login(service)

        assert exc.value.__cause__ is original

    @pytest.mark.parametrize(
        ("target", "error"),
        [
            ("exchange_code", OAuthUnavailableError),
            ("exchange_code", OAuthExchangeError),
            ("get_user_data", OAuthUnavailableError),
            ("get_user_data", OAuthUserDataError),
        ],
    )
    def test_provider_failure_issues_no_session(
        self, service, provider, user_repo, refresh_repo, target, error
    ):
        getattr(provider, target).side_effect = error()

        with pytest.raises(AuthError):
            login(service)

        assert user_repo.users == {}
        assert refresh_repo.families == {}

    def test_unexpected_errors_are_not_swallowed(self, service, provider):
        provider.exchange_code.side_effect = RuntimeError("bug")

        with pytest.raises(RuntimeError):
            login(service)


class TestCompleteLoginInfrastructureFailures:
    def test_user_database_outage(self, provider, refresh_repo):
        service = AuthService(provider, FailingUserRepository(), refresh_repo)

        with pytest.raises(InfrastructureUnavailableError):
            login(service)

        assert refresh_repo.families == {}

    def test_token_store_outage(self, provider, user_repo):
        service = AuthService(provider, user_repo, FailingRefreshTokenRepository())

        with pytest.raises(InfrastructureUnavailableError):
            login(service)

    @pytest.mark.parametrize(
        "error",
        [RefreshTokenRepositoryError("ACL denied"), KeyError("bug")],
        ids=["permanent-store-error", "bug"],
    )
    def test_only_transient_store_errors_are_outages(self, provider, user_repo, error):
        """Permanent failures and bugs need a fix, not a retry: they must not become 503."""
        service = AuthService(provider, user_repo, FailingRefreshTokenRepository(error))

        with pytest.raises(type(error)):
            login(service)

    def test_permanent_database_errors_are_not_outages(self, provider, refresh_repo):
        error = UserRepositoryError("schema mismatch")
        service = AuthService(provider, FailingUserRepository(error), refresh_repo)

        with pytest.raises(UserRepositoryError) as exc:
            login(service)

        assert exc.value is error

    def test_concurrent_first_login_reuses_the_winning_user(self, provider, refresh_repo):
        winner = make_user()
        service = AuthService(provider, RacingUserRepository(winner), refresh_repo)

        result = login(service)

        assert decode(result.access_token, "access").sub == winner.id

    def test_conflict_without_a_winner_is_not_swallowed(self, provider, refresh_repo):
        service = AuthService(provider, RacingUserRepository(None), refresh_repo)

        with pytest.raises(UserAlreadyExistsError):
            login(service)


class TestRefreshRejections:
    def test_missing_token(self, service, refresh_repo):
        with pytest.raises(InvalidSessionError):
            service.refresh(None)

        assert refresh_repo.rotate_calls == 0

    def test_garbage_token(self, service, refresh_repo):
        with pytest.raises(InvalidSessionError):
            service.refresh("not.a.jwt")

        assert refresh_repo.rotate_calls == 0

    def test_expired_token(self, service, refresh_repo, user):
        expired = JsonWebToken.create(user.id, "refresh", timedelta(minutes=-1)).encode()

        with pytest.raises(InvalidSessionError):
            service.refresh(expired)

        assert refresh_repo.rotate_calls == 0

    def test_access_token_is_not_accepted(self, service, session, refresh_repo):
        with pytest.raises(InvalidSessionError):
            service.refresh(session.access_token)

        assert refresh_repo.rotate_calls == 0

    def test_unknown_user(self, service, refresh_repo):
        orphan = JsonWebToken.refresh(uuid.uuid4()).encode()

        with pytest.raises(InvalidSessionError):
            service.refresh(orphan)

        assert refresh_repo.rotate_calls == 0

    def test_user_without_access(self, service, session, user, user_repo, refresh_repo):
        user_repo.users[user.id] = make_user(access=False, id=user.id)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

        assert refresh_repo.rotate_calls == 0

    def test_denied_refresh_does_not_burn_the_token(self, service, session, user, user_repo):
        """The access check runs before rotation, so a rejected request changes no state."""
        user_repo.users[user.id] = make_user(access=False, id=user.id)
        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

        user_repo.users[user.id] = make_user(access=True, id=user.id)

        assert isinstance(service.refresh(session.refresh_token), AuthModel)

    def test_family_never_registered(self, service, user, refresh_repo):
        """Validly signed, but the store has never heard of it (e.g. store was wiped)."""
        unregistered = JsonWebToken.refresh(user.id).encode()

        with pytest.raises(InvalidSessionError):
            service.refresh(unregistered)

    def test_revoked_family(self, service, session, user, refresh_repo):
        refresh = decode(session.refresh_token, "refresh")
        refresh_repo.revoke_family(user.id, refresh.fid)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

    def test_all_sessions_revoked(self, service, session, user, refresh_repo):
        refresh_repo.revoke_all_for_user(user.id)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)


class TestRefreshSuccess:
    def test_returns_new_valid_tokens(self, service, session, user):
        result = service.refresh(session.refresh_token)

        assert decode(result.access, "access").sub == user.id
        assert decode(result.refresh, "refresh").sub == user.id

    def test_issues_a_different_refresh_token(self, service, session):
        result = service.refresh(session.refresh_token)

        assert result.refresh != session.refresh_token
        assert decode(result.refresh, "refresh").jti != decode(session.refresh_token, "refresh").jti

    def test_rotated_tokens_stay_in_the_same_family(self, service, session):
        original = decode(session.refresh_token, "refresh")

        result = service.refresh(session.refresh_token)

        assert decode(result.refresh, "refresh").fid == original.fid
        assert decode(result.access, "access").fid == original.fid

    def test_refresh_can_be_chained(self, service, session):
        """Each rotated token must itself be usable for the next refresh."""
        token = session.refresh_token

        for _ in range(3):
            token = service.refresh(token).refresh

        assert decode(token, "refresh").sub == decode(session.refresh_token, "refresh").sub

    def test_rotation_does_not_create_extra_families(self, service, session, refresh_repo):
        service.refresh(session.refresh_token)

        assert len(refresh_repo.families) == 1


class TestRefreshReuseDetection:
    def test_replaying_a_rotated_token_is_rejected(self, service, session):
        service.refresh(session.refresh_token)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

    def test_replay_also_kills_the_legitimate_new_token(self, service, session):
        rotated = service.refresh(session.refresh_token)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)  # attacker replays the stolen token

        with pytest.raises(InvalidSessionError):
            service.refresh(rotated.refresh)  # the family is gone for everyone

    def test_reuse_does_not_affect_other_sessions(self, service, user, session):
        other_device = login(service)

        service.refresh(session.refresh_token)
        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

        assert isinstance(service.refresh(other_device.refresh_token), AuthModel)


class TestRefreshInfrastructureFailures:
    def test_store_outage_is_not_reported_as_an_invalid_session(self, provider, user_repo, user):
        """A 401 would log every user out during an outage; it must surface as an error."""
        healthy = MockRefreshTokenRepository()
        working = AuthService(provider, user_repo, healthy)
        session = login(working)

        broken = AuthService(provider, user_repo, FailingRefreshTokenRepository())

        with pytest.raises(InfrastructureUnavailableError):
            broken.refresh(session.refresh_token)

    def test_user_database_outage(self, provider, user_repo, refresh_repo, user):
        session = login(AuthService(provider, user_repo, refresh_repo))
        broken = AuthService(provider, FailingUserRepository(), refresh_repo)

        with pytest.raises(InfrastructureUnavailableError):
            broken.refresh(session.refresh_token)

        assert refresh_repo.rotate_calls == 0

    def test_unexpected_store_errors_are_not_disguised_as_outages(self, provider, user_repo, user):
        session = login(AuthService(provider, user_repo, MockRefreshTokenRepository()))
        broken = AuthService(provider, user_repo, FailingRefreshTokenRepository(KeyError("bug")))

        with pytest.raises(KeyError):
            broken.refresh(session.refresh_token)


class TestLogout:
    def test_revokes_the_session(self, service, session):
        service.logout(session.refresh_token)

        with pytest.raises(InvalidSessionError):
            service.refresh(session.refresh_token)

    def test_removes_the_family_from_the_store(self, service, session, refresh_repo):
        fid = decode(session.refresh_token, "refresh").fid

        service.logout(session.refresh_token)

        assert fid not in refresh_repo.families

    def test_works_with_a_rotated_refresh_token(self, service, session, refresh_repo):
        """After a refresh, the newest token is the one the browser holds."""
        rotated = service.refresh(session.refresh_token)

        service.logout(rotated.refresh)

        assert refresh_repo.families == {}
        with pytest.raises(InvalidSessionError):
            service.refresh(rotated.refresh)

    def test_only_the_current_session_is_revoked(self, service, user, session):
        other_device = login(service)

        service.logout(session.refresh_token)

        assert isinstance(service.refresh(other_device.refresh_token), AuthModel)

    def test_is_idempotent(self, service, session):
        service.logout(session.refresh_token)
        service.logout(session.refresh_token)  # must not raise

    def test_already_revoked_family_does_not_raise(self, service, session, user, refresh_repo):
        refresh_repo.revoke_family(user.id, decode(session.refresh_token, "refresh").fid)

        service.logout(session.refresh_token)

    def test_unregistered_family_does_not_raise(self, service, user):
        """Validly signed, but the store has never heard of it (e.g. store was wiped)."""
        service.logout(JsonWebToken.refresh(user.id).encode())

    def test_still_revokes_when_the_user_no_longer_exists(
        self, service, session, user, user_repo, refresh_repo
    ):
        """Logout depends only on the token, not on the user record."""
        user_repo.delete(user.id)

        service.logout(session.refresh_token)

        assert refresh_repo.families == {}

    def test_still_revokes_when_the_user_has_lost_access(
        self, service, session, user, user_repo, refresh_repo
    ):
        user_repo.users[user.id] = make_user(access=False, id=user.id)

        service.logout(session.refresh_token)

        assert refresh_repo.families == {}


class TestLogoutBadTokens:
    """A bad token is not an error (the user wants out either way), but it must
    never revoke anything."""

    def test_missing_token(self, service, session, refresh_repo):
        service.logout(None)

        assert len(refresh_repo.families) == 1

    def test_garbage_token(self, service, session, refresh_repo):
        service.logout("not.a.jwt")

        assert len(refresh_repo.families) == 1

    def test_expired_token(self, service, session, user, refresh_repo):
        fid = decode(session.refresh_token, "refresh").fid
        expired = JsonWebToken.create(
            user.id, "refresh", timedelta(minutes=-1), family_id=fid
        ).encode()

        service.logout(expired)

        assert fid in refresh_repo.families

    def test_access_token_does_not_revoke(self, service, session, refresh_repo):
        """Access tokens carry the same fid, but logout only acts on refresh tokens."""
        service.logout(session.access_token)

        assert len(refresh_repo.families) == 1
        assert isinstance(service.refresh(session.refresh_token), AuthModel)

    def test_token_signed_with_another_secret_does_not_revoke(
        self, service, session, user, refresh_repo
    ):
        original = decode(session.refresh_token, "refresh")
        forged = jwt.encode(
            {
                "iss": TEST_ISSUER,
                "sub": str(user.id),
                "aud": TEST_AUDIENCE,
                "iat": int(original.iat),
                "exp": int(original.exp),
                "jti": str(uuid.uuid4()),
                "fid": str(original.fid),
                "token_type": "refresh",
            },
            "another-secret-that-is-also-long-enough-to-avoid-key-length-warnings",
            algorithm=TEST_ALGORITHM,
        )

        service.logout(forged)

        assert original.fid in refresh_repo.families

    def test_logs_never_contain_token_strings(self, service, session, caplog):
        caplog.set_level(logging.DEBUG)

        service.logout("not.a.jwt")
        service.logout(session.refresh_token)

        assert session.refresh_token not in caplog.text
        assert session.access_token not in caplog.text


class TestLogoutInfrastructureFailures:
    def test_store_outage_is_not_swallowed(self, provider, user_repo, user):
        """If the session could not be revoked, the caller must find out: reporting
        success would leave a live session behind a 'logged out' UI."""
        session = login(AuthService(provider, user_repo, MockRefreshTokenRepository()))
        broken = AuthService(provider, user_repo, FailingRefreshTokenRepository())

        with pytest.raises(InfrastructureUnavailableError):
            broken.logout(session.refresh_token)

    def test_bad_token_does_not_touch_the_store(self, provider, user_repo):
        """A broken store must not turn a harmless no-op logout into an error."""
        broken = AuthService(provider, user_repo, FailingRefreshTokenRepository())

        broken.logout(None)
        broken.logout("not.a.jwt")
