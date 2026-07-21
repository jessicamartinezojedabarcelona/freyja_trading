import os
import re
import uuid
from collections.abc import Iterator
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
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_test_engine() -> Iterator[Engine]:
    """Session-scoped throwaway PostgreSQL database, migrated to head, used by
    every test that exercises the auth API/service layer against real
    PostgreSQL (never SQLite, never mocks)."""
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
    db_deps.set_engine_override(engine)
    try:
        yield engine
    finally:
        db_deps.set_engine_override(None)
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
