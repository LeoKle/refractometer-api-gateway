import logging

from auth.interfaces.auth_service_interface import (
    AuthenticationError,
    AuthModel,
    AuthProviderUnavailableError,
    AuthServiceInterface,
)
from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthExchangeError,
    OAuthNetworkError,
    OAuthProviderInterface,
    OAuthUserDataError,
    UserData,
)
from auth.oauth_transaction import OAuthTransaction, create_transaction
from auth.tokens import JsonWebToken
from users.user import User
from users.user_repository_interface import UserRepositoryInterface

logger = logging.getLogger(__name__)


class AuthService(AuthServiceInterface):
    def __init__(self, oauth_provider: OAuthProviderInterface, user_repo: UserRepositoryInterface):
        self.oauth_provider = oauth_provider
        self.user_repo = user_repo

    def start_login(self, redirect_to: str | None) -> tuple[str, OAuthTransaction]:
        transaction, code_challenge = create_transaction(redirect_to)

        url = self.oauth_provider.get_redirect_url(transaction.state, code_challenge)

        return url, transaction

    def authenticate(self, code: str, code_verifier: str) -> AuthModel:
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

        return self._upsert_user_and_generate_tokens(user_data)

    def _upsert_user_and_generate_tokens(self, user_data: UserData) -> AuthModel:
        user = self.user_repo.get_by_email(user_data.email)

        if not user:
            user = User(email=user_data.email, name=user_data.name)
            user = self.user_repo.create(user)

        return AuthModel(
            access=JsonWebToken.access(user_id=user.id).encode(),
            refresh=JsonWebToken.refresh(user_id=user.id).encode(),
        )
