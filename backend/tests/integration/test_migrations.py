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
        assert current == "0012_remove_regulatory_engine"

        command.downgrade(cfg, "base")
        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT COUNT(*) FROM alembic_version")
            ).scalar_one()
        assert remaining == 0

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            final = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert final == "0012_remove_regulatory_engine"
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


def test_upgrade_from_empty_to_head_reaches_expected_head_with_exact_seed(
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
            assert current == "0012_remove_regulatory_engine"
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


_PROVIDER_TABLES = (
    "freyja2_venues",
    "freyja2_data_sources",
    "freyja2_venue_instruments",
    "freyja2_data_source_instruments",
)


def test_upgrade_from_0009_to_0010_succeeds(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0009_seed_integrity_guard")
        command.upgrade(cfg, "0010_provider_mappings")  # must not raise

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0010_provider_mappings"
            assert _existing_tables(connection, _PROVIDER_TABLES) == set(_PROVIDER_TABLES)
    finally:
        engine.dispose()


def test_0010_downgrade_upgrade_is_reversible(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            assert _existing_tables(connection, _PROVIDER_TABLES) == set(_PROVIDER_TABLES)

        command.downgrade(cfg, "0009_seed_integrity_guard")
        with engine.connect() as connection:
            assert _existing_tables(connection, _PROVIDER_TABLES) == set()
            # Downgrading 0010 must not touch the catalog seed at all.
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _CATALOG_TABLES
            }
            assert counts == _CANONICAL_COUNTS

        command.upgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            assert _existing_tables(connection, _PROVIDER_TABLES) == set(_PROVIDER_TABLES)
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0010_provider_mappings"
    finally:
        engine.dispose()


_CAPABILITY_TABLES = (
    "freyja2_technical_capabilities",
    "freyja2_execution_contexts",
    "freyja2_regulatory_rules",
    "freyja2_execution_context_regulatory_rules",
)


def test_upgrade_from_0010_to_0011_succeeds(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0010_provider_mappings")
        command.upgrade(cfg, "0011_capability_context")  # must not raise

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0011_capability_context"
            assert _existing_tables(connection, _CAPABILITY_TABLES) == set(_CAPABILITY_TABLES)
    finally:
        engine.dispose()


def test_0011_downgrade_upgrade_is_reversible(temp_database_name: str) -> None:
    """Tests 0011's OWN downgrade/upgrade reversibility in isolation, pinned
    to the 0011_capability_context revision explicitly (not "head", which has
    since moved to 0012_remove_regulatory_engine — that revision's own
    reversibility is covered separately below)."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            assert _existing_tables(connection, _CAPABILITY_TABLES) == set(_CAPABILITY_TABLES)

        command.downgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            assert _existing_tables(connection, _CAPABILITY_TABLES) == set()
            # Downgrading 0011 must not touch the catalog seed or provider
            # mappings at all.
            assert _existing_tables(connection, _PROVIDER_TABLES) == set(_PROVIDER_TABLES)
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _CATALOG_TABLES
            }
            assert counts == _CANONICAL_COUNTS

        command.upgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            assert _existing_tables(connection, _CAPABILITY_TABLES) == set(_CAPABILITY_TABLES)
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0011_capability_context"
    finally:
        engine.dispose()


def test_sequential_walk_upgrades_and_downgrades_one_revision_at_a_time(
    temp_database_name: str,
) -> None:
    """POINT1-TEST-001: every Freyja 2.0 migration must apply cleanly one
    step at a time in both directions, not merely as part of a single
    upgrade(head)/downgrade(base) jump — a broken intermediate revision
    could otherwise hide behind Alembic's own step-chaining."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        script = ScriptDirectory.from_config(cfg)
        revisions = list(script.walk_revisions(base="base", head="head"))
        ordered = [r.revision for r in reversed(revisions)]
        assert len(ordered) >= 12

        for revision in ordered:
            command.upgrade(cfg, revision)
            with engine.connect() as connection:
                current = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                assert current == revision

        for revision in reversed(ordered[:-1]):
            command.downgrade(cfg, revision)
            with engine.connect() as connection:
                current = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                assert current == revision

        command.downgrade(cfg, "base")
        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT COUNT(*) FROM alembic_version")
            ).scalar_one()
            assert remaining == 0
    finally:
        engine.dispose()


def test_catalog_provider_capability_migrations_never_alter_unrelated_auth_data(
    temp_database_name: str,
) -> None:
    """A manually-created auth user, present before any catalog table
    exists (0004), must survive byte-for-byte through the entire
    catalog/seed/provider/capability build-out (0005-0012) and back down
    again — proving those migrations only ever add their own tables and
    never touch auth_users via an incidental ALTER, CASCADE, or trigger."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0004_remove_email_verification")

        user_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO auth_users (id, identifier, password_hash, created_via) "
                    "VALUES (:id, 'legacy@example.test', 'not-a-real-hash', 'SELF_REGISTRATION')"
                ),
                {"id": user_id},
            )

        def _snapshot_user(connection: Connection) -> tuple[object, ...]:
            row = connection.execute(
                text(
                    "SELECT identifier, password_hash, is_active, created_via "
                    "FROM auth_users WHERE id = :id"
                ),
                {"id": user_id},
            ).one()
            return tuple(row)

        with engine.connect() as connection:
            before = _snapshot_user(connection)

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert _snapshot_user(connection) == before

        command.downgrade(cfg, "0004_remove_email_verification")
        with engine.connect() as connection:
            assert _snapshot_user(connection) == before
    finally:
        engine.dispose()


_REMOVED_REGULATORY_TABLES = (
    "freyja2_regulatory_rules",
    "freyja2_execution_context_regulatory_rules",
)
_EXECUTION_CONTEXT_REGULATORY_COLUMNS = (
    "jurisdiction",
    "client_classification",
    "regulatory_eligibility_status",
)


def test_upgrade_from_0011_to_0012_removes_regulatory_engine(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")
        command.upgrade(cfg, "0012_remove_regulatory_engine")  # must not raise

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0012_remove_regulatory_engine"
            assert _existing_tables(connection, _REMOVED_REGULATORY_TABLES) == set()
            for column in _EXECUTION_CONTEXT_REGULATORY_COLUMNS:
                assert not _has_column(connection, "freyja2_execution_contexts", column)
            # Never touches catalog/seed, provider mappings, or
            # freyja2_technical_capabilities.
            assert _existing_tables(connection, _PROVIDER_TABLES) == set(_PROVIDER_TABLES)
            assert inspect(connection).has_table("freyja2_technical_capabilities")
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _CATALOG_TABLES
            }
            assert counts == _CANONICAL_COUNTS
    finally:
        engine.dispose()


def test_0012_downgrade_upgrade_is_reversible(temp_database_name: str) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert _existing_tables(connection, _REMOVED_REGULATORY_TABLES) == set()
            for column in _EXECUTION_CONTEXT_REGULATORY_COLUMNS:
                assert not _has_column(connection, "freyja2_execution_contexts", column)

        command.downgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            assert _existing_tables(connection, _REMOVED_REGULATORY_TABLES) == set(
                _REMOVED_REGULATORY_TABLES
            )
            for column in _EXECUTION_CONTEXT_REGULATORY_COLUMNS:
                assert _has_column(connection, "freyja2_execution_contexts", column)
            # Existing ExecutionContext rows (none here, but the seed/
            # catalog/provider data) remain untouched by the round trip.
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in _CATALOG_TABLES
            }
            assert counts == _CANONICAL_COUNTS

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert _existing_tables(connection, _REMOVED_REGULATORY_TABLES) == set()
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0012_remove_regulatory_engine"
    finally:
        engine.dispose()


def test_0012_upgrade_aborts_and_preserves_everything_when_regulatory_data_present(
    temp_database_name: str,
) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")

        rule_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO freyja2_regulatory_rules "
                    "(id, jurisdiction, effect, source_citation, verified_at) "
                    "VALUES (:id, 'TEST_XX', 'NOT_ELIGIBLE', 'TEST fixture citation', now())"
                ),
                {"id": rule_id},
            )

        with pytest.raises(RuntimeError) as excinfo:
            command.upgrade(cfg, "0012_remove_regulatory_engine")
        # Row content (jurisdiction/citation values) must never leak into the
        # abort message — only counts are reported.
        assert "TEST_XX" not in str(excinfo.value)
        assert "TEST fixture citation" not in str(excinfo.value)

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0011_capability_context", "no partial upgrade may have occurred"
            count = connection.execute(
                text("SELECT COUNT(*) FROM freyja2_regulatory_rules")
            ).scalar_one()
            assert count == 1, "the regulatory row must survive the aborted upgrade untouched"
            assert inspect(connection).has_table("freyja2_execution_context_regulatory_rules")
    finally:
        engine.dispose()


def test_0012_upgrade_aborts_when_execution_context_exists_with_no_regulatory_rows(
    temp_database_name: str,
) -> None:
    """Independent-audit regression: an ExecutionContext row with NO
    RegulatoryRule/association attached used to sail past the old guard
    (which only checked the two regulatory tables) and then silently lose
    jurisdiction/client_classification/regulatory_eligibility_status when
    the columns were dropped underneath it. upgrade() must now refuse to run
    at all while freyja2_execution_contexts has any row, regardless of
    whether any regulatory table has data."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")

        owner_id = uuid.uuid4()
        venue_id = uuid.uuid4()
        context_id = uuid.uuid4()
        with engine.begin() as connection:
            product_type_id = connection.execute(
                text("SELECT id FROM freyja2_product_types WHERE code = 'SPOT'")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO auth_users (id, identifier, password_hash, created_via) "
                    "VALUES (:id, 'test-ec-guard-owner@example.test', 'not-a-real-hash', "
                    "'SELF_REGISTRATION')"
                ),
                {"id": owner_id},
            )
            connection.execute(
                text(
                    "INSERT INTO freyja2_venues (id, code, display_name, venue_type, is_active) "
                    "VALUES (:id, 'TEST_MIG_EC_GUARD_VENUE', 'Test Venue', 'EXCHANGE', true)"
                ),
                {"id": venue_id},
            )
            connection.execute(
                text(
                    "INSERT INTO freyja2_execution_contexts "
                    "(id, owner_id, venue_id, account_key, execution_environment, "
                    "product_type_id, jurisdiction, client_classification) "
                    "VALUES (:id, :owner_id, :venue_id, 'TEST_ACC', 'DEMO', :product_type_id, "
                    "'TEST_XX', 'TEST_RETAIL')"
                ),
                {
                    "id": context_id,
                    "owner_id": owner_id,
                    "venue_id": venue_id,
                    "product_type_id": product_type_id,
                },
            )

        with pytest.raises(RuntimeError) as excinfo:
            command.upgrade(cfg, "0012_remove_regulatory_engine")
        assert "TEST_XX" not in str(excinfo.value)
        assert "TEST_RETAIL" not in str(excinfo.value)

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0011_capability_context", "no partial upgrade may have occurred"

            row = connection.execute(
                text(
                    "SELECT jurisdiction, client_classification, account_key "
                    "FROM freyja2_execution_contexts WHERE id = :id"
                ),
                {"id": context_id},
            ).one()
            assert row[0] == "TEST_XX"
            assert row[1] == "TEST_RETAIL"
            assert row[2] == "TEST_ACC"

            for column in _EXECUTION_CONTEXT_REGULATORY_COLUMNS:
                assert _has_column(connection, "freyja2_execution_contexts", column)
            assert _existing_tables(connection, _REMOVED_REGULATORY_TABLES) == set(
                _REMOVED_REGULATORY_TABLES
            )
    finally:
        engine.dispose()


def test_0012_upgrade_succeeds_when_execution_contexts_and_regulatory_tables_are_all_empty(
    temp_database_name: str,
) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM freyja2_execution_contexts")
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM freyja2_regulatory_rules")
                ).scalar_one()
                == 0
            )

        command.upgrade(cfg, "0012_remove_regulatory_engine")  # must not raise

        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == "0012_remove_regulatory_engine"
    finally:
        engine.dispose()


def _enum_labels(connection: Connection, enum_name: str) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :enum_name"
        ),
        {"enum_name": enum_name},
    ).all()
    return {row[0] for row in rows}


def _schema_fingerprint(connection: Connection, tables: tuple[str, ...]) -> dict[str, object]:
    inspector = inspect(connection)
    fingerprint: dict[str, object] = {}
    for table in tables:
        fingerprint[table] = {
            "columns": sorted((c["name"], str(c["type"])) for c in inspector.get_columns(table)),
            "indexes": sorted(
                (ix["name"], tuple(ix["column_names"]), ix.get("unique", False))
                for ix in inspector.get_indexes(table)
            ),
            "check_constraints": sorted(
                str(cc["name"]) for cc in inspector.get_check_constraints(table)
            ),
            "foreign_keys": sorted(
                (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"])
                for fk in inspector.get_foreign_keys(table)
            ),
            "unique_constraints": sorted(
                (uc["name"], tuple(uc["column_names"]))
                for uc in inspector.get_unique_constraints(table)
            ),
        }
    return fingerprint


_PROVIDER_ENUMS = (
    "freyja2_venue_type",
    "freyja2_data_source_type",
    "freyja2_data_source_instrument_purpose",
)

_CAPABILITY_ENUMS = (
    "freyja2_capability_status",
    "freyja2_execution_environment",
    "freyja2_credentials_status",
    "freyja2_venue_permission_status",
    "freyja2_regulatory_eligibility_status",
    "freyja2_owner_authorization_status",
    "freyja2_activation_status",
    "freyja2_regulatory_rule_effect",
)


def test_provider_schema_enums_indexes_checks_fks_survive_downgrade_upgrade_roundtrip(
    temp_database_name: str,
) -> None:
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            before_schema = _schema_fingerprint(connection, _PROVIDER_TABLES)
            before_enums = {name: _enum_labels(connection, name) for name in _PROVIDER_ENUMS}
        assert all(before_enums.values()), "expected non-empty enum labels before round trip"

        command.downgrade(cfg, "0009_seed_integrity_guard")
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert not any(inspector.has_table(t) for t in _PROVIDER_TABLES)
            for name in _PROVIDER_ENUMS:
                assert _enum_labels(connection, name) == set()

        command.upgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            after_schema = _schema_fingerprint(connection, _PROVIDER_TABLES)
            after_enums = {name: _enum_labels(connection, name) for name in _PROVIDER_ENUMS}

        assert after_schema == before_schema
        assert after_enums == before_enums
    finally:
        engine.dispose()


def test_capability_schema_enums_indexes_checks_fks_survive_downgrade_upgrade_roundtrip(
    temp_database_name: str,
) -> None:
    """Pinned to the 0011_capability_context revision explicitly (not
    "head", which has since moved to 0012_remove_regulatory_engine and
    removed two of these tables/enums) — this tests 0011's own schema
    round-trip in isolation, same reasoning as
    test_0011_downgrade_upgrade_is_reversible above."""
    temp_url = get_postgres_settings().url.set(database=temp_database_name)
    cfg = _alembic_config(temp_url)
    engine = create_engine(temp_url)
    try:
        command.upgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            before_schema = _schema_fingerprint(connection, _CAPABILITY_TABLES)
            before_enums = {name: _enum_labels(connection, name) for name in _CAPABILITY_ENUMS}
        assert all(before_enums.values()), "expected non-empty enum labels before round trip"

        command.downgrade(cfg, "0010_provider_mappings")
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert not any(inspector.has_table(t) for t in _CAPABILITY_TABLES)
            for name in _CAPABILITY_ENUMS:
                assert _enum_labels(connection, name) == set()

        command.upgrade(cfg, "0011_capability_context")
        with engine.connect() as connection:
            after_schema = _schema_fingerprint(connection, _CAPABILITY_TABLES)
            after_enums = {name: _enum_labels(connection, name) for name in _CAPABILITY_ENUMS}

        assert after_schema == before_schema
        assert after_enums == before_enums
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
