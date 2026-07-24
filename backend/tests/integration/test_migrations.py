import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Connection, create_engine, inspect, text

from alembic import command
from freyja_backend.core.database import get_postgres_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEMP_DB_PATTERN = re.compile(r"freyja_test_[0-9a-f]{12}")


def _validate_temp_database_name(name: str) -> str:
    if TEMP_DB_PATTERN.fullmatch(name) is None:
        raise ValueError(f"refusing to operate on unvalidated database name: {name!r}")
    return name


def _alembic_config(database_url: URL) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = database_url
    return cfg


@pytest.fixture
def temp_database_name() -> Iterator[str]:
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    db_name = _validate_temp_database_name(f"freyja_test_{uuid.uuid4().hex[:12]}")

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{db_name}"'))
        yield db_name
    finally:
        try:
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
        finally:
            admin_engine.dispose()


@pytest.mark.parametrize(
    "invalid_name",
    [
        'freyja_test_0123456789ab"',
        "freyja_test_0123456789ab;",
        "freyja_test_012345",
        "freyja_test_0123456789AB",
        "freyja_dev",
        "",
    ],
)
def test_validate_temp_database_name_rejects_invalid(invalid_name: str) -> None:
    with pytest.raises(ValueError):
        _validate_temp_database_name(invalid_name)


def test_validate_temp_database_name_accepts_valid() -> None:
    valid_name = "freyja_test_0123456789ab"
    assert _validate_temp_database_name(valid_name) == valid_name


def test_single_head() -> None:
    cfg = _alembic_config(get_postgres_settings().url)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1


def test_invalid_database_url_override_fails_closed() -> None:
    invalid_override = "not-a-url"
    cfg = _alembic_config(get_postgres_settings().url)
    cfg.attributes["database_url"] = invalid_override

    with pytest.raises((TypeError, RuntimeError)) as excinfo:
        command.upgrade(cfg, "head")

    assert invalid_override not in str(excinfo.value)


def test_upgrade_downgrade_upgrade_cycle(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert current == "0008_catalog_integrity"

        command.downgrade(cfg, "base")
        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT COUNT(*) FROM alembic_version")
            ).scalar_one()
        assert remaining == 0

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            final = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert final == "0008_catalog_integrity"
    finally:
        engine.dispose()


_AUTH_TABLES = (
    "auth_users",
    "auth_sessions",
    "auth_rate_limit_events",
    "auth_password_reset_tokens",
)


def _existing_tables(connection: Connection, names: tuple[str, ...]) -> set[str]:
    inspector = inspect(connection)
    return {name for name in names if inspector.has_table(name)}


def _has_column(connection: Connection, table: str, column: str) -> bool:
    inspector = inspect(connection)
    return any(col["name"] == column for col in inspector.get_columns(table))


def test_auth_tables_created_on_upgrade_and_dropped_on_downgrade(
    temp_database_name: str,
) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert _existing_tables(connection, _AUTH_TABLES) == set(_AUTH_TABLES)
            assert not _has_column(connection, "auth_users", "email_verified_at")
            assert _has_column(connection, "auth_users", "created_via")
            assert not inspect(connection).has_table("auth_email_verification_tokens")

        command.downgrade(cfg, "base")
        with engine.connect() as connection:
            assert _existing_tables(connection, _AUTH_TABLES) == set()
    finally:
        engine.dispose()


def _rate_limit_action_enum_labels(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'auth_rate_limit_action'"
        )
    ).all()
    return {row[0] for row in rows}


def test_migration_0004_removes_email_verification_artifacts(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0003_auth_email_flows")
        with engine.connect() as connection:
            assert inspect(connection).has_table("auth_email_verification_tokens")
            assert _has_column(connection, "auth_users", "email_verified_at")
            assert "RESEND_VERIFICATION" in _rate_limit_action_enum_labels(connection)

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert not inspect(connection).has_table("auth_email_verification_tokens")
            assert not _has_column(connection, "auth_users", "email_verified_at")
            assert "RESEND_VERIFICATION" not in _rate_limit_action_enum_labels(connection)

        command.downgrade(cfg, "0003_auth_email_flows")
        with engine.connect() as connection:
            assert inspect(connection).has_table("auth_email_verification_tokens")
            assert _has_column(connection, "auth_users", "email_verified_at")
            assert "RESEND_VERIFICATION" in _rate_limit_action_enum_labels(connection)
    finally:
        engine.dispose()
