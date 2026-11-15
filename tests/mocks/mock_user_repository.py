import uuid

from users.user import User
from users.user_repository_interface import UserRepositoryInterface


class MockUserRepository(UserRepositoryInterface):
    def __init__(self):
        self.users: dict[uuid.UUID, User] = {}

    def get_by_id(self, id: uuid.UUID) -> User | None:
        return self.users.get(id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    def create(self, user: User) -> User:
        self.users[user.id] = user
        return user

    def update(self, user: User) -> User:
        self.users[user.id] = user
        return user

    def delete(self, user_id: uuid.UUID) -> None:
        self.users.pop(user_id, None)
