import dataclasses
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Row, create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from alembic import command
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.db import catalog_seed_v1 as seed_spec

BACKEND_DIR = Path(__file__).resolve().parents[2]

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
    state (idempotency re-verification, divergence detection) — never
    shared with other tests."""
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


@pytest.fixture
def isolated_migrated_database() -> Iterator[tuple[Config, Engine]]:
    """A fresh isolated temp database per test, exposing both the Alembic
    Config (for command.upgrade/downgrade against a specific revision) and
    an Engine — for tests that need to migrate to a partial revision, mutate
    data by hand, then attempt a further migration."""
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

        engine = create_engine(temp_url)
        try:
            yield cfg, engine
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


def _snapshot_catalog(connection: Connection) -> dict[str, Sequence[Row[Any]]]:
    return {
        table: connection.execute(text(f"SELECT * FROM {table} ORDER BY 1")).all()
        for table in _CATALOG_TABLES
    }


def _current_revision(connection: Connection) -> str:
    return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


# --- Exact v1 scope, shape, and identity ------------------------------------


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
    spot_id = seed_spec.instrument_id("FOREX", "SPOT", "EUR/USD")
    binary_id = seed_spec.instrument_id("FOREX", "BINARY_OPTION", "EUR/USD")

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


def test_market_id_matches_independent_uuidv5_calculation_from_literal_url(
    seeded_engine: Engine,
) -> None:
    """Independent recomputation: uuid.uuid5 applied directly to a literal
    URL string — never calling entity_uuid()/market_id(), so the expected
    value isn't derived from the function under test — must match both what
    the module produces and what is actually stored (item 24)."""
    expected = uuid.uuid5(
        uuid.NAMESPACE_URL, "https://freyja.app/freyja2/catalog/v1/underlying-market/CRYPTO"
    )
    assert seed_spec.market_id("CRYPTO") == expected

    with seeded_engine.connect() as connection:
        stored_market_id = connection.execute(
            text("SELECT id FROM freyja2_underlying_markets WHERE code = 'CRYPTO'")
        ).scalar_one()
        assert stored_market_id == expected


def test_instrument_id_matches_independent_uuidv5_calculation_from_literal_url(
    seeded_engine: Engine,
) -> None:
    expected = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "https://freyja.app/freyja2/catalog/v1/instrument/FOREX/SPOT/EUR%2FUSD",
    )
    assert seed_spec.instrument_id("FOREX", "SPOT", "EUR/USD") == expected

    with seeded_engine.connect() as connection:
        stored_instrument_id = connection.execute(
            text(
                "SELECT instrument_id FROM freyja2_instruments "
                "WHERE canonical_symbol = 'EUR/USD' AND underlying_market_id = :market_id "
                "AND underlying_asset_id IS NULL AND underlying_instrument_id IS NULL"
            ),
            {"market_id": seed_spec.market_id("FOREX")},
        ).scalar_one()
        assert stored_instrument_id == expected


# --- Independent regression anchors: literal expected values, never derived
# by calling the function/module under test against itself ------------------

_APPROVED_MARKETS = (
    ("CRYPTO", "Crypto"),
    ("FOREX", "Forex"),
)
_APPROVED_PRODUCTS = (
    ("SPOT", "Spot"),
    ("BINARY_OPTION", "Binary option"),
)
_APPROVED_ASSETS = (
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("XRP", "XRP"),
    ("USDT", "Tether USD"),
    ("EUR", "Euro"),
    ("USD", "US dollar"),
)
_APPROVED_TIMEFRAMES = (
    ("1m", 60, "1 minute"),
    ("5m", 300, "5 minutes"),
    ("15m", 900, "15 minutes"),
    ("1h", 3600, "1 hour"),
    ("4h", 14400, "4 hours"),
)
_APPROVED_INSTRUMENTS = (
    seed_spec.InstrumentSpec("CRYPTO", "SPOT", "BTC/USDT", base="BTC", quote="USDT"),
    seed_spec.InstrumentSpec("CRYPTO", "SPOT", "ETH/USDT", base="ETH", quote="USDT"),
    seed_spec.InstrumentSpec("CRYPTO", "SPOT", "SOL/USDT", base="SOL", quote="USDT"),
    seed_spec.InstrumentSpec("CRYPTO", "SPOT", "XRP/USDT", base="XRP", quote="USDT"),
    seed_spec.InstrumentSpec("FOREX", "SPOT", "EUR/USD", base="EUR", quote="USD"),
    seed_spec.InstrumentSpec("CRYPTO", "BINARY_OPTION", "BTC", underlying_asset="BTC"),
    seed_spec.InstrumentSpec("CRYPTO", "BINARY_OPTION", "ETH", underlying_asset="ETH"),
    seed_spec.InstrumentSpec("CRYPTO", "BINARY_OPTION", "SOL", underlying_asset="SOL"),
    seed_spec.InstrumentSpec("CRYPTO", "BINARY_OPTION", "XRP", underlying_asset="XRP"),
    seed_spec.InstrumentSpec(
        "FOREX",
        "BINARY_OPTION",
        "EUR/USD",
        underlying_instrument=seed_spec.InstrumentKey("FOREX", "SPOT", "EUR/USD"),
    ),
)

# The exact SHA-256 fingerprint 0007_seed_catalog_v1 and 0009_seed_integrity_
# guard each pin as their own historical anchor — a literal here too, not
# obtained by calling contract_fingerprint() and comparing it to itself.
_APPROVED_V1_CONTRACT_SHA256 = "0f40a3df7ed37f9d69a2dd66437747bf72830831b430f17d4a97f695c81117c2"


def test_markets_match_exact_scope_approved_in_point1_domain_001() -> None:
    assert seed_spec.MARKETS == _APPROVED_MARKETS


def test_products_match_exact_scope_approved_in_point1_domain_001() -> None:
    assert seed_spec.PRODUCTS == _APPROVED_PRODUCTS


def test_assets_match_exact_scope_approved_in_point1_domain_001() -> None:
    assert seed_spec.ASSETS == _APPROVED_ASSETS


def test_timeframes_match_exact_scope_approved_in_point1_domain_001() -> None:
    assert seed_spec.TIMEFRAMES == _APPROVED_TIMEFRAMES


def test_instruments_match_exact_scope_approved_in_point1_seed_001() -> None:
    assert seed_spec.INSTRUMENTS == _APPROVED_INSTRUMENTS


def test_contract_fingerprint_matches_the_approved_v1_anchor() -> None:
    assert seed_spec.contract_fingerprint() == _APPROVED_V1_CONTRACT_SHA256


# --- The REAL serialization detects these changes — not a monkeypatched
# contract_fingerprint() return value, but the actual module-level *_ROWS
# data that _canonical_lines()/canonical_serialization() actually reads at
# call time. Each test patches the input data, then calls the real
# contract_fingerprint() and checks the digest actually moved. -------------


def test_fingerprint_changes_if_a_deterministic_uuid_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stands in for a future change to entity_uuid()'s algorithm,
    uuid.NAMESPACE_URL, or the base URL — any of which would change every
    deterministic UUID the same way a single row's id changing here does."""
    original = seed_spec.contract_fingerprint()
    altered_market = dataclasses.replace(seed_spec.MARKET_ROWS[0], id=uuid.uuid4())
    monkeypatch.setattr(seed_spec, "MARKET_ROWS", (altered_market, *seed_spec.MARKET_ROWS[1:]))

    assert seed_spec.contract_fingerprint() != original


def test_fingerprint_changes_if_a_row_is_active_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    original = seed_spec.contract_fingerprint()
    deactivated = dataclasses.replace(seed_spec.INSTRUMENT_ROWS[0], is_active=False)
    monkeypatch.setattr(seed_spec, "INSTRUMENT_ROWS", (deactivated, *seed_spec.INSTRUMENT_ROWS[1:]))

    assert seed_spec.contract_fingerprint() != original


def test_fingerprint_changes_if_an_association_is_active_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = seed_spec.contract_fingerprint()
    deactivated = dataclasses.replace(seed_spec.INSTRUMENT_TIMEFRAME_ROWS[0], is_active=False)
    monkeypatch.setattr(
        seed_spec,
        "INSTRUMENT_TIMEFRAME_ROWS",
        (deactivated, *seed_spec.INSTRUMENT_TIMEFRAME_ROWS[1:]),
    )

    assert seed_spec.contract_fingerprint() != original


def test_fingerprint_changes_if_an_association_uuid_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = seed_spec.contract_fingerprint()
    rewired = dataclasses.replace(seed_spec.INSTRUMENT_TIMEFRAME_ROWS[0], timeframe_id=uuid.uuid4())
    monkeypatch.setattr(
        seed_spec,
        "INSTRUMENT_TIMEFRAME_ROWS",
        (rewired, *seed_spec.INSTRUMENT_TIMEFRAME_ROWS[1:]),
    )

    assert seed_spec.contract_fingerprint() != original


# --- Deep immutability: mutation attempts must fail --------------------------


def test_canonical_markets_tuple_rejects_item_assignment() -> None:
    with pytest.raises(TypeError):
        seed_spec.MARKETS[0] = ("HACKED", "Hacked")  # type: ignore[index]


def test_canonical_instruments_tuple_rejects_item_assignment() -> None:
    with pytest.raises(TypeError):
        seed_spec.INSTRUMENTS[0] = seed_spec.InstrumentSpec(  # type: ignore[index]
            "HACKED", "HACKED", "HACKED"
        )


def test_instrument_spec_rejects_attribute_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        seed_spec.INSTRUMENTS[0].market = "HACKED"  # type: ignore[misc]


def test_market_row_rejects_attribute_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        seed_spec.MARKET_ROWS[0].display_name = "Hacked"  # type: ignore[misc]


def test_instrument_row_rejects_attribute_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        seed_spec.INSTRUMENT_ROWS[0].canonical_symbol = "HACKED"  # type: ignore[misc]


def test_association_row_rejects_attribute_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        seed_spec.INSTRUMENT_TIMEFRAME_ROWS[0].is_active = False  # type: ignore[misc]


def test_seed_table_spec_rejects_attribute_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        seed_spec.CATALOG_ROW_SPECS[0].id_column = "hacked"  # type: ignore[misc]


# --- Contract-alteration guard: fails closed before any DML -----------------


def test_altered_contract_fails_fingerprint_before_0007_inserts_anything(
    monkeypatch: pytest.MonkeyPatch, isolated_migrated_database: tuple[Config, Engine]
) -> None:
    """Simulates an accidental edit to catalog_seed_v1.py (a typo, a merge
    mistake) by monkeypatching contract_fingerprint() so it no longer
    matches either migration's pinned anchor. 0007 must abort before
    inserting a single row, and the revision must not advance."""
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "0006_catalog_display_names")

    monkeypatch.setattr(seed_spec, "contract_fingerprint", lambda: "0" * 64)

    with pytest.raises(seed_spec.ContractFingerprintError):
        command.upgrade(cfg, "0007_seed_catalog_v1")

    with engine.connect() as connection:
        assert _current_revision(connection) == "0006_catalog_display_names"
        assert _count(connection, "freyja2_underlying_markets") == 0
        assert _count(connection, "freyja2_instruments") == 0


def test_altered_contract_fails_fingerprint_before_0009_verifies_anything(
    monkeypatch: pytest.MonkeyPatch, isolated_migrated_database: tuple[Config, Engine]
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "0008_catalog_integrity")

    monkeypatch.setattr(seed_spec, "contract_fingerprint", lambda: "0" * 64)

    with pytest.raises(seed_spec.ContractFingerprintError):
        command.upgrade(cfg, "0009_seed_integrity_guard")

    with engine.connect() as connection:
        assert _current_revision(connection) == "0008_catalog_integrity"


# --- Item 1: idempotent re-verification -------------------------------------


def test_reapplying_verification_across_full_seed_is_idempotent(
    isolated_seeded_connection: Connection,
) -> None:
    """Re-running the fail-closed verification against an
    already-correctly-seeded catalog changes nothing anywhere: every
    canonical row and all 50 associations verify as present and matching,
    and a full snapshot of all six tables is unchanged."""
    connection = isolated_seeded_connection
    before = _snapshot_catalog(connection)

    for table_spec in seed_spec.CATALOG_ROW_SPECS:
        for row in table_spec.rows:
            assert seed_spec.verify_row(
                connection,
                table_spec.table,
                table_spec.id_column,
                table_spec.natural_key_columns,
                row,
                table_spec.compare_columns,
            )
    for row in seed_spec.INSTRUMENT_TIMEFRAME_ROWS:
        assert seed_spec.verify_association(connection, row.instrument_id, row.timeframe_id)
    connection.commit()

    after = _snapshot_catalog(connection)
    assert before == after


# --- Items 2-7: is_active=false is a divergence, per table -----------------


def test_market_is_active_false_is_a_divergence(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    crypto_id = seed_spec.market_id("CRYPTO")
    connection.execute(
        text("UPDATE freyja2_underlying_markets SET is_active = false WHERE id = :id"),
        {"id": crypto_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.MARKET_ROWS if r.code == "CRYPTO")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection, seed_spec.MARKETS_TABLE, "id", ("code",), row, ("display_name", "is_active")
        )
    connection.rollback()

    is_active = connection.execute(
        text("SELECT is_active FROM freyja2_underlying_markets WHERE id = :id"), {"id": crypto_id}
    ).scalar_one()
    assert is_active is False


def test_product_is_active_false_is_a_divergence(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    spot_id = seed_spec.product_id("SPOT")
    connection.execute(
        text("UPDATE freyja2_product_types SET is_active = false WHERE id = :id"), {"id": spot_id}
    )
    connection.commit()

    row = next(r for r in seed_spec.PRODUCT_ROWS if r.code == "SPOT")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection,
            seed_spec.PRODUCTS_TABLE,
            "id",
            ("code",),
            row,
            ("display_name", "is_active"),
        )
    connection.rollback()


def test_asset_is_active_false_is_a_divergence(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    btc_id = seed_spec.asset_id("BTC")
    connection.execute(
        text("UPDATE freyja2_assets SET is_active = false WHERE id = :id"), {"id": btc_id}
    )
    connection.commit()

    row = next(r for r in seed_spec.ASSET_ROWS if r.code == "BTC")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection, seed_spec.ASSETS_TABLE, "id", ("code",), row, ("display_name", "is_active")
        )
    connection.rollback()


def test_timeframe_is_active_false_is_a_divergence(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    one_minute_id = seed_spec.timeframe_id("1m")
    connection.execute(
        text("UPDATE freyja2_timeframes SET is_active = false WHERE id = :id"),
        {"id": one_minute_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.TIMEFRAME_ROWS if r.code == "1m")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection,
            seed_spec.TIMEFRAMES_TABLE,
            "id",
            ("code",),
            row,
            ("duration_seconds", "display_name", "is_active"),
        )
    connection.rollback()


def test_instrument_is_active_false_is_a_divergence(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    btc_usdt_id = seed_spec.instrument_id("CRYPTO", "SPOT", "BTC/USDT")
    connection.execute(
        text("UPDATE freyja2_instruments SET is_active = false WHERE instrument_id = :id"),
        {"id": btc_usdt_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.INSTRUMENT_ROWS if r.canonical_symbol == "BTC/USDT")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection,
            seed_spec.INSTRUMENTS_TABLE,
            "instrument_id",
            ("underlying_market_id", "product_type_id", "canonical_symbol"),
            row,
            (
                "base_asset_id",
                "quote_asset_id",
                "underlying_asset_id",
                "underlying_instrument_id",
                "is_active",
            ),
        )
    connection.rollback()


def test_association_is_active_false_is_a_divergence(
    isolated_seeded_connection: Connection,
) -> None:
    connection = isolated_seeded_connection
    row = seed_spec.INSTRUMENT_TIMEFRAME_ROWS[0]
    connection.execute(
        text(
            "UPDATE freyja2_instrument_timeframes SET is_active = false "
            "WHERE instrument_id = :instrument_id AND timeframe_id = :timeframe_id"
        ),
        {"instrument_id": row.instrument_id, "timeframe_id": row.timeframe_id},
    )
    connection.commit()

    with pytest.raises(seed_spec.SeedDivergenceError, match="inactiva"):
        seed_spec.verify_association(connection, row.instrument_id, row.timeframe_id)
    connection.rollback()


# --- Items 8-11: other field divergences -------------------------------------


def test_display_name_divergence_aborts_and_preserves_original(
    isolated_seeded_connection: Connection,
) -> None:
    connection = isolated_seeded_connection
    crypto_id = seed_spec.market_id("CRYPTO")
    connection.execute(
        text("UPDATE freyja2_underlying_markets SET display_name = 'Corrupted' WHERE id = :id"),
        {"id": crypto_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.MARKET_ROWS if r.code == "CRYPTO")
    with pytest.raises(seed_spec.SeedDivergenceError, match="diverge"):
        seed_spec.verify_row(
            connection, seed_spec.MARKETS_TABLE, "id", ("code",), row, ("display_name", "is_active")
        )
    connection.rollback()

    display_name = connection.execute(
        text("SELECT display_name FROM freyja2_underlying_markets WHERE id = :id"),
        {"id": crypto_id},
    ).scalar_one()
    assert display_name == "Corrupted"


def test_canonical_symbol_divergence_is_detected_as_missing_not_silently_kept(
    isolated_seeded_connection: Connection,
) -> None:
    """canonical_symbol is part of the instrument's own natural key, so
    corrupting it moves the row out from under its natural-key lookup: the
    seed then sees it as MISSING rather than merely diverged. Either way it
    is never silently reconstructed or renamed back — 0009 would raise
    SeedMissingError for it, never repair it."""
    connection = isolated_seeded_connection
    btc_usdt_id = seed_spec.instrument_id("CRYPTO", "SPOT", "BTC/USDT")
    connection.execute(
        text(
            "UPDATE freyja2_instruments SET canonical_symbol = 'BTC/CORRUPTED' "
            "WHERE instrument_id = :id"
        ),
        {"id": btc_usdt_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.INSTRUMENT_ROWS if r.canonical_symbol == "BTC/USDT")
    found = seed_spec.verify_row(
        connection,
        seed_spec.INSTRUMENTS_TABLE,
        "instrument_id",
        ("underlying_market_id", "product_type_id", "canonical_symbol"),
        row,
        (
            "base_asset_id",
            "quote_asset_id",
            "underlying_asset_id",
            "underlying_instrument_id",
            "is_active",
        ),
    )
    assert found is False
    connection.rollback()

    canonical_symbol = connection.execute(
        text("SELECT canonical_symbol FROM freyja2_instruments WHERE instrument_id = :id"),
        {"id": btc_usdt_id},
    ).scalar_one()
    assert canonical_symbol == "BTC/CORRUPTED"


def test_duration_seconds_divergence_is_detected(isolated_seeded_connection: Connection) -> None:
    connection = isolated_seeded_connection
    one_minute_id = seed_spec.timeframe_id("1m")
    connection.execute(
        text("UPDATE freyja2_timeframes SET duration_seconds = 61 WHERE id = :id"),
        {"id": one_minute_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.TIMEFRAME_ROWS if r.code == "1m")
    with pytest.raises(seed_spec.SeedDivergenceError, match="duration_seconds"):
        seed_spec.verify_row(
            connection,
            seed_spec.TIMEFRAMES_TABLE,
            "id",
            ("code",),
            row,
            ("duration_seconds", "display_name", "is_active"),
        )
    connection.rollback()


def test_instrument_fk_divergence_is_detected(isolated_seeded_connection: Connection) -> None:
    """Changing which asset an instrument's base_asset_id FK points to is a
    divergence in a compare_column — caught without ever inferring or
    repairing it from canonical_symbol."""
    connection = isolated_seeded_connection
    btc_usdt_id = seed_spec.instrument_id("CRYPTO", "SPOT", "BTC/USDT")
    connection.execute(
        text(
            "UPDATE freyja2_instruments SET base_asset_id = :wrong_asset WHERE instrument_id = :id"
        ),
        {"wrong_asset": seed_spec.asset_id("ETH"), "id": btc_usdt_id},
    )
    connection.commit()

    row = next(r for r in seed_spec.INSTRUMENT_ROWS if r.canonical_symbol == "BTC/USDT")
    with pytest.raises(seed_spec.SeedDivergenceError, match="base_asset_id"):
        seed_spec.verify_row(
            connection,
            seed_spec.INSTRUMENTS_TABLE,
            "instrument_id",
            ("underlying_market_id", "product_type_id", "canonical_symbol"),
            row,
            (
                "base_asset_id",
                "quote_asset_id",
                "underlying_asset_id",
                "underlying_instrument_id",
                "is_active",
            ),
        )
    connection.rollback()


# --- Item 12: same natural key, different id --------------------------------


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
            with engine.connect() as connection:
                # A pre-existing row under the same natural key ("CRYPTO")
                # but a random, non-deterministic id — never produced by the
                # seed itself.
                connection.execute(
                    text(
                        "INSERT INTO freyja2_underlying_markets "
                        "(id, code, display_name, is_active) "
                        "VALUES (:id, 'CRYPTO', 'Hand-inserted', true)"
                    ),
                    {"id": uuid.uuid4()},
                )
                connection.commit()

                row = next(r for r in seed_spec.MARKET_ROWS if r.code == "CRYPTO")
                with pytest.raises(seed_spec.SeedDivergenceError, match="clave natural"):
                    seed_spec.verify_row(
                        connection,
                        seed_spec.MARKETS_TABLE,
                        "id",
                        ("code",),
                        row,
                        ("display_name", "is_active"),
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


# --- Items 13-14: 0009 aborts on missing rows/associations, never rebuilds --


def test_0009_aborts_on_missing_canonical_row_without_reconstructing_it(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "0008_catalog_integrity")

    xrp_id = seed_spec.asset_id("XRP")
    # XRP is referenced by two canonical instruments: the CRYPTO x SPOT
    # PAIR (base_asset_id) and the CRYPTO x BINARY_OPTION ASSET_UNDERLYING
    # (underlying_asset_id) — both must go before the asset itself can be
    # removed to simulate the missing-row scenario.
    references_xrp = (
        "base_asset_id = :asset_id OR quote_asset_id = :asset_id OR underlying_asset_id = :asset_id"
    )
    with engine.begin() as connection:
        # Clear XRP's dependents first (FK) — the kind of state a partial
        # manual edit could plausibly leave behind.
        connection.execute(
            text(
                "DELETE FROM freyja2_instrument_timeframes WHERE instrument_id IN ("
                f"SELECT instrument_id FROM freyja2_instruments WHERE {references_xrp})"
            ),
            {"asset_id": xrp_id},
        )
        connection.execute(
            text(f"DELETE FROM freyja2_instruments WHERE {references_xrp}"),
            {"asset_id": xrp_id},
        )
        connection.execute(
            text("DELETE FROM freyja2_assets WHERE id = :asset_id"), {"asset_id": xrp_id}
        )

    with pytest.raises(seed_spec.SeedMissingError):
        command.upgrade(cfg, "0009_seed_integrity_guard")

    with engine.connect() as connection:
        assert _current_revision(connection) == "0008_catalog_integrity"
        exists = connection.execute(
            text("SELECT 1 FROM freyja2_assets WHERE id = :asset_id"), {"asset_id": xrp_id}
        ).first()
        assert exists is None


def test_0009_aborts_on_missing_association_without_reconstructing_it(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "0008_catalog_integrity")

    row = seed_spec.INSTRUMENT_TIMEFRAME_ROWS[0]
    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM freyja2_instrument_timeframes "
                "WHERE instrument_id = :instrument_id AND timeframe_id = :timeframe_id"
            ),
            {"instrument_id": row.instrument_id, "timeframe_id": row.timeframe_id},
        )

    with pytest.raises(seed_spec.SeedMissingError):
        command.upgrade(cfg, "0009_seed_integrity_guard")

    with engine.connect() as connection:
        assert _current_revision(connection) == "0008_catalog_integrity"
        exists = connection.execute(
            text(
                "SELECT 1 FROM freyja2_instrument_timeframes "
                "WHERE instrument_id = :instrument_id AND timeframe_id = :timeframe_id"
            ),
            {"instrument_id": row.instrument_id, "timeframe_id": row.timeframe_id},
        ).first()
        assert exists is None


# --- Item 15: non-conflicting custom row is accepted and preserved --------


def test_0009_accepts_and_preserves_a_non_conflicting_custom_row(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "0008_catalog_integrity")

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO freyja2_underlying_markets (id, code, display_name, is_active) "
                "VALUES (:id, 'COMMODITY', 'Commodity', true)"
            ),
            {"id": uuid.uuid4()},
        )

    command.upgrade(cfg, "0009_seed_integrity_guard")  # must not raise

    with engine.connect() as connection:
        assert _current_revision(connection) == "0009_seed_integrity_guard"
        exists = connection.execute(
            text("SELECT 1 FROM freyja2_underlying_markets WHERE code = 'COMMODITY'")
        ).first()
        assert exists is not None
        assert _count(connection, "freyja2_underlying_markets") == 3  # 2 canonical + 1 custom


# --- Items 16-19: fail-closed downgrade -------------------------------------


def test_downgrade_removes_only_canonical_rows_and_preserves_custom_rows(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "head")

    custom_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO freyja2_underlying_markets (id, code, display_name, is_active) "
                "VALUES (:id, 'COMMODITY', 'Commodity', true)"
            ),
            {"id": custom_id},
        )

    command.downgrade(cfg, "0006_catalog_display_names")

    with engine.connect() as connection:
        assert _count(connection, "freyja2_underlying_markets") == 1
        exists = connection.execute(
            text("SELECT 1 FROM freyja2_underlying_markets WHERE id = :id"), {"id": custom_id}
        ).first()
        assert exists is not None
        assert _count(connection, "freyja2_instruments") == 0
        assert _count(connection, "freyja2_instrument_timeframes") == 0


def test_downgrade_aborts_on_modified_canonical_row_and_deletes_nothing(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "head")

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE freyja2_underlying_markets SET display_name = 'Corrupted' WHERE id = :id"),
            {"id": seed_spec.market_id("CRYPTO")},
        )

    with pytest.raises(seed_spec.SeedDivergenceError):
        command.downgrade(cfg, "0006_catalog_display_names")

    with engine.connect() as connection:
        assert _count(connection, "freyja2_underlying_markets") == 2
        assert _count(connection, "freyja2_product_types") == 2
        assert _count(connection, "freyja2_assets") == 7
        assert _count(connection, "freyja2_timeframes") == 5
        assert _count(connection, "freyja2_instruments") == 10
        assert _count(connection, "freyja2_instrument_timeframes") == 50
        assert _current_revision(connection) == "0009_seed_integrity_guard"


def test_downgrade_aborts_on_inactive_canonical_row_and_deletes_nothing(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "head")

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE freyja2_instruments SET is_active = false WHERE instrument_id = :id"),
            {"id": seed_spec.instrument_id("CRYPTO", "SPOT", "BTC/USDT")},
        )

    with pytest.raises(seed_spec.SeedDivergenceError):
        command.downgrade(cfg, "0006_catalog_display_names")

    with engine.connect() as connection:
        assert _count(connection, "freyja2_instruments") == 10
        assert _count(connection, "freyja2_instrument_timeframes") == 50
        assert _current_revision(connection) == "0009_seed_integrity_guard"


def test_downgrade_blocked_by_external_reference_without_cascade_or_partial_loss(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    """A custom instrument linked to a canonical timeframe is not swept up
    by the association delete (which targets only canonical instrument_id
    AND canonical timeframe_id pairs), so it remains behind and blocks the
    later DELETE of that timeframe row via a real FK violation — no CASCADE
    anywhere. Because everything runs in one migration transaction, that
    failure rolls back every delete already issued in this downgrade: no
    partial loss."""
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "head")

    custom_instrument_id = uuid.uuid4()
    one_minute_id = seed_spec.timeframe_id("1m")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO freyja2_instruments "
                "(instrument_id, underlying_market_id, product_type_id, canonical_symbol, "
                "base_asset_id, quote_asset_id, is_active) "
                "VALUES (:id, :market_id, :product_id, 'USDT/BTC', :base, :quote, true)"
            ),
            {
                "id": custom_instrument_id,
                "market_id": seed_spec.market_id("CRYPTO"),
                "product_id": seed_spec.product_id("SPOT"),
                "base": seed_spec.asset_id("USDT"),
                "quote": seed_spec.asset_id("BTC"),
            },
        )
        connection.execute(
            text(
                "INSERT INTO freyja2_instrument_timeframes "
                "(instrument_id, timeframe_id, is_active) "
                "VALUES (:instrument_id, :timeframe_id, true)"
            ),
            {"instrument_id": custom_instrument_id, "timeframe_id": one_minute_id},
        )

    with pytest.raises(IntegrityError):
        command.downgrade(cfg, "0006_catalog_display_names")

    with engine.connect() as connection:
        assert _count(connection, "freyja2_timeframes") == 5
        assert _count(connection, "freyja2_instruments") == 11  # 10 canonical + 1 custom
        assert _count(connection, "freyja2_instrument_timeframes") == 51  # 50 + 1 custom
        assert _current_revision(connection) == "0009_seed_integrity_guard"


# --- POINT1-DB-001: 0007 <-> 0008 preserve the seed (unchanged behavior) ----


def test_upgrade_from_0007_to_0008_preserves_existing_seed() -> None:
    """0008_catalog_integrity adds only constraints (never DML), so
    upgrading past it must not add, remove, or modify a single row seeded
    at 0007_seed_catalog_v1."""
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
    restore the 0007 schema — never delete or alter seeded rows."""
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


# --- Item 22: 0009's downgrade is a true no-op ------------------------------


def test_0009_downgrade_upgrade_roundtrip_does_not_modify_data(
    isolated_migrated_database: tuple[Config, Engine],
) -> None:
    """0009_seed_integrity_guard creates no schema and writes no data, so
    round-tripping head (0009) -> 0008 -> 0009 must leave every catalog
    table byte-for-byte identical at each step."""
    cfg, engine = isolated_migrated_database
    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        before = _snapshot_catalog(connection)

    command.downgrade(cfg, "0008_catalog_integrity")
    with engine.connect() as connection:
        after_downgrade = _snapshot_catalog(connection)
    assert after_downgrade == before

    command.upgrade(cfg, "0009_seed_integrity_guard")
    with engine.connect() as connection:
        after_upgrade = _snapshot_catalog(connection)
    assert after_upgrade == before


# --- Legacy/schema isolation (unchanged) ------------------------------------


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
