import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from freyja_backend.core import email as email_module
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.core.email import InMemoryEmailSender
from freyja_backend.db import deps as db_deps
from freyja_backend.db.session import create_session_factory
from freyja_backend.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEMP_DB_PATTERN = re.compile(r"freyja_test_[0-9a-f]{12}")

_AUTH_TABLES = (
    "auth_sessions",
    "auth_rate_limit_events",
    "auth_password_reset_tokens",
    "auth_users",
)


def _validate_temp_database_name(name: str) -> str:
    if TEMP_DB_PATTERN.fullmatch(name) is None:
        raise ValueError(f"refusing to operate on unvalidated database name: {name!r}")
    return name


def _assert_api_uses_isolated_database(test_engine: Engine) -> None:
    """The API layer must resolve to the throwaway test database — never the
    database configured for development or production. Resolved through the
    same `get_db()` dependency every route uses, so it holds for any app
    instance created by `create_app()`."""
    generator = db_deps.get_db()
    session = next(generator)
    try:
        database_name = session.execute(text("SELECT current_database()")).scalar_one()
    finally:
        next(generator, None)  # runs get_db()'s own commit/close
    _validate_temp_database_name(database_name)
    assert database_name == test_engine.url.database


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def pytest_configure(config: pytest.Config) -> None:
    # Runs before test collection and before any Settings() instantiation:
    # the whole suite always runs as "test", regardless of whatever
    # FREYJA_ENVIRONMENT a developer's local .env happens to carry.
    del config
    os.environ["FREYJA_ENVIRONMENT"] = "test"


@pytest.fixture
def client(auth_test_engine: Engine) -> Iterator[TestClient]:
    _assert_api_uses_isolated_database(auth_test_engine)
    app = create_app()
    # base_url="http://localhost": TestClient defaults to Host "testserver",
    # which TrustedHostMiddleware (allowed_hosts defaults to
    # "localhost,127.0.0.1") would otherwise reject with 400 on every request.
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client


@pytest.fixture
def second_client(auth_test_engine: Engine) -> Iterator[TestClient]:
    """A second, independent browser: same isolated test database as
    `client`, but its own application instance and cookie jar, so the two
    never share a session."""
    _assert_api_uses_isolated_database(auth_test_engine)
    app = create_app()
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client


@contextmanager
def _migrated_temp_database() -> Iterator[Engine]:
    """A throwaway PostgreSQL database migrated to head, dropped on exit."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    db_name = _validate_temp_database_name(f"freyja_test_{uuid.uuid4().hex[:12]}")

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    temp_url = settings.url.set(database=db_name)
    cfg = _alembic_config()
    cfg.attributes["database_url"] = temp_url
    command.upgrade(cfg, "head")

    engine = create_engine(temp_url)
    try:
        yield engine
    finally:
        engine.dispose()
        validated = _validate_temp_database_name(db_name)
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": validated},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{validated}"'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def auth_test_engine() -> Iterator[Engine]:
    """Session-scoped throwaway PostgreSQL database, migrated to head, used by
    every test that exercises the auth API/service layer against real
    PostgreSQL (never SQLite, never mocks)."""
    with _migrated_temp_database() as engine:
        db_deps.set_engine_override(engine)
        try:
            yield engine
        finally:
            db_deps.set_engine_override(None)


@pytest.fixture(scope="module")
def market_data_engine() -> Iterator[Engine]:
    """A module-scoped database of its own, migrated to head. Market-data tests
    read the catalog and the BINANCE source seeded by the real migrations, and
    must not depend on what other suites do to the shared `auth_test_engine`
    database (some of them TRUNCATE the catalog and provider tables there)."""
    with _migrated_temp_database() as engine:
        yield engine


@pytest.fixture
def clean_market_data(market_data_engine: Engine) -> None:
    """Start the test with no candles and no sync state (the catalog and the
    BINANCE source seeded by the migrations stay)."""
    with market_data_engine.connect() as connection:
        connection.execute(text("TRUNCATE freyja2_candles, freyja2_market_data_sync_state"))
        connection.commit()


@pytest.fixture
def market_data_session(market_data_engine: Engine, clean_market_data: None) -> Iterator[Session]:
    del clean_market_data
    session = create_session_factory(market_data_engine)()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _truncate_auth_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(_AUTH_TABLES)} RESTART IDENTITY CASCADE"))
        connection.commit()


@pytest.fixture(autouse=True)
def email_sender() -> Iterator[InMemoryEmailSender]:
    sender = InMemoryEmailSender()
    email_module.set_email_sender_override(sender)
    try:
        yield sender
    finally:
        email_module.set_email_sender_override(None)


@pytest.fixture
def db_session(auth_test_engine: Engine) -> Iterator[Session]:
    session_factory = create_session_factory(auth_test_engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
