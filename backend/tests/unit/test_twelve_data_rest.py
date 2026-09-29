"""Twelve Data REST adapter, driven by deterministic responses.

No test here touches the network: an in-process transport plays the provider, the clock is
fixed and `sleep` is recorded instead of waited for, so the suite is fast and can never
become flaky because Twelve Data (or the internet) is down. The one live check is opt-in,
in tests/integration/test_twelve_data_live.py.

Twelve Data's exact error shapes are unverified without a live API key (see the adapter's
module docstring); the embedded-error behaviour here is deliberately defensive and
documented as such.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from freyja_backend.db.catalog_seed_v1 import INSTRUMENTS, TIMEFRAMES
from freyja_backend.domain.market_data import (
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    ProviderLimits,
    QualityIssueCode,
    Timeframe,
    UnsupportedInstrumentError,
)
from freyja_backend.infrastructure.market_data.twelve_data_rest import (
    MAX_CANDLE_LIMIT,
    PROVIDER_SYMBOLS,
    SYMBOL_MARKETS,
    TIME_SERIES_PATH,
    TwelveDataRestClient,
    TwelveDataRestConfig,
)
from tests.market_data_support import EUR_USD, GBP_USD, M5, NOW, XAU_USD, Provider, at, ok

API_KEY = "test-key-not-a-real-secret"
STEP = 300  # seconds in a 5m candle


def tvalue(
    open_time: datetime,
    *,
    open_: object = "100.10",
    high: object = "101.00",
    low: object = "99.50",
    close: object = "100.50",
    volume: object = "12.345",
) -> dict[str, object]:
    return {
        "datetime": open_time.strftime("%Y-%m-%d %H:%M:%S"),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def payload(
    values: list[dict[str, object]], *, symbol: str = "EUR/USD", interval: str = "5min"
) -> dict[str, object]:
    return {
        "meta": {
            "symbol": symbol,
            "interval": interval,
            "currency_base": "Euro",
            "currency_quote": "US Dollar",
            "type": "Physical Currency",
        },
        "values": values,
        "status": "ok",
    }


def clean_values() -> list[dict[str, object]]:
    """11:55 and 12:00 are closed at 12:07:30; 12:05 is the candle still in progress."""
    return [tvalue(at(11, 55)), tvalue(at(12, 0)), tvalue(at(12, 5))]


def series(count: int) -> list[dict[str, object]]:
    """`count` consecutive closed 5m candles ending with the 12:00 one, then the open 12:05."""
    first = at(12, 0) - timedelta(seconds=STEP * (count - 1))
    return [tvalue(first + timedelta(seconds=STEP * index)) for index in range(count)] + [
        tvalue(at(12, 5))
    ]


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(sleeps: list[float]) -> Iterator[Callable[..., TwelveDataRestClient]]:
    created: list[TwelveDataRestClient] = []

    def build(provider: Provider, **config: object) -> TwelveDataRestClient:
        # Spacing and quota off unless a test asks for them: every other test is about
        # something else.
        options: dict[str, object] = {
            "api_key": API_KEY,
            "min_request_interval_seconds": 0.0,
            "daily_quota": 1_000_000,
            **config,
        }
        client = TwelveDataRestClient(
            TwelveDataRestConfig(**options),  # type: ignore[arg-type]
            transport=httpx2.MockTransport(provider),
            clock=lambda: NOW,
            sleep=sleeps.append,
        )
        created.append(client)
        return client

    yield build
    for client in created:
        client.close()


# -- happy path and what is sent ----------------------------------------------


def test_returns_closed_candles_with_exact_decimals_and_provenance(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload(clean_values())))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.OK
    assert [issue.code for issue in batch.issues] == [QualityIssueCode.OPEN_CANDLE_EXCLUDED]
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    first = batch.candles[0]
    assert first.close_time == at(12, 0)
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        Decimal("100.10"),
        Decimal("101.00"),
        Decimal("99.50"),
        Decimal("100.50"),
        Decimal("12.345"),
    )
    assert all(isinstance(v, Decimal) for v in (first.open, first.volume))
    assert first.open_time.tzinfo is UTC
    assert batch.provenance.source == "TWELVEDATA"
    assert batch.provenance.provider_symbol == "EUR/USD"
    assert batch.provenance.endpoint == TIME_SERIES_PATH
    assert batch.provenance.received_at == NOW
    assert batch.provenance.attempts == 1
    assert batch.instrument == EUR_USD
    assert batch.timeframe is M5


def test_request_is_minimal_and_carries_only_the_key_in_the_header(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload(clean_values())))
    make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)

    (request,) = provider.requests
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "api.twelvedata.com"
    assert request.url.path == TIME_SERIES_PATH
    assert dict(request.url.params) == {
        "symbol": "EUR/USD",
        "interval": "5min",
        "timezone": "UTC",
        "order": "ASC",
        "outputsize": "500",
    }
    assert request.headers["Authorization"] == f"apikey {API_KEY}"
    assert "cookie" not in {name.lower() for name in request.headers}
    assert API_KEY not in str(request.url)  # the key travels only in the header, never the URL


def test_a_window_is_sent_as_start_and_end_date(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload([tvalue(at(11, 55)), tvalue(at(12, 0))])))
    make_client(provider).get_closed_candles(EUR_USD, M5, limit=10, start=at(11, 55), end=at(12, 5))

    params = provider.requests[0].url.params
    assert params["start_date"] == "2026-09-24 11:55:00"
    # One second early: `[start, end)` is half-open.
    assert params["end_date"] == "2026-09-24 12:04:59"


@pytest.mark.parametrize(
    ("timeframe", "interval"),
    [
        (Timeframe.M1, "1min"),
        (Timeframe.M5, "5min"),
        (Timeframe.M15, "15min"),
        (Timeframe.H1, "1h"),
        (Timeframe.H4, "4h"),
    ],
)
def test_every_catalog_timeframe_is_translated_to_twelve_data_intervals(
    make_client: Callable[..., TwelveDataRestClient], timeframe: Timeframe, interval: str
) -> None:
    newest_closed = timeframe.floor(NOW) - timeframe.duration
    values = [
        tvalue(newest_closed - timeframe.duration),
        tvalue(newest_closed),
        tvalue(newest_closed + timeframe.duration),
    ]
    provider = Provider(ok(payload(values, interval=interval)))
    batch = make_client(provider).get_closed_candles(EUR_USD, timeframe, limit=10)

    assert provider.requests[0].url.params["interval"] == interval
    assert batch.quality is DataQuality.OK


def test_forex_and_metals_symbols_both_resolve_to_their_own_market(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload(clean_values(), symbol="GBP/USD")))
    make_client(provider).get_closed_candles(GBP_USD, M5, limit=10)
    assert provider.requests[0].url.params["symbol"] == "GBP/USD"

    provider = Provider(ok(payload(clean_values(), symbol="XAU/USD")))
    make_client(provider).get_closed_candles(XAU_USD, M5, limit=10)
    assert provider.requests[0].url.params["symbol"] == "XAU/USD"


def test_a_symbol_under_the_wrong_catalog_market_is_rejected(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    client = make_client(Provider(ok(payload([]))))
    for bad in (
        InstrumentRef("METALS", "SPOT", "EUR/USD"),  # EUR/USD is FOREX, not METALS
        InstrumentRef("FOREX", "SPOT", "XAU/USD"),  # XAU/USD is METALS, not FOREX
        InstrumentRef("CRYPTO", "SPOT", "BTC/USDT"),
        InstrumentRef("FOREX", "BINARY_OPTION", "EUR/USD"),
    ):
        with pytest.raises(UnsupportedInstrumentError):
            client.get_closed_candles(bad, M5, limit=10)
        with pytest.raises(UnsupportedInstrumentError):
            client.get_instrument_metadata(bad)


def test_only_catalog_timeframes_are_accepted(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    client = make_client(Provider(ok(payload([]))))
    for bad in ("5m", 5, None):
        with pytest.raises(MarketDataRequestError):
            client.get_closed_candles(EUR_USD, bad, limit=10)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, MAX_CANDLE_LIMIT + 1, True])
def test_limit_must_be_within_what_twelve_data_can_serve(
    make_client: Callable[..., TwelveDataRestClient], limit: int
) -> None:
    with pytest.raises(MarketDataRequestError, match="limit"):
        make_client(Provider(ok(payload([])))).get_closed_candles(EUR_USD, M5, limit=limit)


def test_start_and_end_must_be_utc_and_ordered(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    client = make_client(Provider(ok(payload([]))))
    naive = datetime(2026, 9, 24, 9, 0)
    with pytest.raises(MarketDataRequestError, match="start"):
        client.get_closed_candles(EUR_USD, M5, limit=5, start=naive)
    with pytest.raises(MarketDataRequestError, match="end"):
        client.get_closed_candles(EUR_USD, M5, limit=5, end=naive)
    with pytest.raises(MarketDataRequestError, match="before"):
        client.get_closed_candles(EUR_USD, M5, limit=5, start=at(9, 5), end=at(9, 0))


def test_symbols_and_timeframes_do_not_drift_from_the_catalog() -> None:
    # EUR/USD (and FOREX) is in the frozen v1 seed (`catalog_seed_v1.INSTRUMENTS`); the
    # other four came from the separate, additive migration 0016_forex_metals_catalog
    # (MARKET-DATA-TWELVEDATA-CATALOG-001), so they are not in that frozen module.
    catalog_v1_forex = {
        spec.symbol for spec in INSTRUMENTS if spec.product == "SPOT" and spec.market == "FOREX"
    }
    assert catalog_v1_forex == {"EUR/USD"}
    migration_0016_symbols = {"GBP/USD", "USD/JPY", "USD/CHF", "XAU/USD"}

    catalog_forex_metals = catalog_v1_forex | migration_0016_symbols
    assert set(PROVIDER_SYMBOLS) == catalog_forex_metals
    assert set(SYMBOL_MARKETS) == catalog_forex_metals
    assert SYMBOL_MARKETS["XAU/USD"] == "METALS"  # Jessica's decision, 2026-09-29
    assert all(
        SYMBOL_MARKETS[symbol] == "FOREX" for symbol in PROVIDER_SYMBOLS if symbol != "XAU/USD"
    )

    catalog_seconds = {code: seconds for code, seconds, _ in TIMEFRAMES}
    assert {tf.value: int(tf.duration.total_seconds()) for tf in Timeframe} == catalog_seconds

    assert TwelveDataRestClient.limits == ProviderLimits(max_candles_per_request=MAX_CANDLE_LIMIT)


def test_config_requires_a_key_and_the_public_market_data_host_over_https() -> None:
    TwelveDataRestConfig(api_key=API_KEY)
    with pytest.raises(ValueError, match="api_key"):
        TwelveDataRestConfig(api_key="")
    with pytest.raises(ValueError, match="api_key"):
        TwelveDataRestConfig(api_key="   ")
    for bad in (
        "http://api.twelvedata.com",
        "https://www.twelvedata.com",
        "https://api.twelvedata.com.evil.example",
        "https://api.kraken.com",
    ):
        with pytest.raises(ValueError, match="base_url"):
            TwelveDataRestConfig(api_key=API_KEY, base_url=bad)
    with pytest.raises(ValueError, match="max_attempts"):
        TwelveDataRestConfig(api_key=API_KEY, max_attempts=0)
    with pytest.raises(ValueError, match="timeout"):
        TwelveDataRestConfig(api_key=API_KEY, timeout_seconds=0)
    with pytest.raises(ValueError, match="min_request_interval"):
        TwelveDataRestConfig(api_key=API_KEY, min_request_interval_seconds=-1)
    with pytest.raises(ValueError, match="daily_quota"):
        TwelveDataRestConfig(api_key=API_KEY, daily_quota=0)


# -- what the answer may contain -----------------------------------------------


def test_the_candle_in_progress_is_dropped_never_returned_as_closed(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    batch = make_client(Provider(ok(payload(clean_values())))).get_closed_candles(
        EUR_USD, M5, limit=500
    )
    assert at(12, 5) not in [c.open_time for c in batch.candles]
    assert all(c.close_time <= NOW for c in batch.candles)


def test_a_gap_is_visible_as_degraded_and_keeps_the_real_candles(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    values = [tvalue(at(11, 45)), tvalue(at(11, 55)), tvalue(at(12, 0)), tvalue(at(12, 5))]
    batch = make_client(Provider(ok(payload(values)))).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.DEGRADED
    assert QualityIssueCode.GAP in {issue.code for issue in batch.issues}
    assert [c.open_time for c in batch.candles] == [at(11, 45), at(11, 55), at(12, 0)]


def test_stale_data_is_visible_as_degraded(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    values = [tvalue(at(11, 35)), tvalue(at(11, 40)), tvalue(at(11, 45))]
    batch = make_client(Provider(ok(payload(values)))).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.quality is DataQuality.DEGRADED
    assert QualityIssueCode.STALE in {issue.code for issue in batch.issues}


def test_a_missing_or_null_volume_is_treated_as_zero(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    values = [tvalue(at(11, 55), volume=None), tvalue(at(12, 0))]
    batch = make_client(Provider(ok(payload(values)))).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.quality is DataQuality.OK
    assert batch.candles[0].volume == Decimal("0")


@pytest.mark.parametrize(
    "body",
    [
        [],  # not an object
        {"status": "ok"},  # no meta
        {"meta": {"symbol": "GBP/USD"}, "values": [], "status": "ok"},  # answered for another pair
        {"meta": {"symbol": "EUR/USD"}, "values": "not a list", "status": "ok"},
        {
            "meta": {"symbol": "EUR/USD"},
            "values": [{"datetime": "2026-09-24 12:00:00"}],
            "status": "ok",
        },
        payload([tvalue(at(12, 0), open_=100.1)]),  # a JSON float already lost precision
        payload([tvalue(at(12, 0), open_="not a number")]),
        payload([tvalue(at(12, 0), close="-1", low="-2", open_="-1", high="-1")]),
        payload([tvalue(at(12, 0), high="90.00")]),  # high below low
        payload([tvalue(at(12, 0), open_=None) | {"datetime": None}]),  # invalid datetime
        payload([tvalue(at(12, 0)) | {"datetime": "24/09/2026 12:00"}]),  # wrong format
        payload([tvalue(at(12, 1))]),  # not on the 5m UTC grid
        payload([tvalue(at(12, 0)), tvalue(at(12, 0), close="100.60")]),  # conflicting duplicate
    ],
)
def test_an_invalid_answer_is_unavailable_with_no_candles(
    make_client: Callable[..., TwelveDataRestClient], body: object
) -> None:
    batch = make_client(Provider(ok(body))).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.candles == ()
    assert [issue.code for issue in batch.issues] == [QualityIssueCode.INVALID_RESPONSE]


def test_a_body_that_is_not_json_is_unavailable(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    batch = make_client(Provider(httpx2.Response(200, content=b"<html>"))).get_closed_candles(
        EUR_USD, M5, limit=5
    )
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.INVALID_RESPONSE


# -- errors reported inside an HTTP 200 body (unverified shape, handled defensively) ----


def test_an_embedded_rate_limit_error_is_retried_with_backoff_then_recovers(
    make_client: Callable[..., TwelveDataRestClient], sleeps: list[float]
) -> None:
    limited = ok({"code": 429, "message": "quota exceeded", "status": "error"})
    provider = Provider(limited, limited, ok(payload(clean_values())))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.OK
    assert batch.provenance.attempts == 3
    assert sleeps == [1.0, 2.0]


def test_an_embedded_auth_error_is_not_retried(
    make_client: Callable[..., TwelveDataRestClient], sleeps: list[float]
) -> None:
    provider = Provider(ok({"code": 401, "message": "invalid apikey", "status": "error"}))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.PROVIDER_ERROR
    assert len(provider.requests) == 1
    assert sleeps == []


def test_an_embedded_rejection_is_not_retried(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok({"code": 400, "message": "**symbol** not found", "status": "error"}))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.INVALID_RESPONSE
    assert len(provider.requests) == 1


def test_failures_are_logged_without_the_api_key_or_payload(
    make_client: Callable[..., TwelveDataRestClient], caplog: pytest.LogCaptureFixture
) -> None:
    body = json.dumps({"code": 401, "message": "must not be logged", "status": "error"})
    with caplog.at_level("WARNING"):
        make_client(Provider(httpx2.Response(200, content=body))).get_closed_candles(
            EUR_USD, M5, limit=5
        )
    (record,) = caplog.records
    assert record.getMessage() == "market_data_unavailable"
    assert API_KEY not in caplog.text
    assert record.__dict__["source"] == "TWELVEDATA"


# -- daily quota ---------------------------------------------------------------------


def test_the_daily_quota_is_enforced_locally_before_any_request_is_sent(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload(clean_values())))
    client = make_client(provider, daily_quota=2)

    client.get_closed_candles(EUR_USD, M5, limit=500)
    client.get_closed_candles(EUR_USD, M5, limit=500)
    batch = client.get_closed_candles(EUR_USD, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.RATE_LIMITED
    assert "daily quota" in batch.issues[0].detail
    assert len(provider.requests) == 2  # the third call never reached the network


def test_the_daily_quota_resets_on_a_new_utc_day() -> None:
    provider = Provider(ok(payload(clean_values())))
    current = {"now": NOW}
    client = TwelveDataRestClient(
        TwelveDataRestConfig(api_key=API_KEY, min_request_interval_seconds=0.0, daily_quota=1),
        transport=httpx2.MockTransport(provider),
        clock=lambda: current["now"],
    )
    try:
        first = client.get_closed_candles(EUR_USD, M5, limit=500)
        current["now"] = NOW + timedelta(days=1)
        second = client.get_closed_candles(EUR_USD, M5, limit=500)
    finally:
        client.close()
    assert first.quality is DataQuality.OK
    # `second`'s fixed fixture data is now a day stale relative to the advanced clock
    # (DEGRADED), but the point of this test is that it reached the network at all.
    assert QualityIssueCode.RATE_LIMITED not in {issue.code for issue in second.issues}
    assert len(provider.requests) == 2


# -- transport failures ------------------------------------------------------------


def test_http_429_waits_the_retry_after_then_recovers(
    make_client: Callable[..., TwelveDataRestClient], sleeps: list[float]
) -> None:
    provider = Provider(
        httpx2.Response(429, headers={"Retry-After": "3"}), ok(payload(clean_values()))
    )
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.quality is DataQuality.OK
    assert sleeps == [3.0]


def test_http_429_with_a_retry_after_beyond_the_cap_fails_fast(
    make_client: Callable[..., TwelveDataRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": "600"}))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.issues[0].code is QualityIssueCode.RATE_LIMITED
    assert len(provider.requests) == 1
    assert sleeps == []


def test_http_401_and_403_are_never_retried(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    for status in (401, 403):
        provider = Provider(httpx2.Response(status))
        batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
        assert batch.quality is DataQuality.UNAVAILABLE
        assert batch.issues[0].code is QualityIssueCode.PROVIDER_ERROR
        assert len(provider.requests) == 1


def test_a_5xx_is_retried_and_can_recover(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(httpx2.Response(503), ok(payload(clean_values())))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.quality is DataQuality.OK
    assert len(provider.requests) == 2


def test_a_timeout_is_retried_then_reported_as_unavailable(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(httpx2.ReadTimeout("slow"))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.TIMEOUT
    assert len(provider.requests) == 3


def test_a_network_error_is_reported_without_leaking_details(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(httpx2.ConnectError("secret-host.internal refused"))
    batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
    assert batch.issues[0].code is QualityIssueCode.PROVIDER_ERROR
    assert "secret-host" not in batch.issues[0].detail


def test_other_client_errors_and_redirects_are_not_retried_or_followed(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    for response in (
        httpx2.Response(404),
        httpx2.Response(302, headers={"Location": "https://evil.example/x"}),
    ):
        provider = Provider(response)
        batch = make_client(provider).get_closed_candles(EUR_USD, M5, limit=500)
        assert len(provider.requests) == 1
        assert batch.quality is DataQuality.UNAVAILABLE


# -- request spacing ---------------------------------------------------------------


class FakeTime:
    """A monotonic clock that only moves when the client sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def spaced_client(fake: FakeTime, provider: Provider, spacing: float) -> TwelveDataRestClient:
    return TwelveDataRestClient(
        TwelveDataRestConfig(api_key=API_KEY, min_request_interval_seconds=spacing),
        transport=httpx2.MockTransport(provider),
        clock=lambda: NOW,
        sleep=fake.sleep,
        monotonic=fake.monotonic,
    )


def test_requests_are_spaced_so_a_full_scan_stays_under_the_per_minute_limit() -> None:
    fake = FakeTime()
    provider = Provider(ok(payload(clean_values())))
    with spaced_client(fake, provider, 8.0) as client:
        for _ in range(3):
            client.get_closed_candles(EUR_USD, M5, limit=500)

    assert len(provider.requests) == 3
    assert fake.slept == [8.0, 8.0]


def test_no_wait_is_added_when_enough_time_has_already_passed() -> None:
    fake = FakeTime()
    provider = Provider(ok(payload(clean_values())))
    with spaced_client(fake, provider, 8.0) as client:
        client.get_closed_candles(EUR_USD, M5, limit=500)
        fake.now += 20.0
        client.get_closed_candles(EUR_USD, M5, limit=500)

    assert fake.slept == []


# -- instrument metadata ---------------------------------------------------------


def test_metadata_confirms_the_catalog_mapping(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload([tvalue(at(12, 5))])))
    result = make_client(provider).get_instrument_metadata(EUR_USD)

    assert result.quality is DataQuality.OK
    assert result.metadata is not None
    assert (result.metadata.base_asset, result.metadata.quote_asset) == ("EUR", "USD")
    assert result.metadata.provider_symbol == "EUR/USD"
    assert result.metadata.trading is True
    assert result.provenance.endpoint == TIME_SERIES_PATH
    assert dict(provider.requests[0].url.params) == {
        "symbol": "EUR/USD",
        "interval": "1min",
        "timezone": "UTC",
        "order": "DESC",
        "outputsize": "1",
    }


def test_metadata_with_no_recent_values_is_degraded(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload([])))
    result = make_client(provider).get_instrument_metadata(EUR_USD)

    assert result.quality is DataQuality.DEGRADED
    assert result.metadata is not None
    assert result.metadata.trading is False
    assert result.issues[0].code is QualityIssueCode.INSTRUMENT_NOT_TRADING


def test_metadata_for_a_different_symbol_than_requested_is_unavailable(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    """Unlike Kraken's AssetPairs, Twelve Data's `meta` gives no independent base/quote
    ground truth to cross-check against the catalog — only whether the provider answered
    for the symbol that was actually requested."""
    provider = Provider(ok(payload([tvalue(at(12, 5))], symbol="GBP/USD")))
    result = make_client(provider).get_instrument_metadata(EUR_USD)

    assert result.quality is DataQuality.UNAVAILABLE
    assert result.metadata is None
    assert result.issues[0].code is QualityIssueCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"status": "ok"},
        {"meta": {"symbol": "GBP/USD"}, "values": [], "status": "ok"},
        {"meta": {"symbol": "EURUSD"}, "values": [], "status": "ok"},  # no slash
        {"meta": {"symbol": "/USD"}, "values": [], "status": "ok"},
        {"meta": "not an object", "values": [], "status": "ok"},
    ],
)
def test_invalid_metadata_is_unavailable(
    make_client: Callable[..., TwelveDataRestClient], body: object
) -> None:
    result = make_client(Provider(ok(body))).get_instrument_metadata(EUR_USD)
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.issues[0].code is QualityIssueCode.INVALID_RESPONSE


def test_metadata_failures_are_reported_like_candle_failures(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    result = make_client(
        Provider(ok({"code": 500, "message": "internal", "status": "error"}))
    ).get_instrument_metadata(EUR_USD)
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.issues[0].code is QualityIssueCode.PROVIDER_ERROR


# -- the whole surface ---------------------------------------------------------------


def test_only_time_series_is_ever_called(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload([tvalue(at(12, 5))])), ok(payload(clean_values())))
    client = make_client(provider)
    client.get_instrument_metadata(EUR_USD)
    client.get_closed_candles(EUR_USD, M5, limit=500)
    assert {request.url.path for request in provider.requests} == {TIME_SERIES_PATH}
    assert {request.method for request in provider.requests} == {"GET"}


def test_an_unlisted_path_is_refused_before_any_request(
    make_client: Callable[..., TwelveDataRestClient],
) -> None:
    provider = Provider(ok(payload([])))
    client = make_client(provider)
    for path in ("/quote", "/symbol_search", "/"):
        with pytest.raises(MarketDataRequestError, match="allowlisted"):
            client._get_json(path, {})  # the allowlist is the adapter's whole surface
    assert provider.requests == []
