from auth.interfaces.auth_service_interface import AuthModel, AuthServiceInterface
from auth.interfaces.oauth_provider_interface import (
    AuthResponseData,
    OAuthProviderInterface,
    UserData,
)
from auth.jwt import JsonWebToken
from auth.oauth_transaction import OAuthTransaction, create_transaction
from users.user import User
from users.user_repository_interface import UserRepositoryInterface


class AuthService(AuthServiceInterface):
    def __init__(self, oauth_provider: OAuthProviderInterface, user_repo: UserRepositoryInterface):
        self.oauth_provider = oauth_provider
        self.user_repo = user_repo

    def start_login(self, redirect_to: str | None) -> tuple[str, OAuthTransaction]:
        transaction, code_challenge = create_transaction(redirect_to)

        url = self.oauth_provider.get_redirect_url(transaction.state, code_challenge)

        return url, transaction

    def authenticate(self, code: str, code_verifier: str) -> AuthModel:
        auth_data: AuthResponseData = self.oauth_provider.exchange_code(code, code_verifier)
        user_data: UserData = self.oauth_provider.get_user_data(auth_data.access_token)

        return self._upsert_user_and_generate_tokens(user_data)

    def _upsert_user_and_generate_tokens(self, user_data: UserData) -> AuthModel:
        user = self.user_repo.get_by_email(user_data.email)

        if not user:
            user = User(email=user_data.email, name=user_data.name)
            user = self.user_repo.create(user)

        return AuthModel(
            access=JsonWebToken.access(user_id=str(user.id)).encode(),
            refresh=JsonWebToken.refresh(user_id=str(user.id)).encode(),
        )
