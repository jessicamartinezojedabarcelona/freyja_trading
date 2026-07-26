import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    DataSourceInstrumentPurpose,
    DataSourceType,
    Venue,
    VenueInstrument,
    VenueType,
)

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"
VENUES_URL = "/api/v1/catalog/venues"
DATA_SOURCES_URL = "/api/v1/catalog/data-sources"

_TEST_USER_IDENTIFIER = "provider-reader@example.test"
_TEST_USER_PASSWORD = "correct-horse-battery-staple"

_TEST_VENUE_CODE = "TEST_API_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_API_MARKET_DATA"

_PROVIDER_TABLES = (
    "freyja2_venue_instruments",
    "freyja2_data_source_instruments",
    "freyja2_venues",
    "freyja2_data_sources",
)


def _login(client: TestClient, db_session: Session) -> None:
    auth_service.create_owner(
        db_session, identifier=_TEST_USER_IDENTIFIER, password=_TEST_USER_PASSWORD
    )
    db_session.commit()
    client.get(CSRF_URL)
    csrf = client.cookies.get("freyja_csrf")
    assert csrf is not None
    response = client.post(
        LOGIN_URL,
        json={"identifier": _TEST_USER_IDENTIFIER, "password": _TEST_USER_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def _seeded_instrument_id(
    session: Session, market_code: str, product_code: str, symbol: str
) -> uuid.UUID:
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


@pytest.fixture(autouse=True)
def _truncate_provider_tables(auth_test_engine: Engine) -> Iterator[None]:
    yield
    with auth_test_engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(_PROVIDER_TABLES)} RESTART IDENTITY CASCADE"))
        connection.commit()


def _make_venue(session: Session) -> Venue:
    venue = Venue(
        code=_TEST_VENUE_CODE, display_name="Test API Exchange", venue_type=VenueType.EXCHANGE
    )
    session.add(venue)
    session.flush()
    return venue


def _make_data_source(session: Session) -> DataSource:
    source = DataSource(
        code=_TEST_SOURCE_CODE,
        display_name="Test API Market Data",
        source_type=DataSourceType.MARKET_DATA,
    )
    session.add(source)
    session.flush()
    return source


def test_list_venues_requires_authentication(client: TestClient) -> None:
    response = client.get(VENUES_URL)
    assert response.status_code == 401


def test_list_venues_and_data_sources(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    _make_venue(db_session)
    _make_data_source(db_session)
    db_session.commit()

    venues = client.get(VENUES_URL).json()
    assert any(v["code"] == _TEST_VENUE_CODE for v in venues["items"])

    data_sources = client.get(DATA_SOURCES_URL).json()
    assert any(ds["code"] == _TEST_SOURCE_CODE for ds in data_sources["items"])


def test_mappings_separate_venue_and_data_source_and_never_confuse_provider_symbol(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    venue = _make_venue(db_session)
    source = _make_data_source(db_session)

    db_session.add(
        VenueInstrument(venue_id=venue.id, instrument_id=instrument_id, provider_symbol="XBTUSDT")
    )
    db_session.add(
        DataSourceInstrument(
            data_source_id=source.id,
            instrument_id=instrument_id,
            provider_symbol="BTCUSDT.SETTLE",
            purpose=DataSourceInstrumentPurpose.SETTLEMENT,
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/catalog/instruments/{instrument_id}/mappings")
    assert response.status_code == 200
    body = response.json()

    assert len(body["venue_instruments"]) == 1
    assert len(body["data_source_instruments"]) == 1

    venue_mapping = body["venue_instruments"][0]
    assert venue_mapping["provider_symbol"] == "XBTUSDT"
    assert venue_mapping["provider_symbol"] != "BTC/USDT"  # never the canonical symbol
    assert venue_mapping["venue"]["code"] == _TEST_VENUE_CODE

    ds_mapping = body["data_source_instruments"][0]
    assert ds_mapping["provider_symbol"] == "BTCUSDT.SETTLE"
    assert ds_mapping["purpose"] == "SETTLEMENT"
    assert ds_mapping["data_source"]["code"] == _TEST_SOURCE_CODE


def test_mappings_404_for_missing_instrument(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    response = client.get(f"/api/v1/catalog/instruments/{uuid.uuid4()}/mappings")
    assert response.status_code == 404


def test_mappings_empty_for_instrument_with_no_mappings(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "ETH/USDT")
    response = client.get(f"/api/v1/catalog/instruments/{instrument_id}/mappings")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "instrument_id": str(instrument_id),
        "venue_instruments": [],
        "data_source_instruments": [],
    }
