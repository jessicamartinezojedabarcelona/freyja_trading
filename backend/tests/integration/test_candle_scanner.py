"""Candle scanner against real PostgreSQL (MARKET-DATA-SCANNER-001).

Only the external provider is simulated (a deterministic public-klines endpoint behind
the real adapter). The scanner, the sync service, the advisory locks and the database are
real, and every assertion reads back from PostgreSQL.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import httpx2
import pytest
from sqlalchemy import Engine, create_engine, func, select

from freyja_backend.application.candle_scanner import (
    CandleScanner,
    ScanOutcome,
    ScanReport,
    ScanTarget,
    advisory_lock_key,
)
from freyja_backend.db.models import Candle, MarketDataSyncState
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import (
    CandleBatch,
    DataQuality,
    InstrumentRef,
    MetadataResult,
    Provenance,
    Timeframe,
)
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from tests.market_data_support import BTC, ETH, M1, NOW, SyntheticExchange

SOURCE = "BINANCE"
MINUTE = timedelta(minutes=1)


class Time:
    """A clock the test moves by hand; the provider and the scanner share it."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def target(instrument: InstrumentRef = BTC, timeframe: Timeframe = M1) -> ScanTarget:
    return ScanTarget(SOURCE, instrument, timeframe)


@pytest.fixture
def world(
    market_data_engine: Engine, clean_market_data: None
) -> Iterator[Callable[..., tuple[CandleScanner, SyntheticExchange, Time]]]:
    del clean_market_data
    clients: list[BinanceSpotRestClient] = []

    def build(
        targets: list[ScanTarget] | None = None,
        *,
        exchange: SyntheticExchange | None = None,
        **scanner_options: int,
    ) -> tuple[CandleScanner, SyntheticExchange, Time]:
        clock = Time()
        exchange = exchange or SyntheticExchange()
        client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(exchange),
            clock=clock,
            sleep=lambda _seconds: None,
        )
        clients.append(client)
        scanner = CandleScanner(
            create_session_factory(market_data_engine),
            {SOURCE: client},
            targets or [target()],
            clock=clock,
            **scanner_options,
        )
        return scanner, exchange, clock

    yield build
    for client in clients:
        client.close()


def stored_opens(engine: Engine) -> list[datetime]:
    factory = create_session_factory(engine)
    with factory() as session:
        rows = session.execute(select(Candle.open_time).order_by(Candle.open_time)).scalars()
        return [row.astimezone(UTC) for row in rows]


def advance(clock: Time, exchange: SyntheticExchange, to: datetime) -> None:
    clock.now = to
    exchange.set_now(to)


def only(reports: tuple[ScanReport, ...]) -> ScanReport:
    assert len(reports) == 1
    return reports[0]


# -- the first pass ----------------------------------------------------------------------


def test_the_first_pass_stores_the_latest_candles_with_one_request(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, exchange, _ = world()

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.SYNCED
    # 500 requested, the newest of them (12:07) is still open and is not stored.
    assert (report.inserted, report.requests) == (499, 1)
    assert len(exchange.requests) == 1
    opens = stored_opens(market_data_engine)
    assert len(opens) == 499
    assert opens[-1] == datetime(2026, 9, 24, 12, 6, tzinfo=UTC)  # 12:07 is still open


def test_a_series_that_is_up_to_date_makes_no_request_at_all(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]],
) -> None:
    scanner, exchange, _ = world()
    scanner.scan_once()
    sent = len(exchange.requests)

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.UP_TO_DATE
    assert (report.inserted, report.requests) == (0, 0)
    assert len(exchange.requests) == sent  # not even a look at the provider


# -- keeping up ---------------------------------------------------------------------------


def test_a_few_new_candles_are_fetched_and_only_the_new_ones_are_added(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, exchange, clock = world()
    scanner.scan_once()

    advance(clock, exchange, NOW + timedelta(minutes=3))  # 12:10:30 -> 12:07..12:09 closed
    report = only(scanner.scan_once())

    assert (report.outcome, report.inserted, report.requests) == (ScanOutcome.SYNCED, 3, 1)
    assert stored_opens(market_data_engine)[-1] == datetime(2026, 9, 24, 12, 9, tzinfo=UTC)


def test_after_a_long_sleep_it_catches_up_page_by_page_without_leaving_a_hole(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, exchange, clock = world()
    scanner.scan_once()
    before = len(exchange.requests)

    advance(clock, exchange, NOW + timedelta(days=2))
    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.SYNCED
    assert report.inserted == 2880  # two days of one-minute candles
    assert report.requests == 3  # 1000 + 1000 + 880
    assert len(exchange.requests) - before == 3
    opens = stored_opens(market_data_engine)
    assert all(b - a == MINUTE for a, b in pairwise(opens))  # contiguous
    assert opens[-1] == datetime(2026, 9, 26, 12, 6, tzinfo=UTC)


def test_a_catch_up_is_bounded_per_pass_and_the_next_pass_resumes_where_it_stopped(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, exchange, clock = world(max_catchup_candles=1000)
    scanner.scan_once()
    advance(clock, exchange, NOW + timedelta(days=2))

    passes = [only(scanner.scan_once()) for _ in range(3)]

    assert [p.outcome for p in passes] == [
        ScanOutcome.PARTIAL,
        ScanOutcome.PARTIAL,
        ScanOutcome.SYNCED,
    ]
    assert [p.inserted for p in passes] == [1000, 1000, 880]
    opens = stored_opens(market_data_engine)
    assert all(b - a == MINUTE for a, b in pairwise(opens))
    assert only(scanner.scan_once()).outcome is ScanOutcome.UP_TO_DATE


# -- failures never stop the pass -----------------------------------------------------------


def test_a_provider_failure_is_reported_and_recorded_and_the_other_series_still_run(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, _, _ = world(
        [target(BTC), target(ETH)], exchange=SyntheticExchange(failing_calls=frozenset({1}))
    )

    first, second = scanner.scan_once()

    assert first.outcome is ScanOutcome.PROVIDER_UNAVAILABLE
    assert first.inserted == 0
    assert second.outcome is ScanOutcome.SYNCED  # ETH was not held up by BTC
    with create_session_factory(market_data_engine)() as session:
        statuses = list(session.execute(select(MarketDataSyncState.last_status)).scalars())
    assert sorted(statuses) == [DataQuality.OK, DataQuality.UNAVAILABLE]  # the failure is visible


def test_a_series_that_failed_recovers_on_the_next_pass(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]],
) -> None:
    scanner, _, _ = world(exchange=SyntheticExchange(failing_calls=frozenset({1})))

    assert only(scanner.scan_once()).outcome is ScanOutcome.PROVIDER_UNAVAILABLE
    assert only(scanner.scan_once()).outcome is ScanOutcome.SYNCED


def test_an_instrument_missing_from_the_catalog_or_without_a_provider_is_not_configured(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]],
) -> None:
    unknown = target(InstrumentRef("CRYPTO", "SPOT", "DOGE/USDT"))
    no_provider = ScanTarget("SOMEWHERE_ELSE", BTC, M1)
    scanner, exchange, _ = world([unknown, no_provider, target()])

    reports = scanner.scan_once()

    assert [r.outcome for r in reports] == [
        ScanOutcome.NOT_CONFIGURED,
        ScanOutcome.NOT_CONFIGURED,
        ScanOutcome.SYNCED,  # and the valid one still ran
    ]
    assert len(exchange.requests) == 1


class _WrongSymbolProvider:
    """A provider that answers for a different symbol than the catalog maps."""

    def get_closed_candles(
        self,
        instrument: InstrumentRef,
        timeframe: Timeframe,
        *,
        limit: int = 500,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CandleBatch:
        del limit, start, end
        return CandleBatch(
            instrument=instrument,
            timeframe=timeframe,
            candles=(),
            quality=DataQuality.OK,
            issues=(),
            provenance=Provenance(SOURCE, "/x", "NOT-THE-MAPPED-SYMBOL", NOW, NOW, 1),
        )

    def get_instrument_metadata(self, instrument: InstrumentRef) -> MetadataResult:
        raise NotImplementedError


def test_an_answer_that_does_not_match_the_catalog_is_rejected_and_stores_nothing(
    market_data_engine: Engine, clean_market_data: None
) -> None:
    del clean_market_data
    scanner = CandleScanner(
        create_session_factory(market_data_engine),
        {SOURCE: _WrongSymbolProvider()},
        [target()],
        clock=Time(),
    )

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.REJECTED
    assert stored_opens(market_data_engine) == []


def test_a_database_that_is_down_ends_the_pass_early_instead_of_hammering_it() -> None:
    dead: Engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none", connect_args={"connect_timeout": 2}
    )
    factory = create_session_factory(dead)
    scanner = CandleScanner(
        factory, {SOURCE: _WrongSymbolProvider()}, [target(BTC), target(ETH), target()]
    )

    reports = scanner.scan_once()
    dead.dispose()

    assert [r.outcome for r in reports] == [
        ScanOutcome.DATABASE_ERROR,
        ScanOutcome.NOT_ATTEMPTED,
        ScanOutcome.NOT_ATTEMPTED,
    ]


# -- two scanners on one database -------------------------------------------------------------


def test_a_series_another_scanner_is_working_on_is_left_alone_until_it_finishes(
    world: Callable[..., tuple[CandleScanner, SyntheticExchange, Time]], market_data_engine: Engine
) -> None:
    scanner, exchange, _ = world()
    key = advisory_lock_key(target())

    with market_data_engine.connect() as other, other.begin():
        other.execute(select(func.pg_advisory_xact_lock(key)))  # the other scanner's lock
        locked = only(scanner.scan_once())
        assert locked.outcome is ScanOutcome.LOCKED_BY_ANOTHER
        assert exchange.requests == []  # and it did not fetch it either

    assert only(scanner.scan_once()).outcome is ScanOutcome.SYNCED  # lock released with the commit


def test_lock_keys_are_stable_signed_64_bit_and_distinct_per_series() -> None:
    targets = [
        ScanTarget(SOURCE, InstrumentRef("CRYPTO", "SPOT", f"{base}/USDT"), timeframe)
        for base in ("BTC", "ETH", "SOL", "XRP")
        for timeframe in Timeframe
    ]

    keys = [advisory_lock_key(t) for t in targets]

    assert keys == [advisory_lock_key(t) for t in targets]
    assert len(set(keys)) == len(targets)
    assert all(-(2**63) <= key < 2**63 for key in keys)


# -- construction -------------------------------------------------------------------------------


def test_the_limits_are_validated(market_data_engine: Engine) -> None:
    factory = create_session_factory(market_data_engine)
    for recent, catchup in ((0, 5000), (1001, 5000), (500, 0)):
        with pytest.raises(ValueError):
            CandleScanner(factory, {}, [], recent_limit=recent, max_catchup_candles=catchup)
