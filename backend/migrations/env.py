"""Alembic environment.

Uses a synchronous psycopg connection (same DATABASE_URL as the app) because migrations
are a short-lived CLI process; the application itself stays fully async.
The URL can be overridden with `config.set_main_option("sqlalchemy.url", ...)`, which the
test-suite uses to migrate an isolated database.
"""
from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
