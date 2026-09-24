"""GET /catalog/instruments?has_market_data=... (MARKET-DATA-EXPLORER-001).

The explorer must offer only instruments whose candles can actually be served.
"Can be served" is defined by the catalog: an ACTIVE data source publishes the
instrument for ANALYSIS through an ACTIVE mapping. Fictitious instruments are
added next to whatever the catalog already holds, and removed afterwards.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.catalog import Asset, Instrument, InstrumentTimeframe
from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    DataSourceInstrumentPurpose,
    DataSourceType,
)

INSTRUMENTS_URL = "/api/v1/catalog/instruments"
_USER = "hmd-reader@example.test"
_PASSWORD = "correct-horse-battery-staple"
_QUOTE = "TEST_HMD_Q"

# One fictitious instrument per case, named by what makes it (un)available.
COVERED = "BTC/TEST_HMD_Q"
SETTLEMENT_ONLY = "ETH/TEST_HMD_Q"
INACTIVE_MAPPING = "SOL/TEST_HMD_Q"
INACTIVE_SOURCE = "XRP/TEST_HMD_Q"
NO_MAPPING = "EUR/TEST_HMD_Q"
ALL = {COVERED, SETTLEMENT_ONLY, INACTIVE_MAPPING, INACTIVE_SOURCE, NO_MAPPING}


def _login(client: TestClient, session: Session) -> None:
    auth_service.create_owner(session, identifier=_USER, password=_PASSWORD)
    session.commit()
    client.get("/api/v1/auth/csrf")
    csrf = client.cookies.get("freyja_csrf")
    assert csrf is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": _USER, "password": _PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def _seeded_id(session: Session, table: str, code: str) -> uuid.UUID:
    return uuid.UUID(
        str(
            session.execute(
                text(f"SELECT id FROM {table} WHERE code = :c"), {"c": code}
            ).scalar_one()
        )
    )


@pytest.fixture
def five_instruments(db_session: Session) -> Iterator[None]:
    market = _seeded_id(db_session, "freyja2_underlying_markets", "CRYPTO")
    product = _seeded_id(db_session, "freyja2_product_types", "SPOT")
    timeframe = _seeded_id(db_session, "freyja2_timeframes", "1m")
    quote = Asset(code=_QUOTE, display_name="Test HMD quote")
    db_session.add(quote)
    db_session.flush()

    created: dict[str, Instrument] = {}
    for symbol in sorted(ALL):
        base = symbol.split("/")[0]
        instrument = Instrument(
            underlying_market_id=market,
            product_type_id=product,
            canonical_symbol=symbol,
            base_asset_id=_seeded_id(db_session, "freyja2_assets", base),
            quote_asset_id=quote.id,
        )
        db_session.add(instrument)
        db_session.flush()
        db_session.add(
            InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=timeframe)
        )
        created[symbol] = instrument

    active = DataSource(
        code="TEST_HMD_ACTIVE", display_name="Active", source_type=DataSourceType.MARKET_DATA
    )
    inactive = DataSource(
        code="TEST_HMD_INACTIVE",
        display_name="Inactive",
        source_type=DataSourceType.MARKET_DATA,
        is_active=False,
    )
    db_session.add_all([active, inactive])
    db_session.flush()

    def mapping(
        source: DataSource, symbol: str, purpose: DataSourceInstrumentPurpose, *, is_active: bool
    ) -> DataSourceInstrument:
        return DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=created[symbol].instrument_id,
            provider_symbol=symbol.replace("/", ""),
            purpose=purpose,
            is_active=is_active,
        )

    analysis = DataSourceInstrumentPurpose.ANALYSIS
    db_session.add_all(
        [
            mapping(active, COVERED, analysis, is_active=True),
            mapping(
                active, SETTLEMENT_ONLY, DataSourceInstrumentPurpose.SETTLEMENT, is_active=True
            ),
            mapping(active, INACTIVE_MAPPING, analysis, is_active=False),
            mapping(inactive, INACTIVE_SOURCE, analysis, is_active=True),
        ]
    )
    db_session.commit()

    yield

    ids = [i.instrument_id for i in created.values()]
    with db_session.bind.connect() as connection:  # type: ignore[union-attr]
        for statement, params in (
            (
                "DELETE FROM freyja2_data_source_instruments WHERE instrument_id = ANY(:ids)",
                {"ids": ids},
            ),
            ("DELETE FROM freyja2_data_sources WHERE code LIKE 'TEST_HMD_%'", {}),
            (
                "DELETE FROM freyja2_instrument_timeframes WHERE instrument_id = ANY(:ids)",
                {"ids": ids},
            ),
            ("DELETE FROM freyja2_instruments WHERE instrument_id = ANY(:ids)", {"ids": ids}),
            ("DELETE FROM freyja2_assets WHERE code = :code", {"code": _QUOTE}),
        ):
            connection.execute(text(statement), params)
        connection.commit()


def _symbols(client: TestClient, **params: Any) -> set[str]:
    response = client.get(INSTRUMENTS_URL, params={"limit": 200, **params})
    assert response.status_code == 200, response.text
    return {item["canonical_symbol"] for item in response.json()["items"]}


@pytest.mark.usefixtures("five_instruments")
def test_true_keeps_only_instruments_an_active_source_publishes_for_analysis(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)

    served = _symbols(client, has_market_data="true") & ALL

    # SETTLEMENT-only, a deactivated mapping, a deactivated source and no mapping
    # at all each leave an instrument out: none of them can serve candles.
    assert served == {COVERED}


@pytest.mark.usefixtures("five_instruments")
def test_false_is_the_exact_complement(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)

    unserved = _symbols(client, has_market_data="false") & ALL

    assert unserved == ALL - {COVERED}


@pytest.mark.usefixtures("five_instruments")
def test_omitting_the_filter_changes_nothing(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)

    everything = _symbols(client)
    assert everything >= ALL
    assert (
        _symbols(client, has_market_data="true") | _symbols(client, has_market_data="false")
        == everything
    )


@pytest.mark.usefixtures("five_instruments")
def test_it_combines_with_the_other_filters(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)

    assert _symbols(client, has_market_data="true", market_code="CRYPTO") & ALL == {COVERED}
    assert _symbols(client, has_market_data="true", market_code="FOREX") & ALL == set()
    assert _symbols(client, has_market_data="true", symbol=COVERED) == {COVERED}
    assert _symbols(client, has_market_data="true", symbol=NO_MAPPING) == set()


@pytest.mark.usefixtures("five_instruments")
def test_total_counts_the_filtered_set(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)

    everything = client.get(INSTRUMENTS_URL, params={"limit": 200}).json()["total"]
    served = client.get(INSTRUMENTS_URL, params={"limit": 200, "has_market_data": "true"}).json()
    unserved = client.get(INSTRUMENTS_URL, params={"limit": 200, "has_market_data": "false"}).json()

    assert served["total"] == len(served["items"])
    assert served["total"] + unserved["total"] == everything


def test_a_value_that_is_not_a_boolean_is_rejected(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    assert client.get(INSTRUMENTS_URL, params={"has_market_data": "maybe"}).status_code == 422


def test_it_still_requires_a_session(client: TestClient) -> None:
    assert client.get(INSTRUMENTS_URL, params={"has_market_data": "true"}).status_code == 401
