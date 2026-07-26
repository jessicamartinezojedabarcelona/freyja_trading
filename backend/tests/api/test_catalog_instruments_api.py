import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.catalog import Asset, Instrument, InstrumentTimeframe

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"
INSTRUMENTS_URL = "/api/v1/catalog/instruments"

_TEST_USER_IDENTIFIER = "catalog-reader@example.test"
_TEST_USER_PASSWORD = "correct-horse-battery-staple"

# Distinctive, unambiguously fictitious fixture data — inserted alongside the
# seeded v1 catalog, never truncating it (see tests/integration/test_catalog_*
# for the same convention).
_TEST_QUOTE_ASSET_CODE = "TEST_API_QUOTE"
_TEST_SYMBOL = "BTC/TEST_API_QUOTE"


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


def _seeded_id(session: Session, table: str, code: str) -> uuid.UUID:
    row = session.execute(
        text(f"SELECT id FROM {table} WHERE code = :code"), {"code": code}
    ).scalar_one()
    return uuid.UUID(str(row))


@pytest.fixture
def _extra_test_instrument(db_session: Session) -> Iterator[uuid.UUID]:
    """Inserts one additional, distinctively-coded instrument alongside the
    seeded v1 catalog — proving test #1 (a validly-inserted instrument
    appears via the API without any code change) without ever truncating the
    canonical seed."""
    market_id = _seeded_id(db_session, "freyja2_underlying_markets", "CRYPTO")
    product_type_id = _seeded_id(db_session, "freyja2_product_types", "SPOT")
    base_asset_id = _seeded_id(db_session, "freyja2_assets", "BTC")

    quote_asset = Asset(code=_TEST_QUOTE_ASSET_CODE, display_name="Test API Quote")
    db_session.add(quote_asset)
    db_session.flush()

    instrument = Instrument(
        underlying_market_id=market_id,
        product_type_id=product_type_id,
        canonical_symbol=_TEST_SYMBOL,
        base_asset_id=base_asset_id,
        quote_asset_id=quote_asset.id,
    )
    db_session.add(instrument)
    db_session.flush()

    timeframe_id = _seeded_id(db_session, "freyja2_timeframes", "1m")
    db_session.add(
        InstrumentTimeframe(instrument_id=instrument.instrument_id, timeframe_id=timeframe_id)
    )
    db_session.commit()

    yield instrument.instrument_id

    with db_session.bind.connect() as connection:  # type: ignore[union-attr]
        connection.execute(
            text("DELETE FROM freyja2_instrument_timeframes WHERE instrument_id = :id"),
            {"id": instrument.instrument_id},
        )
        connection.execute(
            text("DELETE FROM freyja2_instruments WHERE instrument_id = :id"),
            {"id": instrument.instrument_id},
        )
        connection.execute(
            text("DELETE FROM freyja2_assets WHERE id = :id"), {"id": quote_asset.id}
        )
        connection.commit()


def test_list_instruments_requires_authentication(client: TestClient) -> None:
    response = client.get(INSTRUMENTS_URL)
    assert response.status_code == 401


def test_new_instrument_appears_via_api_without_code_change(
    client: TestClient, db_session: Session, _extra_test_instrument: uuid.UUID
) -> None:
    _login(client, db_session)
    response = client.get(INSTRUMENTS_URL, params={"symbol": _TEST_SYMBOL})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["instrument_id"] == str(_extra_test_instrument)
    # Market/product/symbol/timeframes come straight from PostgreSQL — never
    # a hardcoded/legacy list.
    assert item["market"]["code"] == "CRYPTO"
    assert item["product_type"]["code"] == "SPOT"
    assert item["canonical_symbol"] == _TEST_SYMBOL
    assert item["base_asset"]["code"] == "BTC"
    assert item["quote_asset"]["code"] == _TEST_QUOTE_ASSET_CODE
    assert item["underlying_asset"] is None
    assert [tf["code"] for tf in item["timeframes"]] == ["1m"]


def test_filters_by_market_product_symbol_timeframe(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)

    response = client.get(
        INSTRUMENTS_URL,
        params={"market_code": "FOREX", "product_type_code": "SPOT", "symbol": "EUR/USD"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_symbol"] == "EUR/USD"

    response = client.get(INSTRUMENTS_URL, params={"timeframe_code": "4h"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10  # all 10 seeded v1 instruments support every timeframe


def test_empty_result_is_honest_not_a_fallback(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    response = client.get(INSTRUMENTS_URL, params={"symbol": "DOES_NOT_EXIST_ANYWHERE"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_get_instrument_by_id(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    response = client.get(f"{INSTRUMENTS_URL}/{instrument_id}")
    assert response.status_code == 200
    assert response.json()["canonical_symbol"] == "BTC/USDT"


def test_get_instrument_404_for_missing_id(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    response = client.get(f"{INSTRUMENTS_URL}/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_instrument_422_for_invalid_uuid(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    response = client.get(f"{INSTRUMENTS_URL}/not-a-uuid")
    assert response.status_code == 422


def test_pagination_order_is_stable_across_pages(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    first_page = client.get(INSTRUMENTS_URL, params={"limit": 3, "offset": 0}).json()
    second_page = client.get(INSTRUMENTS_URL, params={"limit": 3, "offset": 3}).json()
    first_ids = {item["instrument_id"] for item in first_page["items"]}
    second_ids = {item["instrument_id"] for item in second_page["items"]}
    assert first_ids.isdisjoint(second_ids)

    repeat_first_page = client.get(INSTRUMENTS_URL, params={"limit": 3, "offset": 0}).json()
    assert [item["instrument_id"] for item in first_page["items"]] == [
        item["instrument_id"] for item in repeat_first_page["items"]
    ]


def test_listing_instruments_does_not_grow_query_count_with_more_rows(
    client: TestClient, db_session: Session, auth_test_engine: Engine
) -> None:
    _login(client, db_session)

    query_counts: list[int] = []

    def _count_queries() -> int:
        counter = {"n": 0}

        def _before_cursor_execute(*_args: object, **_kwargs: object) -> None:
            counter["n"] += 1

        event.listen(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        try:
            response = client.get(INSTRUMENTS_URL, params={"limit": 50, "offset": 0})
            assert response.status_code == 200
        finally:
            event.remove(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        return counter["n"]

    query_counts.append(_count_queries())

    market_id = _seeded_id(db_session, "freyja2_underlying_markets", "CRYPTO")
    product_type_id = _seeded_id(db_session, "freyja2_product_types", "SPOT")
    base_asset_id = _seeded_id(db_session, "freyja2_assets", "BTC")
    for i in range(3):
        quote_asset = Asset(code=f"TEST_NPLUS1_{i}", display_name=f"Test N+1 {i}")
        db_session.add(quote_asset)
        db_session.flush()
        db_session.add(
            Instrument(
                underlying_market_id=market_id,
                product_type_id=product_type_id,
                canonical_symbol=f"BTC/TEST_NPLUS1_{i}",
                base_asset_id=base_asset_id,
                quote_asset_id=quote_asset.id,
            )
        )
    db_session.commit()

    query_counts.append(_count_queries())

    assert query_counts[0] == query_counts[1], (
        "query count must stay constant as row count grows — a per-row query "
        "would be an N+1 regression"
    )
