from dependency_injector import containers, providers
from redis import Redis
from refractometer_common.image import ImageClient

from auth.auth_service import AuthService
from auth.providers.github_oauth_provider import GitHubOAuthProvider
from auth.redis_refresh_token_repository import RedisRefreshTokenRepository
from containers.database import Database
from settings import get_settings
from users.user_repository import SQLUserRepository


class DependencyContainer(containers.DeclarativeContainer):
    settings = providers.Singleton(get_settings)
    config = settings.provided

    redis_client = providers.Singleton(Redis.from_url, config.REDIS_URL)

    db = providers.Singleton(Database, db_url=config.DB_URL, db_echo=config.DB_ECHO)

    session_factory = db.provided.session

    # Auth

    refresh_token_repository = providers.Factory(
        RedisRefreshTokenRepository, redis_client=redis_client
    )

    oauth_provider = providers.Factory(GitHubOAuthProvider)

    user_repository = providers.Factory(SQLUserRepository, session_factory=session_factory)

    auth_service = providers.Factory(
        AuthService,
        oauth_provider=oauth_provider,
        user_repo=user_repository,
        refresh_token_repo=refresh_token_repository,
    )

    user_repository = providers.Factory(SQLUserRepository, session_factory=session_factory)

    # image

    image_client = providers.Factory(
        ImageClient,
        base_url=config.IMAGE_CLIENT_URL,
        timeout=config.IMAGE_CLIENT_TIMEOUT,
    )
