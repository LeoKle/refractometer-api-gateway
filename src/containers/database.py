import logging
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy import create_engine, orm
from sqlalchemy.orm import Session, declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()

SessionFactory = Callable[[], AbstractContextManager[Session]]


class Database:
    """based on: https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html"""

    def __init__(self, db_url: str, db_echo: bool = False) -> None:
        self._engine = create_engine(db_url, echo=db_echo)
        self._session_factory = orm.scoped_session(
            orm.sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine,
            ),
        )

    def create_database(self) -> None:
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session]:
        session: Session = self._session_factory()
        try:
            yield session
        except Exception:
            logger.exception("Session rollback because of exception")
            session.rollback()
            raise
        finally:
            session.close()
