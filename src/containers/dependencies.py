from dependency_injector import containers, providers

from auth.auth_service import AuthService
from auth.providers.github_oauth_provider import GitHubOAuthProvider
from containers.database import Database
from settings import get_settings
from users.user_repository import SQLUserRepository


class DependencyContainer(containers.DeclarativeContainer):
    settings = providers.Singleton(get_settings)
    config = settings.provided

    db = providers.Singleton(Database, db_url=config.DB_URL, db_echo=config.DB_ECHO)

    session_factory = db.provided.session

    # Auth

    oauth_provider = providers.Factory(GitHubOAuthProvider)

    user_repository = providers.Factory(SQLUserRepository, session_factory=session_factory)

    auth_service = providers.Factory(
        AuthService, oauth_provider=oauth_provider, user_repo=user_repository
    )

    user_repository = providers.Factory(SQLUserRepository, session_factory=session_factory)
