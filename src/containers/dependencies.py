from dependency_injector import containers, providers

from containers.database import Database
from settings import Settings


class DependencyContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    config.from_pydantic(Settings())

    db = providers.Singleton(Database, db_url=config.db_url, db_echo=config.db_echo)

    session_factory = db.provided.session
