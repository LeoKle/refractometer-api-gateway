import logging
import secrets
from collections.abc import Generator
from contextlib import contextmanager

from auth.exceptions import (
    AuthProviderUnavailableError,
    InfrastructureUnavailableError,
    InvalidLoginTransactionError,
    InvalidSessionError,
    LoginRejectedError,
)
from auth.interfaces.auth_service_interface import (
    AuthModel,
    AuthServiceInterface,
    LoginResult,
    LoginStart,
)
from auth.interfaces.oauth_provider_interface import (
    OAuthError,
    OAuthProviderInterface,
    OAuthUnavailableError,
    UserData,
)
from auth.interfaces.refresh_token_repository_interface import (
    RefreshTokenRepositoryInterface,
    RefreshTokenRepositoryUnavailableError,
    RefreshTokenRotationResult,
)
from auth.oauth_transaction import (
    InvalidTransactionError,
    OAuthTransaction,
    create_transaction,
    decode_transaction,
    encode_transaction,
)
from auth.tokens import InvalidTokenError, JsonWebToken
from users.user import User
from users.user_repository_interface import (
    UserAlreadyExistsError,
    UserRepositoryInterface,
    UserRepositoryUnavailableError,
)

logger = logging.getLogger(__name__)


@contextmanager
def _infrastructure(operation: str) -> Generator[None]:
    try:
        yield
    except (UserRepositoryUnavailableError, RefreshTokenRepositoryUnavailableError) as err:
        logger.exception("AuthService: %s failed", operation)
        raise InfrastructureUnavailableError(operation) from err


class AuthService(AuthServiceInterface):
    def __init__(
        self,
        oauth_provider: OAuthProviderInterface,
        user_repo: UserRepositoryInterface,
        refresh_token_repo: RefreshTokenRepositoryInterface,
    ):
        self.oauth_provider = oauth_provider
        self.user_repo = user_repo
        self.refresh_repo = refresh_token_repo

    def start_login(self, redirect_to: str | None) -> LoginStart:
        transaction, code_challenge = create_transaction(redirect_to)

        url = self.oauth_provider.get_redirect_url(transaction.state, code_challenge)

        return LoginStart(url=url, transaction=encode_transaction(transaction))

    def complete_login(self, code: str, state: str | None, transaction: str | None) -> LoginResult:
        oauth_transaction = self._verify_transaction(state, transaction)
        user_data = self._fetch_identity(code, oauth_transaction.code_verifier)
        tokens = self._upsert_user_and_generate_tokens(user_data)

        return LoginResult(
            access_token=tokens.access,
            refresh_token=tokens.refresh,
            redirect_to=oauth_transaction.redirect_to,
        )

    def refresh(self, refresh_token: str | None) -> AuthModel:
        token = self._decode_refresh_token(refresh_token)
        if token is None:
            raise InvalidSessionError

        with _infrastructure("user lookup"):
            user = self.user_repo.get_by_id(token.sub)

        if user is None:
            logger.info("Refresh for unknown user %s", token.sub)
            raise InvalidSessionError

        if not user.access:
            logger.info("Refresh denied, user %s has no access", user.id)
            raise InvalidSessionError

        new_access = JsonWebToken.access(user.id, family_id=token.fid)
        new_refresh = JsonWebToken.refresh(user.id, family_id=token.fid)

        with _infrastructure("refresh token rotation"):
            outcome = self.refresh_repo.rotate(token, new_refresh)

        match outcome:
            case RefreshTokenRotationResult.OK:
                return AuthModel(access=new_access.encode(), refresh=new_refresh.encode())
            case RefreshTokenRotationResult.REUSE:
                logger.warning(
                    "Refresh token reuse detected, family revoked (user=%s, family=%s)",
                    user.id,
                    token.fid,
                )
            case RefreshTokenRotationResult.UNKNOWN:
                logger.info("Refresh with unknown or revoked family %s", token.fid)

        raise InvalidSessionError

    def logout(self, refresh_token: str | None) -> None:
        token = self._decode_refresh_token(refresh_token)
        if token is None:
            return

        with _infrastructure("session revocation"):
            self.refresh_repo.revoke_family(token.sub, token.fid)

    @staticmethod
    def _verify_transaction(state: str | None, transaction: str | None) -> OAuthTransaction:
        if transaction is None:
            logger.info("Login callback without a transaction cookie")
            raise InvalidLoginTransactionError

        try:
            oauth_transaction = decode_transaction(transaction)
        except InvalidTransactionError as err:
            logger.info("Login callback with an invalid transaction: %s", err)
            raise InvalidLoginTransactionError from None

        if not state or not secrets.compare_digest(state, oauth_transaction.state):
            logger.info("State missing or not equal to expected transaction state")
            raise InvalidLoginTransactionError

        return oauth_transaction

    def _fetch_identity(self, code: str, code_verifier: str) -> UserData:
        try:
            auth_data = self.oauth_provider.exchange_code(code, code_verifier)
            return self.oauth_provider.get_user_data(auth_data.access_token)
        except OAuthUnavailableError as err:
            logger.exception("AuthService: OAuth provider unavailable")
            raise AuthProviderUnavailableError from err
        except OAuthError as err:
            logger.warning("AuthService: OAuth provider rejected the login: %s", err)
            raise LoginRejectedError from err

    @staticmethod
    def _decode_refresh_token(refresh_token: str | None) -> JsonWebToken | None:
        """Return the verified refresh token, or None if absent or invalid."""
        if refresh_token is None:
            return None

        try:
            return JsonWebToken.decode(refresh_token, "refresh")
        except InvalidTokenError as err:
            logger.info("Rejected refresh token: %s", err)
            return None

    def _get_or_create_user(self, user_data: UserData) -> User:
        user = self.user_repo.get_by_email(user_data.email)
        if user is not None:
            return user

        try:
            return self.user_repo.create(User(email=user_data.email, name=user_data.name))
        except UserAlreadyExistsError:
            user = self.user_repo.get_by_email(user_data.email)
            if user is None:
                raise
            logger.info("AuthService: user created concurrently, reusing it")
            return user

    def _upsert_user_and_generate_tokens(self, user_data: UserData) -> AuthModel:
        with _infrastructure("user upsert"):
            user = self._get_or_create_user(user_data)

        refresh_token = JsonWebToken.refresh(user_id=user.id)
        access_token = JsonWebToken.access(user.id, family_id=refresh_token.fid)

        with _infrastructure("session start"):
            self.refresh_repo.start(refresh_token)

        return AuthModel(
            access=access_token.encode(),
            refresh=refresh_token.encode(),
        )
