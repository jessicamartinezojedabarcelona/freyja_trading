import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.db.models.catalog import (
    Asset,
    Instrument,
    InstrumentTimeframe,
    ProductType,
    Timeframe,
    UnderlyingMarket,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

_CATALOG_TABLES = frozenset(
    {
        "freyja2_underlying_markets",
        "freyja2_product_types",
        "freyja2_assets",
        "freyja2_timeframes",
        "freyja2_instruments",
        "freyja2_instrument_timeframes",
    }
)


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(autouse=True)
def _truncate_catalog_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(sorted(_CATALOG_TABLES))} RESTART IDENTITY CASCADE")
        )
        connection.commit()


def _make_market(session: Session, code: str = "CRYPTO") -> UnderlyingMarket:
    market = UnderlyingMarket(code=code, display_name=code.title())
    session.add(market)
    session.flush()
    return market


def _make_product(session: Session, code: str = "SPOT") -> ProductType:
    product = ProductType(code=code, display_name=code.title())
    session.add(product)
    session.flush()
    return product


def _make_asset(session: Session, code: str) -> Asset:
    asset = Asset(code=code, display_name=code.title())
    session.add(asset)
    session.flush()
    return asset


def test_upgrade_creates_exactly_the_six_catalog_tables(auth_test_engine: Engine) -> None:
    inspector = inspect(auth_test_engine)
    catalog_tables = {name for name in inspector.get_table_names() if name.startswith("freyja2_")}
    assert catalog_tables == _CATALOG_TABLES


def test_0005_catalog_seeds_no_data() -> None:
    """POINT1-DB-001's own acceptance criterion ("no hay datos sembrados
    todavía") is pinned to its exact revision, not to a moving "head" — later
    revisions (POINT1-SEED-001) are expected to add seed data on top."""
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
        command.upgrade(cfg, "0005_catalog")

        engine = create_engine(temp_url)
        try:
            with engine.connect() as connection:
                for table in _CATALOG_TABLES:
                    count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    assert count == 0, f"{table} should be empty at revision 0005_catalog"
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


def test_downgrade_removes_only_the_catalog_tables_and_upgrade_restores_them() -> None:
    """Uses its own isolated temp database (never the shared auth_test_engine)
    so downgrading mid-suite cannot affect any other test. Targets the exact
    revision 0005_catalog (not relative "head"/"-1"), so this test keeps
    proving what POINT1-DB-001 itself delivered regardless of how many
    migrations get layered on top later."""
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
        command.upgrade(cfg, "0005_catalog")

        engine = create_engine(temp_url)
        try:
            inspector = inspect(engine)
            before = set(inspector.get_table_names())
            assert before >= _CATALOG_TABLES
            assert "auth_users" in before

            command.downgrade(cfg, "0004_remove_email_verification")
            inspector = inspect(engine)
            after_downgrade = set(inspector.get_table_names())
            assert not (after_downgrade & _CATALOG_TABLES)
            assert "auth_users" in after_downgrade

            command.upgrade(cfg, "0005_catalog")
            inspector = inspect(engine)
            after_upgrade = set(inspector.get_table_names())
            assert after_upgrade >= _CATALOG_TABLES
            assert "auth_users" in after_upgrade
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


def test_pair_instrument_can_be_created(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")

    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="BTC/USDT",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(instrument)
    db_session.flush()

    assert instrument.instrument_id is not None


def test_asset_underlying_instrument_can_be_created(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "BINARY_OPTION")
    underlying = _make_asset(db_session, "BTC")

    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="BTC",
        underlying_asset_id=underlying.id,
    )
    db_session.add(instrument)
    db_session.flush()

    assert instrument.instrument_id is not None


def test_instrument_underlying_instrument_can_be_created(db_session: Session) -> None:
    market = _make_market(db_session, "FOREX")
    spot = _make_product(db_session, "SPOT")
    binary = _make_product(db_session, "BINARY_OPTION")
    base = _make_asset(db_session, "EUR")
    quote = _make_asset(db_session, "USD")

    spot_instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=spot.id,
        canonical_symbol="EUR/USD",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(spot_instrument)
    db_session.flush()

    binary_instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=binary.id,
        canonical_symbol="EUR/USD",
        underlying_instrument_id=spot_instrument.instrument_id,
    )
    db_session.add(binary_instrument)
    db_session.flush()

    assert binary_instrument.underlying_instrument_id == spot_instrument.instrument_id


def test_instrument_cannot_mix_two_shapes(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")
    underlying = _make_asset(db_session, "ETH")

    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="INVALID/MIX",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
        underlying_asset_id=underlying.id,
    )
    db_session.add(instrument)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_instrument_base_asset_must_differ_from_quote_asset(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    same_asset = _make_asset(db_session, "BTC")

    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="BTC/BTC",
        base_asset_id=same_asset.id,
        quote_asset_id=same_asset.id,
    )
    db_session.add(instrument)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_instrument_cannot_reference_itself_as_underlying(db_session: Session) -> None:
    market = _make_market(db_session, "FOREX")
    product = _make_product(db_session, "BINARY_OPTION")
    fixed_id = uuid.uuid4()

    instrument = Instrument(
        instrument_id=fixed_id,
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="SELF/REF",
        underlying_instrument_id=fixed_id,
    )
    db_session.add(instrument)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_duplicate_market_product_symbol_combination_is_rejected(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")

    db_session.add(
        Instrument(
            underlying_market_id=market.id,
            product_type_id=product.id,
            canonical_symbol="BTC/USDT",
            base_asset_id=base.id,
            quote_asset_id=quote.id,
        )
    )
    db_session.flush()

    db_session.add(
        Instrument(
            underlying_market_id=market.id,
            product_type_id=product.id,
            canonical_symbol="BTC/USDT",
            base_asset_id=base.id,
            quote_asset_id=quote.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_instrument_requires_an_existing_market(db_session: Session) -> None:
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")

    instrument = Instrument(
        underlying_market_id=uuid.uuid4(),
        product_type_id=product.id,
        canonical_symbol="BTC/USDT",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(instrument)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_new_market_code_is_a_data_insertion_not_a_schema_change(db_session: Session) -> None:
    """MODELO EXISTENTE regla 8: adding a market/asset is a data insertion,
    never a schema/enum change — no code list is baked into the schema."""
    market = _make_market(db_session, "COMMODITY")
    assert market.code == "COMMODITY"


def test_instrument_supports_multiple_timeframes(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")
    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="BTC/USDT",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(instrument)
    db_session.flush()

    one_minute = Timeframe(code="1m", duration_seconds=60, display_name="1 minute")
    one_hour = Timeframe(code="1h", duration_seconds=3600, display_name="1 hour")
    db_session.add_all([one_minute, one_hour])
    db_session.flush()

    db_session.add_all(
        [
            InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=one_minute.id),
            InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=one_hour.id),
        ]
    )
    db_session.flush()

    linked = (
        db_session.query(InstrumentTimeframe)
        .filter(InstrumentTimeframe.instrument_id == instrument.instrument_id)
        .count()
    )
    assert linked == 2


_BLANK_OR_PADDED = ["", "   ", " X", "X "]


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_underlying_market_code_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(UnderlyingMarket(code=invalid_value, display_name="Crypto"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_underlying_market_display_name_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(UnderlyingMarket(code="CRYPTO", display_name=invalid_value))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_product_type_code_rejects_blank_or_padded(db_session: Session, invalid_value: str) -> None:
    db_session.add(ProductType(code=invalid_value, display_name="Spot"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_product_type_display_name_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(ProductType(code="SPOT", display_name=invalid_value))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_asset_code_rejects_blank_or_padded(db_session: Session, invalid_value: str) -> None:
    db_session.add(Asset(code=invalid_value, display_name="Bitcoin"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_asset_display_name_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(Asset(code="BTC", display_name=invalid_value))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_timeframe_code_rejects_blank_or_padded(db_session: Session, invalid_value: str) -> None:
    db_session.add(Timeframe(code=invalid_value, duration_seconds=60, display_name="1 minute"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_timeframe_display_name_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(Timeframe(code="1m", duration_seconds=60, display_name=invalid_value))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_instrument_canonical_symbol_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")

    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol=invalid_value,
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(instrument)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_timeframe_duration_rejects_zero(db_session: Session) -> None:
    db_session.add(Timeframe(code="0s", duration_seconds=0, display_name="Zero seconds"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_timeframe_duration_rejects_negative(db_session: Session) -> None:
    db_session.add(Timeframe(code="NEG", duration_seconds=-60, display_name="Negative"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_timeframe_duration_must_be_unique_across_codes(db_session: Session) -> None:
    """Decisión vinculante POINT1-DB-001: dos códigos distintos no pueden
    representar la misma duración canónica. Alias de proveedor pertenecerán a
    mappings de proveedor, no a Timeframe."""
    db_session.add(Timeframe(code="30s", duration_seconds=30, display_name="30 seconds"))
    db_session.flush()

    db_session.add(Timeframe(code="30s-alias", duration_seconds=30, display_name="Alias"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_timeframe_accepts_two_distinct_durations(db_session: Session) -> None:
    db_session.add(Timeframe(code="30s", duration_seconds=30, display_name="30 seconds"))
    db_session.add(Timeframe(code="45s", duration_seconds=45, display_name="45 seconds"))
    db_session.flush()

    count = db_session.query(Timeframe).filter(Timeframe.duration_seconds.in_([30, 45])).count()
    assert count == 2


def test_underlying_instrument_from_a_different_market_is_rejected(db_session: Session) -> None:
    """FK compuesta (underlying_market_id, underlying_instrument_id) ->
    (underlying_market_id, instrument_id): un instrumento subyacente debe
    pertenecer al mismo mercado que quien lo referencia, sin parsear
    canonical_symbol."""
    crypto = _make_market(db_session, "CRYPTO")
    forex = _make_market(db_session, "FOREX")
    spot = _make_product(db_session, "SPOT")
    binary = _make_product(db_session, "BINARY_OPTION")
    eur = _make_asset(db_session, "EUR")
    usd = _make_asset(db_session, "USD")

    forex_spot = Instrument(
        underlying_market_id=forex.id,
        product_type_id=spot.id,
        canonical_symbol="EUR/USD",
        base_asset_id=eur.id,
        quote_asset_id=usd.id,
    )
    db_session.add(forex_spot)
    db_session.flush()

    cross_market_binary = Instrument(
        underlying_market_id=crypto.id,
        product_type_id=binary.id,
        canonical_symbol="CROSS/MARKET",
        underlying_instrument_id=forex_spot.instrument_id,
    )
    db_session.add(cross_market_binary)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_postgres_does_not_validate_market_asset_semantics(db_session: Session) -> None:
    """POINT1-DB-001, corrección de auditoría independiente (2026-07-24): las
    FKs prueban existencia, las CHECK prueban forma, y la FK compuesta prueba
    que un instrumento subyacente pertenece al mismo mercado — pero
    PostgreSQL no deduce ni valida semántica de mercado/producto/activo desde
    un símbolo. Nada aquí impide que una fila declare BTC como base de un
    instrumento del mercado FOREX: qué combinaciones están autorizadas en v1
    lo prueba exclusivamente el seed canónico (0007_seed_catalog_v1), nunca
    un CHECK ni un enum de esquema."""
    forex = _make_market(db_session, "FOREX")
    product = _make_product(db_session, "SPOT")
    btc = _make_asset(db_session, "BTC")
    usdt = _make_asset(db_session, "USDT")

    semantically_wrong_but_physically_valid = Instrument(
        underlying_market_id=forex.id,
        product_type_id=product.id,
        canonical_symbol="BTC/USDT",
        base_asset_id=btc.id,
        quote_asset_id=usdt.id,
    )
    db_session.add(semantically_wrong_but_physically_valid)
    db_session.flush()

    assert semantically_wrong_but_physically_valid.instrument_id is not None


def test_duplicate_instrument_timeframe_link_is_rejected(db_session: Session) -> None:
    market = _make_market(db_session, "CRYPTO")
    product = _make_product(db_session, "SPOT")
    base = _make_asset(db_session, "BTC")
    quote = _make_asset(db_session, "USDT")
    instrument = Instrument(
        underlying_market_id=market.id,
        product_type_id=product.id,
        canonical_symbol="BTC/USDT",
        base_asset_id=base.id,
        quote_asset_id=quote.id,
    )
    db_session.add(instrument)
    timeframe = Timeframe(code="1m", duration_seconds=60, display_name="1 minute")
    db_session.add(timeframe)
    db_session.flush()

    db_session.add(
        InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=timeframe.id)
    )
    db_session.flush()

    db_session.add(
        InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=timeframe.id)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
