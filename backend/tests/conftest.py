import asyncio
import sys

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

# psycopg's async mode cannot run on Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _url_for(dbname: str) -> str:
    assert dbname.endswith("_test"), "refusing to touch a non-test database"
    return make_url(get_settings().database_url).set(database=dbname).render_as_string(
        hide_password=False
    )


def _admin_engine():
    return create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")


def recreate_database(dbname: str) -> str:
    """Drop + create an isolated *_test database; skip the test if Postgres is unreachable."""
    assert dbname.endswith("_test")
    admin = _admin_engine()
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{dbname}"'))
    except Exception as exc:  # pragma: no cover - depends on local infra
        pytest.skip(f"PostgreSQL not available for DB tests: {type(exc).__name__}")
    finally:
        admin.dispose()
    return _url_for(dbname)


def drop_database(dbname: str) -> None:
    assert dbname.endswith("_test")
    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db_url():
    """Isolated database migrated to head using the real Alembic migrations."""
    url = recreate_database("whale_test")
    command.upgrade(alembic_config(url), "head")
    yield url
    drop_database("whale_test")


@pytest.fixture
def db(migrated_db_url):
    """Sync engine on the test DB; tables emptied after each test."""
    engine = create_engine(migrated_db_url)
    yield engine
    with engine.begin() as c:
        c.execute(text("TRUNCATE users, wallets, transactions, sync_checkpoints, transaction_classifications RESTART IDENTITY CASCADE"))
    engine.dispose()
