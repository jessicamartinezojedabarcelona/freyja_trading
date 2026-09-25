"""GET /api/v1/market-data/candles against real PostgreSQL.

Candles are stored through the real path (adapter -> sync service -> database)
and read back over HTTP with a real session. The clock is fixed so freshness is
deterministic; only the external provider is simulated.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from freyja_backend.api.deps import get_clock
from freyja_backend.application import auth_service, market_data_service
from freyja_backend.db import deps as db_deps
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    KrakenRestConfig,
    KrakenSpotRestClient,
)
from freyja_backend.main import create_app
from tests.market_data_support import (
    BTC,
    ETH,
    M1,
    M5,
    NOW,
    Rows,
    SyntheticExchange,
    SyntheticKraken,
    at,
)

NOW_Z = "2026-09-24T12:07:30Z"
URL = "/api/v1/market-data/candles"
SOURCE = "BINANCE"
_USER = "reader@freyja-test.dev"
_PASSWORD = "correct-horse-battery-staple"


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def market_client(
    auth_test_engine: Engine, market_data_engine: Engine, clean_market_data: None, clock: FixedClock
) -> Iterator[TestClient]:
    del clean_market_data
    with market_data_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE auth_sessions, auth_rate_limit_events, "
                "auth_password_reset_tokens, auth_users CASCADE"
            )
        )
    # The API layer talks to this module's own database, and goes back to the
    # shared one afterwards so no other test notices.
    db_deps.set_engine_override(market_data_engine)
    try:
        app: FastAPI = create_app()
        app.dependency_overrides[get_clock] = lambda: clock
        with TestClient(app, base_url="http://localhost") as test_client:
            yield test_client
    finally:
        db_deps.set_engine_override(auth_test_engine)


def login(client: TestClient, engine: Engine) -> None:
    with create_session_factory(engine)() as session:
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


@pytest.fixture
def api(market_client: TestClient, market_data_engine: Engine) -> TestClient:
    login(market_client, market_data_engine)
    return market_client


def instrument_id(
    engine: Engine, symbol: str, market: str = "CRYPTO", product: str = "SPOT"
) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            text(
                "SELECT i.instrument_id FROM freyja2_instruments i "
                "JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id "
                "JOIN freyja2_product_types p ON p.id = i.product_type_id "
                "WHERE m.code = :m AND p.code = :p AND i.canonical_symbol = :s"
            ),
            {"m": market, "p": product, "s": symbol},
        ).scalar_one()
    return str(value)


def store(
    engine: Engine,
    exchange: SyntheticExchange,
    *,
    instrument: InstrumentRef = BTC,
    timeframe: Timeframe = M1,
    limit: int = 6,
    now: datetime = NOW,
) -> market_data_service.SyncResult:
    """Ingest through the real adapter and service, exactly as the CLI does."""
    client = BinanceSpotRestClient(
        BinanceRestConfig(max_attempts=1),
        transport=httpx2.MockTransport(exchange),
        clock=lambda: now,
        sleep=lambda _seconds: None,
    )
    try:
        with create_session_factory(engine)() as session:
            result = market_data_service.sync_candles(
                session,
                client,
                source_code=SOURCE,
                instrument=instrument,
                timeframe=timeframe,
                limit=limit,
            )
            session.commit()
            return result
    finally:
        client.close()


def read(api: TestClient, engine: Engine, **params: Any) -> dict[str, Any]:
    query = {
        "instrument_id": instrument_id(engine, "BTC/USDT"),
        "data_source_code": SOURCE,
        **params,
    }
    response = api.get(URL, params=query)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def opens(body: dict[str, Any]) -> list[str]:
    return [str(c["open_time"]) for c in body["candles"]]


def z(hour: int, minute: int) -> str:
    return at(hour, minute).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- access -------------------------------------------------------------------------------------


def test_requires_a_session(market_client: TestClient, market_data_engine: Engine) -> None:
    response = market_client.get(
        URL,
        params={
            "instrument_id": instrument_id(market_data_engine, "BTC/USDT"),
            "data_source_code": SOURCE,
        },
    )
    assert response.status_code == 401


# -- reading what is stored ---------------------------------------------------------------------


def test_returns_the_latest_closed_candles_oldest_first_with_source_and_freshness(
    api: TestClient, market_data_engine: Engine
) -> None:
    store(market_data_engine, SyntheticExchange())  # limit=6 -> 12:02..12:07, 12:07 still open

    body = read(api, market_data_engine)

    assert body["data_source_code"] == "BINANCE"
    assert body["timeframe_code"] == "1m"  # the standard period when none is given
    assert body["instrument_id"] == instrument_id(market_data_engine, "BTC/USDT")
    assert opens(body) == [z(12, m) for m in (2, 3, 4, 5, 6)]
    assert body["quality"] == "OK"
    assert body["issues"] == [] and body["gaps"] == []
    assert body["has_more"] is False and body["next_start"] is None
    assert body["freshness"] == {
        "status": "FRESH",
        "checked_at": NOW_Z,
        "latest_open_time": z(12, 6),
        "latest_close_time": z(12, 7),
        "latest_received_at": NOW_Z,
    }
    provider = body["provider"]
    assert isinstance(provider, dict)
    assert provider["last_status"] == "OK" and provider["consecutive_failures"] == 0
    assert provider["last_success_at"] == NOW_Z


def test_prices_are_exact_decimal_strings(api: TestClient, market_data_engine: Engine) -> None:
    store(market_data_engine, SyntheticExchange())

    body = read(api, market_data_engine, limit=1)

    (candle,) = body["candles"]
    base = SyntheticExchange.price(int(at(12, 6).timestamp() * 1000), 60_000)
    assert candle["open"] == f"{base}.1"  # a string, never a float; no trailing zeros
    assert candle["high"] == str(base + 2)
    assert candle["low"] == str(base - 1)
    assert candle["close"] == str(base + 1)
    assert candle["volume"] == "10.5"
    assert candle["quality"] == "OK"
    assert candle["open_time"] == z(12, 6) and candle["close_time"] == z(12, 7)


def test_limit_returns_the_newest_candles(api: TestClient, market_data_engine: Engine) -> None:
    store(market_data_engine, SyntheticExchange())
    assert opens(read(api, market_data_engine, limit=2)) == [z(12, 5), z(12, 6)]


def test_reading_forward_pages_with_next_start(api: TestClient, market_data_engine: Engine) -> None:
    store(market_data_engine, SyntheticExchange())

    first = read(api, market_data_engine, start=z(12, 3), limit=2)
    assert opens(first) == [z(12, 3), z(12, 4)]
    assert first["has_more"] is True and first["next_start"] == z(12, 5)
    assert first["quality"] == "OK"  # a page that continues is not "incomplete"

    second = read(api, market_data_engine, start=first["next_start"], limit=2)
    assert opens(second) == [z(12, 5), z(12, 6)]
    assert second["has_more"] is False and second["next_start"] is None
    assert second["quality"] == "OK"


def test_end_excludes_candles_that_open_at_or_after_it(
    api: TestClient, market_data_engine: Engine
) -> None:
    store(market_data_engine, SyntheticExchange())
    assert opens(read(api, market_data_engine, end=z(12, 5))) == [z(12, m) for m in (2, 3, 4)]
    assert opens(read(api, market_data_engine, start=z(12, 3), end=z(12, 5))) == [
        z(12, 3),
        z(12, 4),
    ]


def test_time_zone_offsets_are_understood(api: TestClient, market_data_engine: Engine) -> None:
    store(market_data_engine, SyntheticExchange())
    body = read(api, market_data_engine, start="2026-09-24T14:04:00+02:00", limit=1)
    assert opens(body) == [z(12, 4)]


# -- series never mix ---------------------------------------------------------------------------


def test_instruments_and_timeframes_are_never_mixed(
    api: TestClient, market_data_engine: Engine
) -> None:
    exchange = SyntheticExchange()
    store(market_data_engine, exchange, instrument=BTC, timeframe=M1)
    store(market_data_engine, exchange, instrument=BTC, timeframe=M5, limit=4)
    store(market_data_engine, exchange, instrument=ETH, timeframe=M1, limit=3)

    btc_1m = read(api, market_data_engine)
    btc_5m = read(api, market_data_engine, timeframe_code="5m")
    eth_1m = read(
        api, market_data_engine, instrument_id=instrument_id(market_data_engine, "ETH/USDT")
    )

    assert len(btc_1m["candles"]) == 5
    assert opens(btc_5m) == [z(11, 50), z(11, 55), z(12, 0)]  # limit=4 -> 12:05 still open
    assert opens(eth_1m) == [z(12, 5), z(12, 6)]  # limit=3 -> 12:05..12:07, 12:07 open
    assert btc_5m["timeframe_code"] == "5m"


def test_two_accounts_see_the_same_common_market_data(
    api: TestClient, market_data_engine: Engine
) -> None:
    store(market_data_engine, SyntheticExchange())
    mine = read(api, market_data_engine)

    other_app = create_app()
    other_app.dependency_overrides[get_clock] = lambda: FixedClock(NOW)
    with TestClient(other_app, base_url="http://localhost") as other:
        with create_session_factory(market_data_engine)() as session:
            auth_service.create_owner(
                session, identifier="second@freyja-test.dev", password="another-long-password-1"
            )
            session.commit()
        other.get("/api/v1/auth/csrf")
        csrf = other.cookies.get("freyja_csrf")
        assert csrf is not None
        assert (
            other.post(
                "/api/v1/auth/login",
                json={
                    "identifier": "second@freyja-test.dev",
                    "password": "another-long-password-1",
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        theirs = read(other, market_data_engine)

    assert theirs == mine


# -- quality: nothing, old, holes, failing provider ---------------------------------------------


def test_a_series_with_nothing_stored_says_so_and_is_not_zero(
    api: TestClient, market_data_engine: Engine
) -> None:
    body = read(api, market_data_engine)

    assert body["candles"] == []
    assert body["quality"] == "UNAVAILABLE"
    assert [i["code"] for i in body["issues"]] == ["NO_DATA"]
    assert body["freshness"]["status"] == "NO_DATA"
    assert body["freshness"]["latest_open_time"] is None
    assert body["provider"] is None


def test_old_data_is_never_presented_as_current(
    api: TestClient, market_data_engine: Engine, clock: FixedClock
) -> None:
    store(market_data_engine, SyntheticExchange())
    clock.now = NOW + timedelta(hours=1)

    body = read(api, market_data_engine)

    assert body["freshness"]["status"] == "STALE"
    assert body["freshness"]["latest_open_time"] == z(12, 6)
    assert body["quality"] == "DEGRADED"
    assert "STALE" in [i["code"] for i in body["issues"]]
    assert len(body["candles"]) == 5  # shown, but flagged


def test_a_historical_window_of_stale_data_reports_freshness_without_calling_it_incomplete(
    api: TestClient, market_data_engine: Engine, clock: FixedClock
) -> None:
    store(market_data_engine, SyntheticExchange())
    clock.now = NOW + timedelta(hours=1)

    body = read(api, market_data_engine, start=z(12, 3), end=z(12, 6))

    assert opens(body) == [z(12, 3), z(12, 4), z(12, 5)]
    assert body["quality"] == "OK"  # that window is complete
    assert body["freshness"]["status"] == "STALE"


def test_holes_are_reported_as_gaps(api: TestClient, market_data_engine: Engine) -> None:
    missing = int(at(12, 4).timestamp() * 1000)

    def drop(rows: Rows) -> Rows:
        return [r for r in rows if r[0] != missing]

    store(market_data_engine, SyntheticExchange(mutate=drop))

    body = read(api, market_data_engine)

    assert opens(body) == [z(12, 2), z(12, 3), z(12, 5), z(12, 6)]
    assert body["gaps"] == [{"after_open_time": z(12, 3), "missing": 1}]
    assert body["quality"] == "DEGRADED"
    assert "GAP" in [i["code"] for i in body["issues"]]


def test_a_failing_provider_is_visible_next_to_the_data_it_could_not_refresh(
    api: TestClient, market_data_engine: Engine
) -> None:
    store(market_data_engine, SyntheticExchange())
    later = NOW + timedelta(minutes=1)
    failed = store(
        market_data_engine,
        SyntheticExchange(now=later, failing_calls=frozenset({1})),
        now=later,
    )
    assert failed.quality.value == "UNAVAILABLE"

    body = read(api, market_data_engine)

    provider = body["provider"]
    assert isinstance(provider, dict)
    assert provider["last_status"] == "UNAVAILABLE"
    assert provider["consecutive_failures"] == 1
    assert provider["last_issue_codes"] == ["PROVIDER_ERROR"]
    assert provider["last_success_at"] == NOW_Z
    assert body["quality"] == "DEGRADED"
    assert "PROVIDER_FAILING" in [i["code"] for i in body["issues"]]
    assert len(body["candles"]) == 5  # the stored ones are still served


# -- rejected requests --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "status_code", "detail"),
    [
        ({"instrument_id": str(uuid.uuid4())}, 404, "Instrumento no encontrado."),
        ({"data_source_code": "NOWHERE"}, 404, "Fuente de datos no encontrada."),
        ({"timeframe_code": "30s"}, 422, "Temporalidad no válida."),
        ({"start": "2026-09-24T12:00:00"}, 422, "start debe incluir zona horaria"),
        ({"end": "2026-09-24T12:00:00"}, 422, "end debe incluir zona horaria"),
        (
            {"start": "2026-09-24T12:05:00Z", "end": "2026-09-24T12:05:00Z"},
            422,
            "start debe ser anterior a end.",
        ),
        (
            {"start": "2026-09-24T12:06:00Z", "end": "2026-09-24T12:05:00Z"},
            422,
            "start debe ser anterior a end.",
        ),
    ],
)
def test_invalid_requests_are_rejected(
    api: TestClient,
    market_data_engine: Engine,
    overrides: dict[str, str],
    status_code: int,
    detail: str,
) -> None:
    params = {
        "instrument_id": instrument_id(market_data_engine, "BTC/USDT"),
        "data_source_code": SOURCE,
        **overrides,
    }
    response = api.get(URL, params=params)
    assert response.status_code == status_code
    assert detail in str(response.json()["detail"])


def test_a_source_that_does_not_publish_the_instrument_is_not_found(
    api: TestClient, market_data_engine: Engine
) -> None:
    forex = instrument_id(market_data_engine, "EUR/USD", market="FOREX")
    response = api.get(URL, params={"instrument_id": forex, "data_source_code": SOURCE})
    assert response.status_code == 404
    assert response.json()["detail"] == "Esta fuente no publica datos para este instrumento."


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": "many"},
        {"instrument_id": "not-a-uuid"},
        {"start": "yesterday"},
    ],
)
def test_malformed_parameters_are_rejected_by_validation(
    api: TestClient, market_data_engine: Engine, params: dict[str, Any]
) -> None:
    query: dict[str, Any] = {
        "instrument_id": instrument_id(market_data_engine, "BTC/USDT"),
        "data_source_code": SOURCE,
        **params,
    }
    assert api.get(URL, params=query).status_code == 422


def test_required_parameters_are_required(api: TestClient, market_data_engine: Engine) -> None:
    assert api.get(URL, params={"data_source_code": SOURCE}).status_code == 422
    assert (
        api.get(
            URL, params={"instrument_id": instrument_id(market_data_engine, "BTC/USDT")}
        ).status_code
        == 422
    )


def test_the_endpoint_is_read_only(api: TestClient, market_data_engine: Engine) -> None:
    query = {
        "instrument_id": instrument_id(market_data_engine, "BTC/USDT"),
        "data_source_code": SOURCE,
    }
    for method in ("post", "put", "patch", "delete"):
        assert getattr(api, method)(URL, params=query).status_code == 405


# -- Kraken as a second source (MARKET-DATA-KRAKEN-REST-001) ----------------------------------


def store_from_kraken(
    engine: Engine, kraken: SyntheticKraken, *, limit: int = 3, now: datetime = NOW
) -> market_data_service.SyncResult:
    """Ingest through the real Kraken adapter and the same service, exactly as the CLI does."""
    client = KrakenSpotRestClient(
        KrakenRestConfig(max_attempts=1, min_request_interval_seconds=0.0),
        transport=httpx2.MockTransport(kraken),
        clock=lambda: now,
        sleep=lambda _seconds: None,
    )
    try:
        with create_session_factory(engine)() as session:
            result = market_data_service.sync_candles(
                session,
                client,
                source_code="KRAKEN",
                instrument=BTC,
                timeframe=M1,
                limit=limit,
            )
            session.commit()
            return result
    finally:
        client.close()


def test_the_same_instrument_and_period_from_two_sources_are_never_mixed(
    api: TestClient, market_data_engine: Engine
) -> None:
    store(market_data_engine, SyntheticExchange(), limit=6)  # Binance: 5 closed candles
    store_from_kraken(market_data_engine, SyntheticKraken(), limit=3)  # Kraken: 3

    binance = read(api, market_data_engine, data_source_code="BINANCE")
    kraken = read(api, market_data_engine, data_source_code="KRAKEN")

    assert (binance["data_source_code"], len(binance["candles"])) == ("BINANCE", 5)
    assert (kraken["data_source_code"], len(kraken["candles"])) == ("KRAKEN", 3)
    # Kraken's three are the newest three; nothing was borrowed from Binance's series.
    assert opens(kraken) == opens(binance)[-3:]


def test_a_source_with_no_candles_yet_says_so_instead_of_failing(
    api: TestClient, market_data_engine: Engine
) -> None:
    """Kraken exists in the catalog as soon as 0014 runs, before the scanner has stored
    anything for it: a reader gets an honest empty series, never an error or Binance's data."""
    store(market_data_engine, SyntheticExchange(), limit=6)

    body = read(api, market_data_engine, data_source_code="KRAKEN")

    assert body["candles"] == []
    assert body["freshness"]["status"] == "NO_DATA"
    assert [i["code"] for i in body["issues"]] == ["NO_DATA"]


def test_a_symbol_s_sources_are_listed_in_a_fixed_order_binance_first(
    api: TestClient, market_data_engine: Engine
) -> None:
    """The explorer opens on the first source of this list, so its order is part of the
    contract: Binance (by code) stays the default when Kraken is added."""
    response = api.get(
        f"/api/v1/catalog/instruments/{instrument_id(market_data_engine, 'BTC/USDT')}/mappings"
    )
    assert response.status_code == 200
    analysis = [
        (m["data_source"]["code"], m["provider_symbol"])
        for m in response.json()["data_source_instruments"]
        if m["purpose"] == "ANALYSIS"
    ]
    assert analysis == [("BINANCE", "BTCUSDT"), ("KRAKEN", "XBTUSDT")]
