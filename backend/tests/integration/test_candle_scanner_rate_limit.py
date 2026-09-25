"""A source that says "too many requests" is left alone (MARKET-DATA-RATE-LIMIT-001).

Seen in production: Binance answered RATE_LIMITED to the backend's shared Render IP, and the
scanner kept asking for every other series of that source (a dozen requests in four seconds)
and again a minute later. Insisting is what turns a temporary limit into an IP ban. These
tests run the real scanner, adapters and PostgreSQL; only the two providers are simulated,
and every request is counted.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import httpx2
import pytest
from sqlalchemy import Engine, select

from freyja_backend.application.candle_scanner import (
    RATE_LIMIT_COOLDOWN_SECONDS,
    CandleScanner,
    ScanOutcome,
    ScanReport,
    ScanTarget,
)
from freyja_backend.application.candle_scanner_service import _FAILURE_OUTCOMES
from freyja_backend.db.models import MarketDataSyncState
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import InstrumentRef
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    KrakenRestConfig,
    KrakenSpotRestClient,
)
from tests.market_data_support import (
    BTC,
    ETH,
    M1,
    NOW,
    SyntheticExchange,
    SyntheticKraken,
)

SOL = InstrumentRef("CRYPTO", "SPOT", "SOL/USDT")
SECOND = timedelta(seconds=1)
ALWAYS = frozenset(range(1, 500))


class Time:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def move(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def binance(instrument: InstrumentRef) -> ScanTarget:
    return ScanTarget("BINANCE", instrument, M1)


def kraken(instrument: InstrumentRef) -> ScanTarget:
    return ScanTarget("KRAKEN", instrument, M1)


World = tuple[CandleScanner, SyntheticExchange, SyntheticKraken, Time]


@pytest.fixture
def world(market_data_engine: Engine, clean_market_data: None) -> Iterator[Callable[..., World]]:
    del clean_market_data
    clients: list[BinanceSpotRestClient | KrakenSpotRestClient] = []

    def build(
        targets: list[ScanTarget],
        *,
        exchange: SyntheticExchange | None = None,
        kraken_feed: SyntheticKraken | None = None,
    ) -> World:
        clock = Time()
        exchange = exchange or SyntheticExchange()
        kraken_feed = kraken_feed or SyntheticKraken()
        binance_client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(exchange),
            clock=clock,
            sleep=lambda _seconds: None,
        )
        kraken_client = KrakenSpotRestClient(
            KrakenRestConfig(max_attempts=1, min_request_interval_seconds=0.0),
            transport=httpx2.MockTransport(kraken_feed),
            clock=clock,
            sleep=lambda _seconds: None,
        )
        clients.extend([binance_client, kraken_client])
        scanner = CandleScanner(
            create_session_factory(market_data_engine),
            {"BINANCE": binance_client, "KRAKEN": kraken_client},
            targets,
            clock=clock,
        )
        return scanner, exchange, kraken_feed, clock

    yield build
    for client in clients:
        client.close()


def outcomes(reports: tuple[ScanReport, ...]) -> list[tuple[str, ScanOutcome]]:
    return [(r.target.label, r.outcome) for r in reports]


def rate_limited(reports: tuple[ScanReport, ...]) -> list[ScanReport]:
    return [r for r in reports if r.detail == "RATE_LIMITED"]


# -- the pass that meets the limit -----------------------------------------------------------------


def test_the_first_rate_limited_answer_stops_every_other_series_of_that_source(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=429)
    scanner, exchange, _, _ = world([binance(BTC), binance(ETH), binance(SOL)], exchange=exchange)

    reports = scanner.scan_once()

    assert outcomes(reports) == [
        ("BINANCE BTC/USDT 1m", ScanOutcome.PROVIDER_UNAVAILABLE),
        ("BINANCE ETH/USDT 1m", ScanOutcome.COOLING_DOWN),
        ("BINANCE SOL/USDT 1m", ScanOutcome.COOLING_DOWN),
    ]
    assert len(exchange.requests) == 1  # one request, the one that was refused; nothing after
    assert [r.requests for r in reports] == [1, 0, 0]
    assert "not asked again before" in (reports[1].detail or "")


def test_a_ban_answer_also_stops_the_source(world: Callable[..., World]) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=418)
    scanner, exchange, _, _ = world([binance(BTC), binance(ETH)], exchange=exchange)

    reports = scanner.scan_once()

    assert reports[1].outcome is ScanOutcome.COOLING_DOWN
    assert len(exchange.requests) == 1


def test_another_source_in_the_same_pass_is_not_affected(world: Callable[..., World]) -> None:
    exchange = SyntheticExchange(failing_calls=ALWAYS, fail_status=429)
    scanner, exchange, feed, _ = world(
        [binance(BTC), kraken(BTC), binance(ETH), kraken(ETH)], exchange=exchange
    )

    reports = scanner.scan_once()

    assert outcomes(reports) == [
        ("BINANCE BTC/USDT 1m", ScanOutcome.PROVIDER_UNAVAILABLE),
        ("KRAKEN BTC/USDT 1m", ScanOutcome.SYNCED),
        ("BINANCE ETH/USDT 1m", ScanOutcome.COOLING_DOWN),
        ("KRAKEN ETH/USDT 1m", ScanOutcome.SYNCED),
    ]
    assert len(exchange.requests) == 1
    assert len(feed.requests) == 2


def test_kraken_being_rate_limited_stops_kraken_and_leaves_binance_alone(
    world: Callable[..., World],
) -> None:
    feed = SyntheticKraken(errors_by_call={1: ["EGeneral:Too many requests"]})
    scanner, _, feed, _ = world(
        [kraken(BTC), binance(BTC), kraken(ETH), binance(ETH)], kraken_feed=feed
    )

    reports = scanner.scan_once()

    assert outcomes(reports) == [
        ("KRAKEN BTC/USDT 1m", ScanOutcome.PROVIDER_UNAVAILABLE),
        ("BINANCE BTC/USDT 1m", ScanOutcome.SYNCED),
        ("KRAKEN ETH/USDT 1m", ScanOutcome.COOLING_DOWN),
        ("BINANCE ETH/USDT 1m", ScanOutcome.SYNCED),
    ]
    assert len(feed.requests) == 1


# -- the cooldown ----------------------------------------------------------------------------------


def test_no_request_is_made_while_the_source_cools_down(world: Callable[..., World]) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=429)
    scanner, exchange, _, clock = world([binance(BTC), binance(ETH)], exchange=exchange)
    scanner.scan_once()
    assert len(exchange.requests) == 1

    for _ in range(5):  # every minute for five minutes: still cooling (first cooldown is 2)
        clock.move(20)
        reports = scanner.scan_once()
        assert {r.outcome for r in reports} == {ScanOutcome.COOLING_DOWN}
    assert len(exchange.requests) == 1


def test_after_the_cooldown_exactly_one_request_probes_the_source(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=ALWAYS, fail_status=429)
    scanner, exchange, _, clock = world(
        [binance(BTC), binance(ETH), binance(SOL)], exchange=exchange
    )
    scanner.scan_once()

    clock.move(RATE_LIMIT_COOLDOWN_SECONDS[0] - 1)
    scanner.scan_once()
    assert len(exchange.requests) == 1  # one second early: nothing

    clock.move(1)
    reports = scanner.scan_once()
    assert len(exchange.requests) == 2  # the probe, and only the probe
    assert outcomes(reports) == [
        ("BINANCE BTC/USDT 1m", ScanOutcome.PROVIDER_UNAVAILABLE),
        ("BINANCE ETH/USDT 1m", ScanOutcome.COOLING_DOWN),
        ("BINANCE SOL/USDT 1m", ScanOutcome.COOLING_DOWN),
    ]


def test_the_cooldown_doubles_while_the_source_keeps_refusing_and_stops_growing(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=ALWAYS, fail_status=429)
    scanner, exchange, _, clock = world([binance(BTC)], exchange=exchange)
    scanner.scan_once()  # refused: cooldown 1
    asked = len(exchange.requests)

    waits = [*RATE_LIMIT_COOLDOWN_SECONDS, RATE_LIMIT_COOLDOWN_SECONDS[-1]]  # capped at 1800
    for seconds in waits:
        clock.move(seconds - 1)
        scanner.scan_once()
        assert len(exchange.requests) == asked, f"asked {seconds - 1}s in, too early"
        clock.move(1)
        scanner.scan_once()
        asked += 1
        assert len(exchange.requests) == asked, f"did not probe after {seconds}s"


def test_the_schedule_is_two_minutes_doubling_to_a_thirty_minute_ceiling() -> None:
    assert RATE_LIMIT_COOLDOWN_SECONDS == (120, 240, 480, 960, 1800)
    assert RATE_LIMIT_COOLDOWN_SECONDS[-1] == 30 * 60


def test_a_probe_that_goes_through_reopens_the_whole_source(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=429)
    scanner, exchange, _, clock = world(
        [binance(BTC), binance(ETH), binance(SOL)], exchange=exchange
    )
    scanner.scan_once()

    clock.move(RATE_LIMIT_COOLDOWN_SECONDS[0])
    reports = scanner.scan_once()

    assert [r.outcome for r in reports] == [ScanOutcome.SYNCED] * 3  # BTC probed, the rest follow
    assert len(exchange.requests) == 1 + 3


def test_after_a_recovery_the_next_limit_starts_again_at_two_minutes(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1, 2, 4}), fail_status=429)
    scanner, exchange, _, clock = world([binance(BTC), binance(ETH)], exchange=exchange)
    scanner.scan_once()  # call 1 refused: cooldown 120
    clock.move(120)
    scanner.scan_once()  # call 2 refused: cooldown 240
    clock.move(240)
    scanner.scan_once()  # call 3 (BTC) and 4 (ETH: refused): recovered on BTC, limited on ETH
    calls = len(exchange.requests)

    # ETH's refusal after the recovery is the first of a new streak: 120 s, not 480.
    clock.move(119)
    scanner.scan_once()
    assert len(exchange.requests) == calls
    clock.move(1)
    scanner.scan_once()
    assert len(exchange.requests) > calls


def test_a_refused_probe_doubles_the_cooldown(world: Callable[..., World]) -> None:
    exchange = SyntheticExchange(failing_calls=ALWAYS, fail_status=429)
    scanner, exchange, _, clock = world([binance(BTC), binance(ETH)], exchange=exchange)
    scanner.scan_once()  # BTC refused

    clock.move(RATE_LIMIT_COOLDOWN_SECONDS[0])
    scanner.scan_once()  # the probe is refused again: cooldown doubles
    clock.move(RATE_LIMIT_COOLDOWN_SECONDS[0])  # 120 s into a doubled 240 s cooldown
    reports = scanner.scan_once()

    assert {r.outcome for r in reports} == {ScanOutcome.COOLING_DOWN}


# -- what does not open the cooldown ---------------------------------------------------------------


def test_a_server_error_does_not_stop_the_source(world: Callable[..., World]) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=503)
    scanner, exchange, _, _ = world([binance(BTC), binance(ETH), binance(SOL)], exchange=exchange)

    reports = scanner.scan_once()

    assert reports[0].outcome is ScanOutcome.PROVIDER_UNAVAILABLE
    assert [r.outcome for r in reports[1:]] == [ScanOutcome.SYNCED, ScanOutcome.SYNCED]
    assert len(exchange.requests) == 3  # every series was still tried


def test_a_provider_that_is_down_is_still_tried_again_on_the_next_pass(
    world: Callable[..., World],
) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=503)
    scanner, exchange, _, clock = world([binance(BTC)], exchange=exchange)
    scanner.scan_once()
    clock.move(60)

    assert scanner.scan_once()[0].outcome is ScanOutcome.SYNCED  # no cooldown to wait out


# -- state and logs --------------------------------------------------------------------------------


def test_the_recorded_state_is_untouched_while_a_source_cools_down(
    world: Callable[..., World], market_data_engine: Engine
) -> None:
    exchange = SyntheticExchange(failing_calls=ALWAYS, fail_status=429)
    scanner, exchange, _, clock = world([binance(BTC), binance(ETH)], exchange=exchange)
    scanner.scan_once()

    def failures() -> dict[str, int]:
        with create_session_factory(market_data_engine)() as session:
            rows = session.execute(select(MarketDataSyncState)).scalars().all()
            return {str(row.instrument_id): row.consecutive_failures for row in rows}

    after_first = failures()
    assert list(after_first.values()) == [1]  # BTC's refused attempt is on record; ETH has none

    for _ in range(3):
        clock.move(30)
        scanner.scan_once()
    assert failures() == after_first  # skipped passes are not attempts and add no failures


def test_the_limit_is_logged_once_with_its_cooldown_and_the_recovery_when_it_ends(
    world: Callable[..., World], caplog: pytest.LogCaptureFixture
) -> None:
    exchange = SyntheticExchange(failing_calls=frozenset({1}), fail_status=429)
    scanner, exchange, _, clock = world(
        [binance(BTC), binance(ETH), binance(SOL)], exchange=exchange
    )

    with caplog.at_level(logging.INFO, logger="freyja_backend.application.candle_scanner"):
        scanner.scan_once()
        scanner.scan_once()  # cooling: no new line for the same limit
        clock.move(RATE_LIMIT_COOLDOWN_SECONDS[0])
        scanner.scan_once()

    limited = [r for r in caplog.records if r.getMessage() == "candle_source_rate_limited"]
    recovered = [r for r in caplog.records if r.getMessage() == "candle_source_recovered"]
    assert len(limited) == 1
    assert limited[0].__dict__["source"] == "BINANCE"
    assert limited[0].__dict__["cooldown_seconds"] == 120
    assert limited[0].__dict__["streak"] == 1
    assert len(recovered) == 1


def test_the_adapter_log_says_which_kind_of_refusal_it_was(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A temporary limit (429) and a ban (418) look the same as RATE_LIMITED; the detail is
    what tells them apart when reading the logs of a live service."""
    for status, expected in ((429, "rate limited (429)"), (418, "provider banned this IP (418)")):
        caplog.clear()
        client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(lambda _r, s=status: httpx2.Response(s)),
            clock=lambda: NOW,
            sleep=lambda _seconds: None,
        )
        with caplog.at_level(logging.WARNING), client:
            client.get_closed_candles(BTC, M1, limit=5)
        record = next(r for r in caplog.records if r.getMessage() == "market_data_unavailable")
        assert record.__dict__["issue"] == "RATE_LIMITED"
        assert record.__dict__["detail"] == expected
        assert "Retry-After" not in caplog.text or status == 429  # only fixed text, no payloads


def test_skipped_series_are_a_failure_in_the_pass_summary() -> None:
    assert ScanOutcome.COOLING_DOWN in _FAILURE_OUTCOMES
