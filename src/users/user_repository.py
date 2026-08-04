import uuid

from containers.database import SessionFactory
from users.user import User as UserDomain
from users.user_model import UserModel as UserSQL
from users.user_repository_interface import UserRepositoryInterface


class SQLUserRepository(UserRepositoryInterface):
    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory

    def get_by_id(self, id: uuid.UUID) -> UserDomain | None:
        with self.session_factory() as session:
            row = session.get(UserSQL, id)
            return self._to_domain(row) if row else None

    def get_by_email(self, email: str) -> UserDomain | None:
        with self.session_factory() as session:
            row = session.query(UserSQL).filter(UserSQL.email == email).first()
            return self._to_domain(row) if row else None

    def create(self, user: UserDomain) -> UserDomain:
        with self.session_factory() as session:
            row = self._to_sql(user)
            session.add(row)
            session.commit()
            return self._to_domain(row)

    def update(self, user: UserDomain) -> UserDomain:
        with self.session_factory() as session:
            row = session.get(UserSQL, user.id)
            if not row:
                msg = f"user {user.id} not found"
                raise ValueError(msg)
            row.admin = user.admin
            row.access = user.access
            session.commit()
            return self._to_domain(row)

    def delete(self, user_id: uuid.UUID) -> None:
        with self.session_factory() as session:
            row = session.get(UserSQL, user_id)
            if row:
                session.delete(row)
                session.commit()

    @staticmethod
    def _to_domain(row: UserDomain) -> UserDomain:
        return UserDomain(
            id=row.id,
            email=row.email,
            name=row.name,
            admin=row.admin,
            access=row.access,
        )

    @staticmethod
    def _to_sql(user: UserDomain) -> UserDomain:
        return UserSQL(
            id=user.id,
            email=user.email,
            name=user.name,
            admin=user.admin,
            access=user.access,
        )
