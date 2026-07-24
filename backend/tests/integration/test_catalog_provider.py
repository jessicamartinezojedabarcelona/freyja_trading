import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    DataSourceInstrumentPurpose,
    DataSourceType,
    Venue,
    VenueInstrument,
    VenueType,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

_PROVIDER_TABLES = frozenset(
    {
        "freyja2_venues",
        "freyja2_data_sources",
        "freyja2_venue_instruments",
        "freyja2_data_source_instruments",
    }
)

# Unambiguously fictitious fixtures — never presented as real, verified
# provider support. No real broker, exchange, or contract is named or
# seeded anywhere in this task.
_TEST_VENUE_CODE = "TEST_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_MARKET_DATA"
_TEST_SYMBOL = "TEST_BTCUSDT"


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(autouse=True)
def _truncate_provider_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(sorted(_PROVIDER_TABLES))} RESTART IDENTITY CASCADE")
        )
        connection.commit()


def _seeded_instrument_id(
    session: Session, market_code: str, product_code: str, symbol: str
) -> uuid.UUID:
    """Looks up an instrument already present in the approved v1 seed —
    never inserts a new canonical row into the shared database."""
    row = session.execute(
        text(
            "SELECT i.instrument_id FROM freyja2_instruments i "
            "JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id "
            "JOIN freyja2_product_types p ON p.id = i.product_type_id "
            "WHERE m.code = :market_code AND p.code = :product_code "
            "AND i.canonical_symbol = :symbol"
        ),
        {"market_code": market_code, "product_code": product_code, "symbol": symbol},
    ).scalar_one()
    return uuid.UUID(str(row))


def _make_venue(session: Session, code: str = _TEST_VENUE_CODE) -> Venue:
    venue = Venue(code=code, display_name=code.title(), venue_type=VenueType.EXCHANGE)
    session.add(venue)
    session.flush()
    return venue


def _make_data_source(session: Session, code: str = _TEST_SOURCE_CODE) -> DataSource:
    source = DataSource(
        code=code, display_name=code.title(), source_type=DataSourceType.MARKET_DATA
    )
    session.add(source)
    session.flush()
    return source


# --- Item 4: exactly the four new tables -------------------------------------


def test_upgrade_creates_exactly_the_four_provider_tables(auth_test_engine: Engine) -> None:
    inspector = inspect(auth_test_engine)
    provider_tables = {
        name
        for name in inspector.get_table_names()
        if name in _PROVIDER_TABLES
        or name.startswith("freyja2_venue")
        or name.startswith("freyja2_data_source")
    }
    assert provider_tables == _PROVIDER_TABLES


# --- Item 19: 0010 inserts nothing -------------------------------------------


def test_no_provider_rows_exist_after_migration(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        for table in _PROVIDER_TABLES:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            assert count == 0, f"{table} must be empty — 0010 creates schema only, never data"


# --- Item 17: no credential/account/authorization columns anywhere ----------


_FORBIDDEN_COLUMN_SUBSTRINGS = (
    "credential",
    "secret",
    "token",
    "password",
    "account",
    "api_key",
    "apikey",
    "environment",
    "demo",
    "real",
    "enabled",
    "verified",
    "supported",
    "availab",
    "authoriz",
    "permission",
)


def test_no_provider_table_has_credential_account_or_authorization_columns(
    auth_test_engine: Engine,
) -> None:
    inspector = inspect(auth_test_engine)
    for table in _PROVIDER_TABLES:
        for column in inspector.get_columns(table):
            column_name = column["name"].lower()
            for forbidden in _FORBIDDEN_COLUMN_SUBSTRINGS:
                assert forbidden not in column_name, (
                    f"{table}.{column['name']} looks like a credential/account/"
                    f"authorization column (matches {forbidden!r}) — forbidden by "
                    "POINT1-PROVIDER-001"
                )


# --- Items 6-7: Venue/DataSource code shape and uniqueness ------------------

_BLANK_OR_PADDED = ["", "   ", " X", "X "]


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_venue_code_rejects_blank_or_padded(db_session: Session, invalid_value: str) -> None:
    db_session.add(
        Venue(code=invalid_value, display_name="Test Exchange", venue_type=VenueType.EXCHANGE)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_data_source_code_rejects_blank_or_padded(db_session: Session, invalid_value: str) -> None:
    db_session.add(
        DataSource(
            code=invalid_value, display_name="Test Source", source_type=DataSourceType.MARKET_DATA
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_venue_code_is_unique(db_session: Session) -> None:
    _make_venue(db_session, _TEST_VENUE_CODE)
    db_session.add(
        Venue(code=_TEST_VENUE_CODE, display_name="Duplicate", venue_type=VenueType.BROKER)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_data_source_code_is_unique(db_session: Session) -> None:
    _make_data_source(db_session, _TEST_SOURCE_CODE)
    db_session.add(
        DataSource(
            code=_TEST_SOURCE_CODE, display_name="Duplicate", source_type=DataSourceType.EXCHANGE
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Items 6, 8: VenueInstrument.provider_symbol shape and uniqueness -------


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_venue_instrument_provider_symbol_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol=invalid_value
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_venue_instrument_venue_and_provider_symbol_combination_is_unique(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    other_instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "ETH/USDT")

    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol=_TEST_SYMBOL
        )
    )
    db_session.flush()

    # Same venue + same symbol, even against a DIFFERENT instrument, must
    # collide: a venue cannot use one symbol for two different listings.
    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=other_instrument_id, provider_symbol=_TEST_SYMBOL
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Item 10: a venue may expose several contracts for the same instrument -


def test_venue_can_have_multiple_contracts_for_the_same_instrument(db_session: Session) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add_all(
        [
            VenueInstrument(
                venue_id=venue.id, instrument_id=instrument_id, provider_symbol=f"{_TEST_SYMBOL}_A"
            ),
            VenueInstrument(
                venue_id=venue.id, instrument_id=instrument_id, provider_symbol=f"{_TEST_SYMBOL}_B"
            ),
        ]
    )
    db_session.flush()

    count = (
        db_session.query(VenueInstrument)
        .filter(
            VenueInstrument.venue_id == venue.id, VenueInstrument.instrument_id == instrument_id
        )
        .count()
    )
    assert count == 2


# --- Items 6, 9, 11, 12: DataSourceInstrument shape, uniqueness, purpose ----


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_data_source_instrument_provider_symbol_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    source = _make_data_source(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add(
        DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=instrument_id,
            provider_symbol=invalid_value,
            purpose=DataSourceInstrumentPurpose.ANALYSIS,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_data_source_symbol_purpose_combination_is_unique(db_session: Session) -> None:
    source = _make_data_source(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add(
        DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=instrument_id,
            provider_symbol=_TEST_SYMBOL,
            purpose=DataSourceInstrumentPurpose.ANALYSIS,
        )
    )
    db_session.flush()

    db_session.add(
        DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=instrument_id,
            provider_symbol=_TEST_SYMBOL,
            purpose=DataSourceInstrumentPurpose.ANALYSIS,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_analysis_and_settlement_remain_distinct_rows_for_same_source_and_instrument(
    db_session: Session,
) -> None:
    """Same data_source + instrument + provider_symbol under two DIFFERENT
    purposes must both be allowed and remain independently queryable — the
    unique constraint includes purpose precisely so ANALYSIS and SETTLEMENT
    are never conflated (POINT1-PROVIDER-001)."""
    source = _make_data_source(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add_all(
        [
            DataSourceInstrument(
                data_source_id=source.id,
                instrument_id=instrument_id,
                provider_symbol=_TEST_SYMBOL,
                purpose=DataSourceInstrumentPurpose.ANALYSIS,
            ),
            DataSourceInstrument(
                data_source_id=source.id,
                instrument_id=instrument_id,
                provider_symbol=_TEST_SYMBOL,
                purpose=DataSourceInstrumentPurpose.SETTLEMENT,
            ),
        ]
    )
    db_session.flush()

    analysis_count = (
        db_session.query(DataSourceInstrument)
        .filter(
            DataSourceInstrument.data_source_id == source.id,
            DataSourceInstrument.purpose == DataSourceInstrumentPurpose.ANALYSIS,
        )
        .count()
    )
    settlement_count = (
        db_session.query(DataSourceInstrument)
        .filter(
            DataSourceInstrument.data_source_id == source.id,
            DataSourceInstrument.purpose == DataSourceInstrumentPurpose.SETTLEMENT,
        )
        .count()
    )
    assert analysis_count == 1
    assert settlement_count == 1


def test_multiple_data_sources_can_map_the_same_instrument(db_session: Session) -> None:
    first_source = _make_data_source(db_session, "TEST_MARKET_DATA_A")
    second_source = _make_data_source(db_session, "TEST_MARKET_DATA_B")
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add_all(
        [
            DataSourceInstrument(
                data_source_id=first_source.id,
                instrument_id=instrument_id,
                provider_symbol=_TEST_SYMBOL,
                purpose=DataSourceInstrumentPurpose.ANALYSIS,
            ),
            DataSourceInstrument(
                data_source_id=second_source.id,
                instrument_id=instrument_id,
                provider_symbol=_TEST_SYMBOL,
                purpose=DataSourceInstrumentPurpose.ANALYSIS,
            ),
        ]
    )
    db_session.flush()

    count = (
        db_session.query(DataSourceInstrument)
        .filter(DataSourceInstrument.instrument_id == instrument_id)
        .count()
    )
    assert count == 2


# --- Item 13: a mapping never modifies canonical_symbol ---------------------


def test_creating_a_mapping_never_modifies_the_instrument_canonical_symbol(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")

    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol=_TEST_SYMBOL
        )
    )
    db_session.flush()

    canonical_symbol = db_session.execute(
        text("SELECT canonical_symbol FROM freyja2_instruments WHERE instrument_id = :id"),
        {"id": instrument_id},
    ).scalar_one()
    assert canonical_symbol == "BTC/USDT"


# --- Items 15-16: FKs block deletion, no CASCADE ----------------------------


def test_fk_prevents_deleting_a_referenced_venue(db_session: Session) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol=_TEST_SYMBOL
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM freyja2_venues WHERE id = :id"), {"id": venue.id})
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_referenced_data_source(db_session: Session) -> None:
    source = _make_data_source(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    db_session.add(
        DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=instrument_id,
            provider_symbol=_TEST_SYMBOL,
            purpose=DataSourceInstrumentPurpose.ANALYSIS,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_data_sources WHERE id = :id"), {"id": source.id}
        )
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_referenced_instrument(db_session: Session) -> None:
    """Also demonstrates item 16 (no CASCADE): if either FK cascaded, this
    DELETE would silently succeed and take the mapping down with it instead
    of raising."""
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol=_TEST_SYMBOL
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_instruments WHERE instrument_id = :id"),
            {"id": instrument_id},
        )
        db_session.flush()
    db_session.rollback()


# --- Item 14 / extensibility: same text under different canonical products,
# and a future CRYPTO x BINARY_OPTION x BTC/USDT instrument added without
# touching provider tables -- demonstrated with a temporary canonical row
# created ONLY inside an isolated, throwaway database, never the shared
# seed. -----------------------------------------------------------------


@pytest.fixture
def isolated_seeded_database() -> Iterator[Engine]:
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


def test_binary_option_on_a_pair_reuses_the_symbol_text_without_colliding(
    isolated_seeded_database: Engine,
) -> None:
    """Not part of the approved v1 seed (2/2/7/10/5/50 stays untouched
    everywhere else) — this row exists only inside this throwaway,
    isolated database, purely to prove the architecture: a future
    CRYPTO x BINARY_OPTION x BTC/USDT instrument (referencing the canonical
    CRYPTO x SPOT x BTC/USDT pair as its underlying, exactly like the
    existing FOREX x BINARY_OPTION x EUR/USD seed row does) can be added,
    and provider mappings attached to it, without changing
    freyja2_venues/freyja2_data_sources/freyja2_venue_instruments/
    freyja2_data_source_instruments at all."""
    engine = isolated_seeded_database
    with engine.begin() as connection:
        crypto_market_id = connection.execute(
            text("SELECT id FROM freyja2_underlying_markets WHERE code = 'CRYPTO'")
        ).scalar_one()
        spot_product_id = connection.execute(
            text("SELECT id FROM freyja2_product_types WHERE code = 'SPOT'")
        ).scalar_one()
        binary_product_id = connection.execute(
            text("SELECT id FROM freyja2_product_types WHERE code = 'BINARY_OPTION'")
        ).scalar_one()
        spot_btc_usdt_id = connection.execute(
            text(
                "SELECT instrument_id FROM freyja2_instruments "
                "WHERE underlying_market_id = :market_id AND product_type_id = :product_id "
                "AND canonical_symbol = 'BTC/USDT'"
            ),
            {"market_id": crypto_market_id, "product_id": spot_product_id},
        ).scalar_one()

        temporary_binary_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_instruments "
                "(instrument_id, underlying_market_id, product_type_id, canonical_symbol, "
                "underlying_instrument_id, is_active) "
                "VALUES (:id, :market_id, :product_id, 'BTC/USDT', :underlying, true)"
            ),
            {
                "id": temporary_binary_id,
                "market_id": crypto_market_id,
                "product_id": binary_product_id,
                "underlying": spot_btc_usdt_id,
            },
        )

        # Same canonical_symbol text ('BTC/USDT'), different product —
        # no collision, because uq_freyja2_instruments_market_product_symbol
        # is keyed on (market, product, symbol), not symbol alone.
        distinct_ids = connection.execute(
            text(
                "SELECT COUNT(DISTINCT instrument_id) FROM freyja2_instruments "
                "WHERE underlying_market_id = :market_id AND canonical_symbol = 'BTC/USDT'"
            ),
            {"market_id": crypto_market_id},
        ).scalar_one()
        assert distinct_ids == 2

        # Provider tables attach to the new temporary instrument with zero
        # schema changes.
        venue_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_venues (id, code, display_name, venue_type, is_active) "
                "VALUES (:id, :code, :name, 'BROKER', true)"
            ),
            {"id": venue_id, "code": _TEST_VENUE_CODE, "name": "Test Exchange"},
        )
        connection.execute(
            text(
                "INSERT INTO freyja2_venue_instruments "
                "(id, venue_id, instrument_id, provider_symbol, is_active) "
                "VALUES (:id, :venue_id, :instrument_id, :symbol, true)"
            ),
            {
                "id": uuid.uuid4(),
                "venue_id": venue_id,
                "instrument_id": temporary_binary_id,
                "symbol": f"{_TEST_SYMBOL}_BINARY",
            },
        )

        mapped_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM freyja2_venue_instruments "
                "WHERE instrument_id = :instrument_id"
            ),
            {"instrument_id": temporary_binary_id},
        ).scalar_one()
        assert mapped_count == 1
