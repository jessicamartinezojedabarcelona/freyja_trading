"""Kraken Spot public REST adapter, driven by deterministic responses.

No test here touches the network: an in-process transport plays the provider, the clock is
fixed and `sleep` is recorded instead of waited for, so the suite is fast and can never
become flaky because Kraken (or the internet) is down. The one live check is opt-in, in
tests/integration/test_kraken_live.py.

The shapes reproduced here (errors inside a 200 response, 720 candles plus the one in
progress, XBT for Bitcoin, numbers as strings) were observed on the live API on 2026-09-25.
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
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    ASSET_PAIRS_PATH,
    HISTORY_CANDLES,
    OHLC_PATH,
    PROVIDER_SYMBOLS,
    KrakenRestConfig,
    KrakenSpotRestClient,
)
from tests.market_data_support import BTC, ETH, M5, NOW, Provider, at, ok

PAIR = "XBTUSDT"
STEP = 300  # seconds in a 5m candle


def epoch(moment: datetime) -> int:
    return int(moment.timestamp())


def krow(
    open_time: datetime,
    *,
    open_: object = "100.10",
    high: object = "101.00",
    low: object = "99.50",
    close: object = "100.50",
    volume: object = "12.345",
) -> list[object]:
    """One OHLC row in Kraken's 8-field wire format."""
    return [epoch(open_time), open_, high, low, close, "100.30", volume, 7]


def payload(rows: list[list[object]], *, pair: str = PAIR, last: object = 0) -> dict[str, object]:
    return {"error": [], "result": {pair: rows, "last": last}}


def clean_rows() -> list[list[object]]:
    """11:55 and 12:00 are closed at 12:07:30; 12:05 is the candle still in progress."""
    return [krow(at(11, 55)), krow(at(12, 0)), krow(at(12, 5))]


def series(count: int) -> list[list[object]]:
    """`count` consecutive closed 5m candles ending with the 12:00 one, then the open 12:05."""
    first = at(12, 0) - timedelta(seconds=STEP * (count - 1))
    return [krow(first + timedelta(seconds=STEP * index)) for index in range(count)] + [
        krow(at(12, 5))
    ]


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(sleeps: list[float]) -> Iterator[Callable[..., KrakenSpotRestClient]]:
    created: list[KrakenSpotRestClient] = []

    def build(provider: Provider, **config: object) -> KrakenSpotRestClient:
        # Spacing off unless a test asks for it: every other test is about something else.
        options: dict[str, object] = {"min_request_interval_seconds": 0.0, **config}
        client = KrakenSpotRestClient(
            KrakenRestConfig(**options),  # type: ignore[arg-type]
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
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload(clean_rows())))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.OK
    # The candle still in progress was in the answer and is reported, never returned.
    assert [issue.code for issue in batch.issues] == [QualityIssueCode.OPEN_CANDLE_EXCLUDED]
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    first = batch.candles[0]
    assert first.close_time == at(12, 0)
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        Decimal("100.10"),
        Decimal("101.00"),
        Decimal("99.50"),
        Decimal("100.50"),
        Decimal("12.345"),  # the volume, not the vwap that sits before it in the row
    )
    assert all(isinstance(v, Decimal) for v in (first.open, first.volume))
    assert first.open_time.tzinfo is UTC
    assert batch.provenance.source == "KRAKEN"
    assert batch.provenance.provider_symbol == "XBTUSDT"  # Kraken's name for BTC
    assert batch.provenance.endpoint == OHLC_PATH
    assert batch.provenance.received_at == NOW
    assert batch.provenance.attempts == 1
    assert batch.instrument == BTC
    assert batch.timeframe is M5


def test_request_is_public_read_only_and_minimal(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload(clean_rows())))
    make_client(provider).get_closed_candles(BTC, M5, limit=500)

    (request,) = provider.requests
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "api.kraken.com"
    assert request.url.path == OHLC_PATH
    assert dict(request.url.params) == {"pair": "XBTUSDT", "interval": "5"}
    forbidden = {"api-key", "api-sign", "authorization", "cookie"}
    assert forbidden.isdisjoint(name.lower() for name in request.headers)
    assert "nonce" not in request.url.params


def test_a_window_is_sent_as_since_one_second_early_and_enforced_here(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    rows = [krow(at(11, 50)), krow(at(11, 55)), krow(at(12, 0)), krow(at(12, 5))]
    provider = Provider(ok(payload(rows)))
    batch = make_client(provider).get_closed_candles(
        BTC, M5, limit=10, start=at(11, 55), end=at(12, 5)
    )

    # One second early: correct whether `since` is inclusive or exclusive at a candle open.
    assert provider.requests[0].url.params["since"] == str(epoch(at(11, 55)) - 1)
    # Kraken has no `end`, and answered with candles outside the window: they are dropped.
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    assert batch.quality is DataQuality.OK


def test_the_most_recent_candles_are_kept_when_a_limit_is_given(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload(series(10))))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=3)

    assert [c.open_time for c in batch.candles] == [at(11, 50), at(11, 55), at(12, 0)]
    assert batch.quality is DataQuality.OK
    assert "limit" not in provider.requests[0].url.params  # Kraken has none to send


def test_a_window_with_a_limit_keeps_the_first_candles_from_its_start(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload(series(10))))
    start = at(12, 0) - timedelta(seconds=STEP * 9)  # the oldest candle of the answer
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=3, start=start, end=at(12, 5))

    assert [c.open_time for c in batch.candles] == [
        start,
        start + timedelta(seconds=STEP),
        start + timedelta(seconds=2 * STEP),
    ]
    # Cut off at the limit, not missing: no gap and no phantom open candle after the cut.
    assert not [i for i in batch.issues if i.code is QualityIssueCode.GAP]


@pytest.mark.parametrize(
    ("timeframe", "interval"),
    [
        (Timeframe.M1, 1),
        (Timeframe.M5, 5),
        (Timeframe.M15, 15),
        (Timeframe.H1, 60),
        (Timeframe.H4, 240),
    ],
)
def test_every_catalog_timeframe_is_translated_to_kraken_minutes(
    make_client: Callable[..., KrakenSpotRestClient], timeframe: Timeframe, interval: int
) -> None:
    step = int(timeframe.duration.total_seconds())
    newest_closed = timeframe.floor(NOW) - timeframe.duration
    rows = [
        [epoch(newest_closed - timeframe.duration), "1", "2", "1", "2", "1", "3", 1],
        [epoch(newest_closed), "1", "2", "1", "2", "1", "3", 1],
        [epoch(newest_closed + timeframe.duration), "1", "2", "1", "2", "1", "3", 1],
    ]
    provider = Provider(ok(payload(rows)))
    batch = make_client(provider).get_closed_candles(BTC, timeframe, limit=10)

    assert provider.requests[0].url.params["interval"] == str(interval)
    assert batch.quality is DataQuality.OK
    assert all(int((c.close_time - c.open_time).total_seconds()) == step for c in batch.candles)


def test_only_allowlisted_instruments_are_processed(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload(clean_rows(), pair="ETHUSDT")))
    make_client(provider).get_closed_candles(ETH, M5, limit=10)
    assert provider.requests[0].url.params["pair"] == "ETHUSDT"

    client = make_client(Provider(ok(payload([]))))
    for bad in (
        InstrumentRef("CRYPTO", "SPOT", "DOGE/USDT"),
        InstrumentRef("CRYPTO", "SPOT", "BTC/USD"),
        InstrumentRef("FOREX", "SPOT", "EUR/USD"),
        InstrumentRef("CRYPTO", "BINARY_OPTION", "BTC/USDT"),
    ):
        with pytest.raises(UnsupportedInstrumentError):
            client.get_closed_candles(bad, M5, limit=10)
        with pytest.raises(UnsupportedInstrumentError):
            client.get_instrument_metadata(bad)


def test_only_catalog_timeframes_are_accepted(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    client = make_client(Provider(ok(payload([]))))
    for bad in ("5m", 5, None):
        with pytest.raises(MarketDataRequestError):
            client.get_closed_candles(BTC, bad, limit=10)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, HISTORY_CANDLES + 1, True])
def test_limit_must_be_within_what_kraken_can_serve(
    make_client: Callable[..., KrakenSpotRestClient], limit: int
) -> None:
    with pytest.raises(MarketDataRequestError, match="limit"):
        make_client(Provider(ok(payload([])))).get_closed_candles(BTC, M5, limit=limit)


def test_start_and_end_must_be_utc_and_ordered(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    client = make_client(Provider(ok(payload([]))))
    naive = datetime(2026, 9, 24, 9, 0)
    with pytest.raises(MarketDataRequestError, match="start"):
        client.get_closed_candles(BTC, M5, limit=5, start=naive)
    with pytest.raises(MarketDataRequestError, match="end"):
        client.get_closed_candles(BTC, M5, limit=5, end=naive)
    with pytest.raises(MarketDataRequestError, match="before"):
        client.get_closed_candles(BTC, M5, limit=5, start=at(9, 5), end=at(9, 0))


def test_symbols_intervals_and_limits_do_not_drift_from_the_catalog() -> None:
    catalog_pairs = {
        spec.symbol for spec in INSTRUMENTS if (spec.market, spec.product) == ("CRYPTO", "SPOT")
    }
    assert set(PROVIDER_SYMBOLS) == catalog_pairs
    assert PROVIDER_SYMBOLS["BTC/USDT"] == "XBTUSDT"  # Kraken's XBT, the one irregular name

    catalog_seconds = {code: seconds for code, seconds, _ in TIMEFRAMES}
    assert {tf.value: int(tf.duration.total_seconds()) for tf in Timeframe} == catalog_seconds

    # What the scanner is told about this provider.
    assert KrakenSpotRestClient.limits == ProviderLimits(
        max_candles_per_request=720, history_candles=720
    )


def test_config_only_accepts_the_public_market_data_host_over_https() -> None:
    KrakenRestConfig()
    for bad in (
        "http://api.kraken.com",
        "https://www.kraken.com",
        "https://api.kraken.com.evil.example",
        "https://futures.kraken.com",
        "https://data-api.binance.vision",
    ):
        with pytest.raises(ValueError, match="base_url"):
            KrakenRestConfig(base_url=bad)
    with pytest.raises(ValueError, match="max_attempts"):
        KrakenRestConfig(max_attempts=0)
    with pytest.raises(ValueError, match="timeout"):
        KrakenRestConfig(timeout_seconds=0)
    with pytest.raises(ValueError, match="min_request_interval"):
        KrakenRestConfig(min_request_interval_seconds=-1)


# -- what the answer may contain -----------------------------------------------


def test_the_candle_in_progress_is_dropped_never_returned_as_closed(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    batch = make_client(Provider(ok(payload(clean_rows())))).get_closed_candles(BTC, M5, limit=500)
    assert at(12, 5) not in [c.open_time for c in batch.candles]
    assert all(c.close_time <= NOW for c in batch.candles)


def test_a_gap_is_visible_as_degraded_and_keeps_the_real_candles(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    rows = [krow(at(11, 45)), krow(at(11, 55)), krow(at(12, 0)), krow(at(12, 5))]
    batch = make_client(Provider(ok(payload(rows)))).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.DEGRADED
    assert QualityIssueCode.GAP in {issue.code for issue in batch.issues}
    assert [c.open_time for c in batch.candles] == [at(11, 45), at(11, 55), at(12, 0)]


def test_stale_data_is_visible_as_degraded(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    rows = [krow(at(11, 35)), krow(at(11, 40)), krow(at(11, 45))]
    batch = make_client(Provider(ok(payload(rows)))).get_closed_candles(BTC, M5, limit=500)
    assert batch.quality is DataQuality.DEGRADED
    assert QualityIssueCode.STALE in {issue.code for issue in batch.issues}


def test_a_window_older_than_kraken_still_serves_is_incomplete_not_invented(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    """Kraken answers a too-old `since` with its latest candles, which are outside the
    window: nothing of them is kept, and the series says it is incomplete."""
    old_start = at(12, 0) - timedelta(days=3)
    provider = Provider(ok(payload(series(10))))
    batch = make_client(provider).get_closed_candles(
        BTC, M5, limit=100, start=old_start, end=old_start + timedelta(hours=1)
    )

    assert batch.candles == ()
    assert batch.quality is DataQuality.DEGRADED  # not UNAVAILABLE: the provider answered
    assert QualityIssueCode.INCOMPLETE_RANGE in {issue.code for issue in batch.issues}


@pytest.mark.parametrize(
    "body",
    [
        [],  # not an object
        {"error": []},  # no result
        {"error": [], "result": []},  # result is not an object
        {"error": [], "result": {"ETHUSDT": [], "last": 0}},  # answered for another pair
        {"error": [], "result": {PAIR: [], "last": 0, "extra": []}},  # more than one series
        {"error": [], "result": {PAIR: []}},  # no `last`
        {"error": [], "result": {PAIR: [], "last": "0"}},  # `last` is not a number
        {"error": [], "result": {PAIR: {}, "last": 0}},  # rows are not a list
        {"error": [], "result": {PAIR: [[1, "1"]], "last": 0}},  # incomplete row
        {"result": {PAIR: [], "last": 0}},  # no error list
        payload([krow(at(12, 0), open_=100.1)]),  # a JSON float already lost precision
        payload([krow(at(12, 0), open_="not a number")]),
        payload([krow(at(12, 0), close="-1", low="-2", open_="-1", high="-1")]),  # not positive
        payload([krow(at(12, 0), high="90.00")]),  # high below low
        payload([[True, "1", "2", "1", "2", "1", "3", 1]]),  # boolean as a timestamp
        payload([[epoch(at(12, 0)) * 10**6, "1", "2", "1", "2", "1", "3", 1]]),  # year 60k
        payload([krow(at(12, 1))]),  # not on the 5m UTC grid
        payload([krow(at(9, 0))] * (HISTORY_CANDLES + 2)),  # more than Kraken promises
        payload([krow(at(12, 0)), krow(at(12, 0), close="100.60")]),  # conflicting duplicate
    ],
)
def test_an_invalid_answer_is_unavailable_with_no_candles(
    make_client: Callable[..., KrakenSpotRestClient], body: object
) -> None:
    batch = make_client(Provider(ok(body))).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.candles == ()
    assert [issue.code for issue in batch.issues] == [QualityIssueCode.INVALID_RESPONSE]


def test_a_body_that_is_not_json_is_unavailable(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    batch = make_client(Provider(httpx2.Response(200, content=b"<html>"))).get_closed_candles(
        BTC, M5, limit=5
    )
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.INVALID_RESPONSE


# -- errors Kraken reports inside a 200 answer ----------------------------------


def test_the_rate_limit_error_is_retried_with_backoff_then_recovers(
    make_client: Callable[..., KrakenSpotRestClient], sleeps: list[float]
) -> None:
    limited = ok({"error": ["EGeneral:Too many requests"]})
    provider = Provider(limited, limited, ok(payload(clean_rows())))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.OK
    assert batch.provenance.attempts == 3
    assert sleeps == [1.0, 2.0]  # bounded, deterministic exponential backoff


def test_a_persistent_rate_limit_ends_as_rate_limited_and_never_hammers(
    make_client: Callable[..., KrakenSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(ok({"error": ["EAPI:Rate limit exceeded"]}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.RATE_LIMITED
    assert len(provider.requests) == 3  # max_attempts, then it stops
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    "code", ["EService:Unavailable", "EService:Busy", "EGeneral:Internal error"]
)
def test_a_service_error_is_retried_as_a_provider_error(
    make_client: Callable[..., KrakenSpotRestClient], code: str
) -> None:
    provider = Provider(ok({"error": [code]}), ok(payload(clean_rows())))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.OK
    assert len(provider.requests) == 2


def test_a_rejected_request_is_not_retried(
    make_client: Callable[..., KrakenSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(ok({"error": ["EQuery:Unknown asset pair"]}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.INVALID_RESPONSE
    assert "EQuery:Unknown asset pair" in batch.issues[0].detail
    assert len(provider.requests) == 1
    assert sleeps == []


def test_an_error_text_that_is_not_a_kraken_code_is_never_echoed(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok({"error": ["<script>alert('x')</script> internal detail"]}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.UNAVAILABLE
    assert "script" not in batch.issues[0].detail
    assert "internal detail" not in batch.issues[0].detail


# -- transport failures ------------------------------------------------------------


def test_http_429_waits_the_retry_after_then_recovers(
    make_client: Callable[..., KrakenSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(
        httpx2.Response(429, headers={"Retry-After": "3"}), ok(payload(clean_rows()))
    )
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
    assert batch.quality is DataQuality.OK
    assert sleeps == [3.0]


def test_http_429_with_a_retry_after_beyond_the_cap_fails_fast(
    make_client: Callable[..., KrakenSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": "600"}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
    assert batch.issues[0].code is QualityIssueCode.RATE_LIMITED
    assert len(provider.requests) == 1
    assert sleeps == []


def test_a_5xx_is_retried_and_can_recover(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(httpx2.Response(503), ok(payload(clean_rows())))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
    assert batch.quality is DataQuality.OK
    assert len(provider.requests) == 2


def test_a_timeout_is_retried_then_reported_as_unavailable(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(httpx2.ReadTimeout("slow"))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.issues[0].code is QualityIssueCode.TIMEOUT
    assert len(provider.requests) == 3


def test_a_network_error_is_reported_without_leaking_details(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(httpx2.ConnectError("secret-host.internal refused"))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
    assert batch.issues[0].code is QualityIssueCode.PROVIDER_ERROR
    assert "secret-host" not in batch.issues[0].detail


def test_other_client_errors_and_redirects_are_not_retried_or_followed(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    for response in (
        httpx2.Response(403),
        httpx2.Response(302, headers={"Location": "https://evil.example/x"}),
    ):
        provider = Provider(response)
        batch = make_client(provider).get_closed_candles(BTC, M5, limit=500)
        assert len(provider.requests) == 1
        assert batch.quality is DataQuality.UNAVAILABLE


def test_failures_are_logged_without_secrets_or_payloads(
    make_client: Callable[..., KrakenSpotRestClient], caplog: pytest.LogCaptureFixture
) -> None:
    body = json.dumps({"error": ["EGeneral:Invalid arguments"], "detail": "must not be logged"})
    with caplog.at_level("WARNING"):
        make_client(Provider(httpx2.Response(400, content=body))).get_closed_candles(
            BTC, M5, limit=5
        )
    (record,) = caplog.records
    assert record.getMessage() == "market_data_unavailable"
    assert "must not be logged" not in caplog.text
    assert record.__dict__["source"] == "KRAKEN"
    assert record.__dict__["issue"] == "PROVIDER_ERROR"


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


def spaced_client(fake: FakeTime, provider: Provider, spacing: float) -> KrakenSpotRestClient:
    return KrakenSpotRestClient(
        KrakenRestConfig(min_request_interval_seconds=spacing),
        transport=httpx2.MockTransport(provider),
        clock=lambda: NOW,
        sleep=fake.sleep,
        monotonic=fake.monotonic,
    )


def test_requests_are_spaced_so_a_full_scan_never_trips_the_rate_limit() -> None:
    fake = FakeTime()
    provider = Provider(ok(payload(clean_rows())))
    with spaced_client(fake, provider, 1.0) as client:
        for _ in range(4):
            client.get_closed_candles(BTC, M5, limit=500)

    assert len(provider.requests) == 4
    assert fake.slept == [1.0, 1.0, 1.0]  # none before the first, one full second between


def test_no_wait_is_added_when_enough_time_has_already_passed() -> None:
    fake = FakeTime()
    provider = Provider(ok(payload(clean_rows())))
    with spaced_client(fake, provider, 1.0) as client:
        client.get_closed_candles(BTC, M5, limit=500)
        fake.now += 5.0  # the scanner spent its time elsewhere
        client.get_closed_candles(BTC, M5, limit=500)
        fake.now += 0.4
        client.get_closed_candles(BTC, M5, limit=500)

    assert fake.slept == [pytest.approx(0.6)]


def test_a_retry_after_a_rate_limit_error_is_spaced_too() -> None:
    fake = FakeTime()
    limited = ok({"error": ["EGeneral:Too many requests"]})
    provider = Provider(limited, ok(payload(clean_rows())))
    with spaced_client(fake, provider, 1.0) as client:
        batch = client.get_closed_candles(BTC, M5, limit=500)

    assert batch.quality is DataQuality.OK
    assert fake.slept == [1.0]  # the backoff itself already satisfied the spacing


# -- instrument metadata ---------------------------------------------------------


def pair_info(**overrides: object) -> dict[str, object]:
    info: dict[str, object] = {
        "altname": PAIR,
        "wsname": "XBT/USDT",
        "base": "XXBT",
        "quote": "USDT",
        "status": "online",
    }
    return {**info, **overrides}


def pairs_answer(info: dict[str, object], key: str = PAIR) -> dict[str, object]:
    return {"error": [], "result": {key: info}}


def test_metadata_confirms_the_catalog_mapping_translating_xbt_to_btc(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(pairs_answer(pair_info())))
    result = make_client(provider).get_instrument_metadata(BTC)

    assert result.quality is DataQuality.OK
    assert result.metadata is not None
    assert (result.metadata.base_asset, result.metadata.quote_asset) == ("BTC", "USDT")
    assert result.metadata.provider_symbol == "XBTUSDT"
    assert result.metadata.trading is True
    assert result.provenance.endpoint == ASSET_PAIRS_PATH
    assert dict(provider.requests[0].url.params) == {"pair": "XBTUSDT"}


def test_metadata_for_a_pair_not_open_for_trading_is_degraded(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(pairs_answer(pair_info(status="cancel_only"))))
    result = make_client(provider).get_instrument_metadata(BTC)

    assert result.quality is DataQuality.DEGRADED
    assert result.metadata is not None
    assert result.metadata.trading is False
    assert result.issues[0].code is QualityIssueCode.INSTRUMENT_NOT_TRADING


def test_metadata_that_contradicts_the_catalog_is_unavailable(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(pairs_answer(pair_info(wsname="ETH/USDT"))))
    result = make_client(provider).get_instrument_metadata(BTC)

    assert result.quality is DataQuality.UNAVAILABLE
    assert result.metadata is None
    assert result.issues[0].code is QualityIssueCode.SYMBOL_MISMATCH


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"error": [], "result": {}},
        {"error": [], "result": {PAIR: pair_info(), "ETHUSDT": pair_info()}},
        pairs_answer(pair_info(), key="ETHUSDT"),  # a different pair than requested
        pairs_answer(pair_info(wsname=None)),
        pairs_answer(pair_info(wsname="XBTUSDT")),  # no slash
        pairs_answer(pair_info(wsname="/USDT")),
        pairs_answer(pair_info(status=None)),
        pairs_answer("not an object"),  # type: ignore[arg-type]
    ],
)
def test_invalid_metadata_is_unavailable(
    make_client: Callable[..., KrakenSpotRestClient], body: object
) -> None:
    result = make_client(Provider(ok(body))).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.issues[0].code is QualityIssueCode.INVALID_RESPONSE


def test_metadata_failures_are_reported_like_candle_failures(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    result = make_client(Provider(ok({"error": ["EService:Unavailable"]}))).get_instrument_metadata(
        BTC
    )
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.issues[0].code is QualityIssueCode.PROVIDER_ERROR


# -- the whole surface ---------------------------------------------------------------


def test_only_the_two_public_endpoints_are_ever_called(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(pairs_answer(pair_info())), ok(payload(clean_rows())))
    client = make_client(provider)
    client.get_instrument_metadata(BTC)
    client.get_closed_candles(BTC, M5, limit=500)
    assert {request.url.path for request in provider.requests} == {OHLC_PATH, ASSET_PAIRS_PATH}
    assert {request.method for request in provider.requests} == {"GET"}


def test_a_private_or_unlisted_path_is_refused_before_any_request(
    make_client: Callable[..., KrakenSpotRestClient],
) -> None:
    provider = Provider(ok(payload([])))
    client = make_client(provider)
    for path in ("/0/private/Balance", "/0/private/AddOrder", "/0/public/Trades", "/"):
        with pytest.raises(MarketDataRequestError, match="allowlisted"):
            client._get_json(path, {})  # the allowlist is the adapter's whole surface
    assert provider.requests == []
