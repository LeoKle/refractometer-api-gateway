import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # ruff: ignore[os-path-abspath, os-path-join, os-path-dirname]
SRC_DIR = os.path.join(BASE_DIR, "src")  # ruff: ignore[os-path-join]

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

from users.user_model import UserModel
from settings import get_settings  # ruff: ignore[module-import-not-at-top-of-file]

settings = get_settings()
print(settings.DB_URL)

config = context.config
config.set_main_option("sqlalchemy.url", settings.DB_URL)

fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline():
    url = settings.DB_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # to allow SQLite
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # to allow SQLite
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
