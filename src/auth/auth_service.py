import logging
import secrets

from auth.interfaces.auth_service_interface import (
    AuthenticationError,
    AuthModel,
    AuthProviderUnavailableError,
    AuthServiceInterface,
    InvalidLoginTransactionError,
    InvalidSessionError,
    LoginResult,
    LoginStart,
)
from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthExchangeError,
    OAuthNetworkError,
    OAuthProviderInterface,
    OAuthUserDataError,
    UserData,
)
from auth.oauth_transaction import create_transaction, decode_transaction, encode_transaction
from auth.tokens import InvalidTokenError, JsonWebToken
from users.user import User
from users.user_repository_interface import UserRepositoryInterface

logger = logging.getLogger(__name__)


class AuthService(AuthServiceInterface):
    def __init__(self, oauth_provider: OAuthProviderInterface, user_repo: UserRepositoryInterface):
        self.oauth_provider = oauth_provider
        self.user_repo = user_repo

    def start_login(self, redirect_to: str | None) -> LoginStart:
        transaction, code_challenge = create_transaction(redirect_to)

        url = self.oauth_provider.get_redirect_url(transaction.state, code_challenge)

        return LoginStart(url=url, transaction=encode_transaction(transaction))

    def complete_login(self, code: str, state: str | None, transaction: str | None) -> LoginResult:
        if transaction is None:
            logger.info("Login callback without a transaction cookie")
            raise InvalidLoginTransactionError

        oauth_transaction = decode_transaction(transaction)

        if oauth_transaction is None:
            logger.info("Login callback with an invalid or expired transaction")
            raise InvalidLoginTransactionError

        if not state or not secrets.compare_digest(state, oauth_transaction.state):
            logger.info("State missing or not equal to expected transaction state")
            raise InvalidLoginTransactionError

        code_verifier = oauth_transaction.code_verifier

        try:
            auth_data: AuthResponseData = self.oauth_provider.exchange_code(code, code_verifier)
        except OAuthNetworkError as err:
            logger.exception("AuthService: provider unreachable during code exchange")
            raise AuthProviderUnavailableError from err
        except OAuthExchangeError as err:
            logger.warning("AuthService: code exchange rejected: %s", err)
            raise AuthenticationError from err

        try:
            user_data: UserData = self.oauth_provider.get_user_data(auth_data.access_token)
        except OAuthNetworkError as err:
            logger.exception("AuthService: provider unreachable during user data fetch")
            raise AuthProviderUnavailableError from err
        except OAuthUserDataError as err:
            logger.warning("AuthService: user data rejected: %s", err)
            raise AuthenticationError from err

        tokens: AuthModel = self._upsert_user_and_generate_tokens(user_data)

        login_result = LoginResult(
            access_token=tokens.access,
            refresh_token=tokens.refresh,
            redirect_to=oauth_transaction.redirect_to,
        )

        return login_result

    def refresh(self, refresh_token: str | None):
        if refresh_token is None:
            raise InvalidSessionError

        try:
            token = JsonWebToken.decode(refresh_token, "refresh")
        except InvalidTokenError:
            logger.info("Invalid refresh token")
            raise InvalidSessionError from None

        user = self.user_repo.get_by_id(token.sub)
        if user is None:
            logger.info("Refresh for unknown user %s", token.sub)
            raise InvalidSessionError

        if not user.access:
            logger.info("Refresh denied, user %s has no access", user.id)
            raise InvalidSessionError

        new_access = JsonWebToken.access(user.id)
        new_refresh = JsonWebToken.refresh(user.id)

        # TODO: token rotation

        return AuthModel(access=new_access.encode(), refresh=new_refresh.encode())

    def _upsert_user_and_generate_tokens(self, user_data: UserData) -> AuthModel:
        user = self.user_repo.get_by_email(user_data.email)

        if not user:
            user = User(email=user_data.email, name=user_data.name)
            user = self.user_repo.create(user)

        refresh_token = JsonWebToken.refresh(user_id=user.id)
        access_token = JsonWebToken.access(user.id, family_id=refresh_token.fid)

        return AuthModel(
            access=access_token.encode(),
            refresh=refresh_token.encode(),
        )
