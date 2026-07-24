import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Connection, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

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
        assert current == "0009_seed_integrity_guard"

        command.downgrade(cfg, "base")
        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT COUNT(*) FROM alembic_version")
            ).scalar_one()
        assert remaining == 0

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            final = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert final == "0009_seed_integrity_guard"
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


_CATALOG_TABLES = (
    "freyja2_underlying_markets",
    "freyja2_product_types",
    "freyja2_assets",
    "freyja2_timeframes",
    "freyja2_instruments",
    "freyja2_instrument_timeframes",
)

_CANONICAL_COUNTS = {
    "freyja2_underlying_markets": 2,
    "freyja2_product_types": 2,
    "freyja2_assets": 7,
    "freyja2_timeframes": 5,
    "freyja2_instruments": 10,
    "freyja2_instrument_timeframes": 50,
}


def test_upgrade_from_empty_to_0009_reaches_expected_head_with_exact_seed(
    temp_database_name: str,
) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0009_seed_integrity_guard"
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _CATALOG_TABLES
            }
        assert counts == _CANONICAL_COUNTS
    finally:
        engine.dispose()


def test_upgrade_from_0008_to_0009_succeeds_with_correct_seed(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0008_catalog_integrity")
        command.upgrade(cfg, "0009_seed_integrity_guard")  # must not raise

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0009_seed_integrity_guard"
    finally:
        engine.dispose()


def test_manual_row_at_0005_blocks_upgrade_to_0006_and_is_preserved(
    temp_database_name: str,
) -> None:
    """POINT1-SEED-001 fail-closed decision: 0006_catalog_display_names adds
    display_name as NOT NULL with no server_default, because it presupposes
    the four catalog tables are still empty (it precedes the official
    seed). PostgreSQL itself enforces that assumption: ADD COLUMN ... NOT
    NULL without a default fails immediately against a non-empty table. A
    manually-inserted row at 0005 therefore blocks the upgrade, is left
    untouched, and Alembic never advances past 0005_catalog — there is no
    backfill and no code-as-display-name fallback."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0005_catalog")

        manual_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO freyja2_underlying_markets (id, code, is_active) "
                    "VALUES (:id, 'MANUAL', true)"
                ),
                {"id": manual_id},
            )

        with pytest.raises(IntegrityError):
            command.upgrade(cfg, "0006_catalog_display_names")

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0005_catalog"

            row = connection.execute(
                text("SELECT code FROM freyja2_underlying_markets WHERE id = :id"),
                {"id": manual_id},
            ).first()
            assert row is not None
            assert row[0] == "MANUAL"
    finally:
        engine.dispose()
