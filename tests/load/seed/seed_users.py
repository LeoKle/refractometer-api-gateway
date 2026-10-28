from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from settings import get_settings
from users.user_model import UserModel

fake = Faker()


engine = create_engine(get_settings().DB_URL)
SessionLocal = sessionmaker(bind=engine)


def seed_users(count: int = 100_000):
    with SessionLocal() as session:
        batch_size = 1_000

        for start in range(0, count, batch_size):
            batch = [
                UserModel(
                    id=fake.uuid4(),
                    email=f"loadtest_{start + i}@example.com",
                    name=f"loadtest_{start + i}",
                    access=True,
                )
                for i in range(min(batch_size, count - start))
            ]

            session.add_all(batch)
            session.commit()

        print(f"Seeded {count} users.")


if __name__ == "__main__":
    seed_users()
