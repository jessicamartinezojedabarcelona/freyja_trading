import importlib.util
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Row, create_engine, text
from sqlalchemy.engine import Connection, Engine

from alembic import command
from freyja_backend.core.database import get_postgres_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SEED_MODULE_PATH = BACKEND_DIR / "alembic" / "versions" / "0007_seed_catalog_v1.py"

_CATALOG_TABLES = (
    "freyja2_underlying_markets",
    "freyja2_product_types",
    "freyja2_assets",
    "freyja2_timeframes",
    "freyja2_instruments",
    "freyja2_instrument_timeframes",
)


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _load_seed_module() -> ModuleType:
    """Loads the seed migration as a plain module so its pure helper
    functions (_seed_rows, _market_id, etc.) can be called directly against
    a real connection — the same functions upgrade()/downgrade() call, just
    invoked without going through Alembic's own revision tracking (which
    would no-op a second "upgrade head" instead of actually re-running the
    seed block)."""
    spec = importlib.util.spec_from_file_location("seed_catalog_v1", _SEED_MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seeded_engine() -> Iterator[Engine]:
    """One isolated temp database, migrated to head (schema + seed), shared
    read-only across the tests in this module."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


@pytest.fixture
def isolated_seeded_connection() -> Iterator[Connection]:
    """A fresh isolated temp database per test, for tests that mutate seed
    state (idempotency re-application, divergence detection) — never shared
    with other tests."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        try:
            with engine.connect() as connection:
                yield connection
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def _count(connection: Connection, table: str) -> int:
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def test_seed_produces_exact_row_counts(seeded_engine: Engine) -> None:
    with seeded_engine.connect() as connection:
        assert _count(connection, "freyja2_underlying_markets") == 2
        assert _count(connection, "freyja2_product_types") == 2
        assert _count(connection, "freyja2_assets") == 7
        assert _count(connection, "freyja2_instruments") == 10
        assert _count(connection, "freyja2_timeframes") == 5
        assert _count(connection, "freyja2_instrument_timeframes") == 50


def test_instrument_shape_distribution_is_5_pair_4_asset_1_instrument(
    seeded_engine: Engine,
) -> None:
    with seeded_engine.connect() as connection:
        pair_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM freyja2_instruments "
                "WHERE base_asset_id IS NOT NULL AND quote_asset_id IS NOT NULL "
                "AND underlying_asset_id IS NULL AND underlying_instrument_id IS NULL"
            )
        ).scalar_one()
        asset_underlying_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM freyja2_instruments "
                "WHERE underlying_asset_id IS NOT NULL "
                "AND base_asset_id IS NULL AND quote_asset_id IS NULL "
                "AND underlying_instrument_id IS NULL"
            )
        ).scalar_one()
        instrument_underlying_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM freyja2_instruments "
                "WHERE underlying_instrument_id IS NOT NULL "
                "AND base_asset_id IS NULL AND quote_asset_id IS NULL "
                "AND underlying_asset_id IS NULL"
            )
        ).scalar_one()
        assert pair_count == 5
        assert asset_underlying_count == 4
        assert instrument_underlying_count == 1


def test_forex_binary_references_forex_spot_instrument(seeded_engine: Engine) -> None:
    seed = _load_seed_module()
    spot_id = seed._instrument_id("FOREX", "SPOT", "EUR/USD")
    binary_id = seed._instrument_id("FOREX", "BINARY_OPTION", "EUR/USD")

    with seeded_engine.connect() as connection:
        underlying_instrument_id = connection.execute(
            text(
                "SELECT underlying_instrument_id FROM freyja2_instruments "
                "WHERE instrument_id = :binary_id"
            ),
            {"binary_id": binary_id},
        ).scalar_one()
        assert underlying_instrument_id == spot_id


def test_timeframe_durations_are_exact(seeded_engine: Engine) -> None:
    expected = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
    with seeded_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT code, duration_seconds FROM freyja2_timeframes")
        ).all()
        actual = {str(code): int(duration) for code, duration in rows}
        assert actual == expected


def test_50_instrument_timeframe_associations_have_no_duplicates(
    seeded_engine: Engine,
) -> None:
    with seeded_engine.connect() as connection:
        total = _count(connection, "freyja2_instrument_timeframes")
        distinct = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT DISTINCT instrument_id, timeframe_id "
                "FROM freyja2_instrument_timeframes"
                ") AS distinct_pairs"
            )
        ).scalar_one()
        assert total == 50
        assert distinct == 50


def test_identity_is_deterministic_across_independent_recomputation(
    seeded_engine: Engine,
) -> None:
    """The same seed recomputed independently (a second, fresh import of the
    migration module) must produce byte-identical UUIDs to what's actually
    stored — proving the identity scheme is a pure function of the canonical
    strings, not an accident of a single run."""
    seed_a = _load_seed_module()
    seed_b = _load_seed_module()

    assert seed_a._market_id("CRYPTO") == seed_b._market_id("CRYPTO")
    assert seed_a._instrument_id("FOREX", "SPOT", "EUR/USD") == seed_b._instrument_id(
        "FOREX", "SPOT", "EUR/USD"
    )

    with seeded_engine.connect() as connection:
        stored_id = connection.execute(
            text("SELECT id FROM freyja2_underlying_markets WHERE code = 'CRYPTO'")
        ).scalar_one()
        assert stored_id == seed_a._market_id("CRYPTO")


def test_reapplying_the_seed_block_is_idempotent(
    isolated_seeded_connection: Connection,
) -> None:
    seed = _load_seed_module()
    connection = isolated_seeded_connection

    before = connection.execute(
        text(
            "SELECT id, code, display_name, created_at "
            "FROM freyja2_underlying_markets ORDER BY code"
        )
    ).all()

    market_rows = [
        {"id": seed._market_id(code), "code": code, "display_name": name}
        for code, name in seed._MARKETS
    ]
    seed._seed_rows(connection, seed._markets_t, "id", ("code",), market_rows, ("display_name",))
    connection.commit()

    after = connection.execute(
        text(
            "SELECT id, code, display_name, created_at "
            "FROM freyja2_underlying_markets ORDER BY code"
        )
    ).all()

    assert before == after


def test_reapplying_the_seed_block_detects_divergence_and_aborts(
    isolated_seeded_connection: Connection,
) -> None:
    seed = _load_seed_module()
    connection = isolated_seeded_connection

    crypto_id = seed._market_id("CRYPTO")
    connection.execute(
        text("UPDATE freyja2_underlying_markets SET display_name = 'Corrupted' WHERE id = :id"),
        {"id": crypto_id},
    )
    connection.commit()

    market_rows = [
        {"id": seed._market_id(code), "code": code, "display_name": name}
        for code, name in seed._MARKETS
    ]
    with pytest.raises(RuntimeError, match="divergencia"):
        seed._seed_rows(
            connection, seed._markets_t, "id", ("code",), market_rows, ("display_name",)
        )

    connection.rollback()

    # The failed attempt must not have partially written anything else: only
    # the deliberately-corrupted row differs from the canonical seed.
    display_name = connection.execute(
        text("SELECT display_name FROM freyja2_underlying_markets WHERE id = :id"),
        {"id": crypto_id},
    ).scalar_one()
    assert display_name == "Corrupted"


def test_seed_detects_divergence_by_natural_key_not_only_by_id() -> None:
    """A row already present under the seed's natural key (code) but a
    DIFFERENT id must be caught as a divergence, not silently missed by an
    id-only lookup (which would instead hit the table's own UNIQUE(code)
    constraint and raise a raw IntegrityError with a far worse message)."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        # Migrate only up to the schema (display_name added, no seed yet).
        command.upgrade(cfg, "0006_catalog_display_names")

        engine = create_engine(temp_url)
        try:
            seed = _load_seed_module()
            with engine.connect() as connection:
                # A pre-existing row under the same natural key ("CRYPTO")
                # but a random, non-deterministic id — never produced by the
                # seed itself.
                connection.execute(
                    text(
                        "INSERT INTO freyja2_underlying_markets (id, code, display_name) "
                        "VALUES (:id, 'CRYPTO', 'Hand-inserted')"
                    ),
                    {"id": uuid.uuid4()},
                )
                connection.commit()

                market_rows = [
                    {"id": seed._market_id(code), "code": code, "display_name": name}
                    for code, name in seed._MARKETS
                ]
                with pytest.raises(RuntimeError, match="clave natural"):
                    seed._seed_rows(
                        connection,
                        seed._markets_t,
                        "id",
                        ("code",),
                        market_rows,
                        ("display_name",),
                    )
                connection.rollback()
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def test_downgrade_seed_removes_only_seeded_rows_keeps_schema_and_legacy_intact() -> None:
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        try:
            with engine.connect() as connection:
                assert _count(connection, "freyja2_instruments") == 10

            command.downgrade(cfg, "0006_catalog_display_names")
            with engine.connect() as connection:
                # Schema (including display_name) survives; only the rows go —
                # every one of the six catalog tables, not just a subset.
                assert _count(connection, "freyja2_underlying_markets") == 0
                assert _count(connection, "freyja2_product_types") == 0
                assert _count(connection, "freyja2_assets") == 0
                assert _count(connection, "freyja2_timeframes") == 0
                assert _count(connection, "freyja2_instruments") == 0
                assert _count(connection, "freyja2_instrument_timeframes") == 0
                connection.execute(
                    text("SELECT display_name FROM freyja2_underlying_markets LIMIT 0")
                )  # column must still exist
                auth_users_count = connection.execute(
                    text("SELECT COUNT(*) FROM auth_users")
                ).scalar_one()
                assert auth_users_count == 0

            command.upgrade(cfg, "head")
            with engine.connect() as connection:
                assert _count(connection, "freyja2_instruments") == 10
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def _snapshot_catalog(connection: Connection) -> dict[str, Sequence[Row[Any]]]:
    return {
        table: connection.execute(text(f"SELECT * FROM {table} ORDER BY 1")).all()
        for table in _CATALOG_TABLES
    }


def test_upgrade_from_0007_to_0008_preserves_existing_seed() -> None:
    """POINT1-DB-001 correction: 0008_catalog_integrity adds only constraints
    (never DML), so upgrading past it must not add, remove, or modify a
    single row seeded at 0007_seed_catalog_v1."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "0007_seed_catalog_v1")

        engine = create_engine(temp_url)
        try:
            with engine.connect() as connection:
                before = _snapshot_catalog(connection)

            command.upgrade(cfg, "0008_catalog_integrity")

            with engine.connect() as connection:
                after = _snapshot_catalog(connection)

            assert before == after
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def test_downgrade_0008_to_0007_and_back_preserves_seed_data() -> None:
    """0008's downgrade must retire exclusively the constraints it added and
    restore the 0007 schema — never delete or alter seeded rows. Round-trips
    head (0008) -> 0007 -> 0008 and asserts every catalog table is
    byte-for-byte identical at each step."""
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        try:
            with engine.connect() as connection:
                before = _snapshot_catalog(connection)

            command.downgrade(cfg, "0007_seed_catalog_v1")
            with engine.connect() as connection:
                after_downgrade = _snapshot_catalog(connection)
            assert after_downgrade == before

            command.upgrade(cfg, "0008_catalog_integrity")
            with engine.connect() as connection:
                after_upgrade = _snapshot_catalog(connection)
            assert after_upgrade == before
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()
