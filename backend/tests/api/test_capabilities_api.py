import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.capability import CapabilityStatus, TechnicalCapability
from freyja_backend.db.models.provider import DataSource, DataSourceType, Venue, VenueType

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"
CAPABILITIES_URL = "/api/v1/capabilities"

_TEST_USER_IDENTIFIER = "capability-reader@example.test"
_TEST_USER_PASSWORD = "correct-horse-battery-staple"

_TEST_VENUE_CODE = "TEST_CAP_API_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_CAP_API_MARKET_DATA"

_CAPABILITY_TABLES = (
    "freyja2_technical_capabilities",
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


def _seeded_timeframe_id(session: Session, code: str) -> uuid.UUID:
    row = session.execute(
        text("SELECT id FROM freyja2_timeframes WHERE code = :code"), {"code": code}
    ).scalar_one()
    return uuid.UUID(str(row))


@pytest.fixture(autouse=True)
def _truncate_capability_tables(auth_test_engine: Engine) -> Iterator[None]:
    yield
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(_CAPABILITY_TABLES)} RESTART IDENTITY CASCADE")
        )
        connection.commit()


def _make_venue(session: Session) -> Venue:
    venue = Venue(
        code=_TEST_VENUE_CODE, display_name="Test Cap API Exchange", venue_type=VenueType.EXCHANGE
    )
    session.add(venue)
    session.flush()
    return venue


def _make_data_source(session: Session) -> DataSource:
    source = DataSource(
        code=_TEST_SOURCE_CODE,
        display_name="Test Cap API Market Data",
        source_type=DataSourceType.MARKET_DATA,
    )
    session.add(source)
    session.flush()
    return source


def test_list_capabilities_requires_authentication(client: TestClient) -> None:
    response = client.get(CAPABILITIES_URL)
    assert response.status_code == 401


def test_all_five_capability_statuses_preserved_without_coercion(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            market_data_status=CapabilityStatus.SUPPORTED,
            signal_detection_status=CapabilityStatus.NOT_IMPLEMENTED,
            backtest_status=CapabilityStatus.NOT_EVALUATED,
            demo_execution_status=CapabilityStatus.SUPPORTED,
            real_execution_status=CapabilityStatus.NOT_SUPPORTED,
            settlement_status=CapabilityStatus.NOT_SUPPORTED,
            reason_unavailable="TEST fixture reason — not real supportability evidence",
        )
    )
    db_session.commit()

    response = client.get(CAPABILITIES_URL, params={"instrument_id": str(instrument_id)})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["market_data_status"] == "SUPPORTED"
    assert item["signal_detection_status"] == "NOT_IMPLEMENTED"
    assert item["backtest_status"] == "NOT_EVALUATED"
    assert item["demo_execution_status"] == "SUPPORTED"
    assert item["real_execution_status"] == "NOT_SUPPORTED"
    assert item["settlement_status"] == "NOT_SUPPORTED"
    assert item["provider"] == {
        "kind": "venue",
        "id": str(venue.id),
        "code": _TEST_VENUE_CODE,
        "display_name": venue.display_name,
    }


def test_data_source_capability_has_not_applicable_execution_and_settlement(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "5m")
    source = _make_data_source(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            data_source_id=source.id,
            market_data_status=CapabilityStatus.SUPPORTED,
            demo_execution_status=CapabilityStatus.NOT_APPLICABLE,
            real_execution_status=CapabilityStatus.NOT_APPLICABLE,
            settlement_status=CapabilityStatus.NOT_APPLICABLE,
        )
    )
    db_session.commit()

    response = client.get(CAPABILITIES_URL, params={"data_source_id": str(source.id)})
    item = response.json()["items"][0]
    assert item["demo_execution_status"] == "NOT_APPLICABLE"
    assert item["real_execution_status"] == "NOT_APPLICABLE"
    assert item["settlement_status"] == "NOT_APPLICABLE"
    assert item["provider"]["kind"] == "data_source"
    assert item["provider"]["code"] == _TEST_SOURCE_CODE


def test_current_query_excludes_closed_history_by_default(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "15m")
    venue = _make_venue(db_session)
    now = datetime.now(UTC)

    closed = TechnicalCapability(
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        market_data_status=CapabilityStatus.NOT_SUPPORTED,
        reason_unavailable="TEST fixture — historical row",
        effective_from=now - timedelta(days=10),
        effective_to=now - timedelta(days=1),
    )
    current = TechnicalCapability(
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        market_data_status=CapabilityStatus.SUPPORTED,
        effective_from=now - timedelta(days=1),
        effective_to=None,
    )
    db_session.add_all([closed, current])
    db_session.commit()

    default_response = client.get(
        CAPABILITIES_URL, params={"instrument_id": str(instrument_id), "venue_id": str(venue.id)}
    ).json()
    assert default_response["total"] == 1
    assert default_response["items"][0]["market_data_status"] == "SUPPORTED"

    history_response = client.get(
        CAPABILITIES_URL,
        params={
            "instrument_id": str(instrument_id),
            "venue_id": str(venue.id),
            "include_history": "true",
        },
    ).json()
    assert history_response["total"] == 2
    statuses = {item["market_data_status"] for item in history_response["items"]}
    assert statuses == {"SUPPORTED", "NOT_SUPPORTED"}


def test_future_effective_from_is_not_current_even_without_effective_to(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "ETH/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1h")
    venue = _make_venue(db_session)
    future = datetime.now(UTC) + timedelta(days=30)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            market_data_status=CapabilityStatus.SUPPORTED,
            effective_from=future,
            effective_to=None,
        )
    )
    db_session.commit()

    default_response = client.get(
        CAPABILITIES_URL, params={"instrument_id": str(instrument_id), "venue_id": str(venue.id)}
    ).json()
    assert default_response["total"] == 0

    history_response = client.get(
        CAPABILITIES_URL,
        params={
            "instrument_id": str(instrument_id),
            "venue_id": str(venue.id),
            "include_history": "true",
        },
    ).json()
    assert history_response["total"] == 1


def test_timeframe_id_filter_is_applied(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    one_minute_id = _seeded_timeframe_id(db_session, "1m")
    five_minute_id = _seeded_timeframe_id(db_session, "5m")
    venue = _make_venue(db_session)

    db_session.add_all(
        [
            TechnicalCapability(
                instrument_id=instrument_id,
                timeframe_id=one_minute_id,
                venue_id=venue.id,
                market_data_status=CapabilityStatus.SUPPORTED,
            ),
            TechnicalCapability(
                instrument_id=instrument_id,
                timeframe_id=five_minute_id,
                venue_id=venue.id,
                market_data_status=CapabilityStatus.NOT_EVALUATED,
            ),
        ]
    )
    db_session.commit()

    response = client.get(CAPABILITIES_URL, params={"timeframe_id": str(one_minute_id)})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["timeframe"]["id"] == str(one_minute_id)


def test_response_never_contains_execution_context_fields(
    client: TestClient, db_session: Session
) -> None:
    """Capabilities and ExecutionContext are separate concerns (POINT1-
    CAPABILITY-001) — a /capabilities response must never carry
    activation/eligibility/credential fields that belong only to
    ExecutionContext."""
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)
    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            market_data_status=CapabilityStatus.SUPPORTED,
        )
    )
    db_session.commit()

    response = client.get(CAPABILITIES_URL, params={"instrument_id": str(instrument_id)})
    item = response.json()["items"][0]

    forbidden_keys = (
        "activation_status",
        "credentials_status",
        "venue_permission_status",
        "regulatory_eligibility_status",
        "owner_authorization_status",
        "suspension_reasons",
        "jurisdiction",
        "client_classification",
        "account_key",
        "execution_environment",
    )
    for key in forbidden_keys:
        assert key not in item, f"capability response leaked ExecutionContext field {key!r}"


def test_response_never_contains_secret_shaped_fields(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)
    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            market_data_status=CapabilityStatus.SUPPORTED,
        )
    )
    db_session.commit()

    response = client.get(CAPABILITIES_URL, params={"instrument_id": str(instrument_id)})
    body = response.json()

    def _walk(value: object) -> Iterator[str]:
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from _walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from _walk(nested)

    forbidden = ("password", "secret", "token", "api_key", "apikey", "credential_value", "hash")
    for key in _walk(body):
        lowered = key.lower()
        for bad in forbidden:
            assert bad not in lowered, f"response field {key!r} looks secret-shaped"


def test_listing_capabilities_does_not_grow_query_count_with_more_rows(
    client: TestClient, db_session: Session, auth_test_engine: Engine
) -> None:
    _login(client, db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_ids = [
        _seeded_timeframe_id(db_session, code) for code in ("1m", "5m", "15m", "1h", "4h")
    ]
    venue = _make_venue(db_session)
    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_ids[0],
            venue_id=venue.id,
            market_data_status=CapabilityStatus.SUPPORTED,
        )
    )
    db_session.commit()

    def _count_queries() -> int:
        counter = {"n": 0}

        def _before_cursor_execute(*_args: object, **_kwargs: object) -> None:
            counter["n"] += 1

        event.listen(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        try:
            response = client.get(CAPABILITIES_URL, params={"limit": 50, "offset": 0})
            assert response.status_code == 200
        finally:
            event.remove(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        return counter["n"]

    before = _count_queries()

    db_session.add_all(
        [
            TechnicalCapability(
                instrument_id=instrument_id,
                timeframe_id=timeframe_id,
                venue_id=venue.id,
                market_data_status=CapabilityStatus.SUPPORTED,
            )
            for timeframe_id in timeframe_ids[1:]
        ]
    )
    db_session.commit()

    after = _count_queries()

    assert before == after, (
        "query count must stay constant as row count grows — a per-row query "
        "would be an N+1 regression"
    )


def test_get_capability_404_for_missing_id(client: TestClient, db_session: Session) -> None:
    _login(client, db_session)
    response = client.get(f"{CAPABILITIES_URL}/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_capability_422_for_invalid_uuid_filter(
    client: TestClient, db_session: Session
) -> None:
    _login(client, db_session)
    response = client.get(CAPABILITIES_URL, params={"instrument_id": "not-a-uuid"})
    assert response.status_code == 422
