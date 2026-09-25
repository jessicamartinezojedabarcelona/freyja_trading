"""Kraken as a second candle source, against real PostgreSQL (MARKET-DATA-KRAKEN-REST-001).

Only Kraken itself is simulated (a deterministic OHLC endpoint that behaves like the real
one: the latest 720 closed candles plus the one in progress, no limit, no end). The Kraken
adapter, the scanner, the sync service, the advisory locks and the database are real, and
every assertion reads back from PostgreSQL.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from uuid import UUID

import httpx2
import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from freyja_backend.application import market_data_query_service
from freyja_backend.application.candle_scanner import (
    CandleScanner,
    ScanOutcome,
    ScanReport,
    ScanTarget,
)
from freyja_backend.db.models import Candle, DataSource, MarketDataSyncState
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import CandleProvider, InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    HISTORY_CANDLES,
    KrakenRestConfig,
    KrakenSpotRestClient,
)
from tests.market_data_support import BTC, M1, NOW, SyntheticExchange, SyntheticKraken

KRAKEN = "KRAKEN"
BINANCE = "BINANCE"
MINUTE = timedelta(minutes=1)


class Time:
    """A clock the test moves by hand; the providers and the scanner share it."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def target(
    source: str = KRAKEN, instrument: InstrumentRef = BTC, timeframe: Timeframe = M1
) -> ScanTarget:
    return ScanTarget(source, instrument, timeframe)


@pytest.fixture
def world(
    market_data_engine: Engine, clean_market_data: None
) -> Iterator[Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]]]:
    del clean_market_data
    clients: list[CandleProvider] = []

    def build(
        targets: list[ScanTarget] | None = None,
        *,
        kraken: SyntheticKraken | None = None,
        max_attempts: int = 1,
    ) -> tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]:
        clock = Time()
        kraken = kraken or SyntheticKraken()
        binance = SyntheticExchange()
        kraken_client = KrakenSpotRestClient(
            KrakenRestConfig(max_attempts=max_attempts, min_request_interval_seconds=0.0),
            transport=httpx2.MockTransport(kraken),
            clock=clock,
            sleep=lambda _seconds: None,
        )
        binance_client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(binance),
            clock=clock,
            sleep=lambda _seconds: None,
        )
        clients.extend([kraken_client, binance_client])
        scanner = CandleScanner(
            create_session_factory(market_data_engine),
            {KRAKEN: kraken_client, BINANCE: binance_client},
            targets or [target()],
            clock=clock,
        )
        return scanner, kraken, binance, clock

    yield build
    for client in clients:
        client.close()  # type: ignore[attr-defined]


def stored_opens(engine: Engine, source: str = KRAKEN) -> list[datetime]:
    with create_session_factory(engine)() as session:
        rows = session.execute(
            select(Candle.open_time)
            .join(DataSource, DataSource.id == Candle.data_source_id)
            .where(DataSource.code == source)
            .order_by(Candle.open_time)
        ).scalars()
        return [row.astimezone(UTC) for row in rows]


def advance(clock: Time, kraken: SyntheticKraken, to: datetime) -> None:
    clock.now = to
    kraken.set_now(to)


def only(reports: tuple[ScanReport, ...]) -> ScanReport:
    assert len(reports) == 1
    return reports[0]


def holes(opens: list[datetime]) -> list[tuple[datetime, int]]:
    """(open time after which candles are missing, how many) for a 1m series."""
    return [
        (before, int((after - before) / MINUTE) - 1)
        for before, after in pairwise(opens)
        if after - before != MINUTE
    ]


# -- the first pass and staying current ------------------------------------------------


def test_the_first_pass_stores_the_latest_candles_with_one_request(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    scanner, kraken, _, _ = world()

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.SYNCED
    # The scanner asks for its usual 500; Kraken has 720 (+ the open one) and the adapter
    # keeps the most recent 500 closed ones.
    assert (report.inserted, report.requests) == (500, 1)
    assert len(kraken.requests) == 1
    opens = stored_opens(market_data_engine)
    assert len(opens) == 500
    assert opens[-1] == datetime(2026, 9, 24, 12, 6, tzinfo=UTC)  # 12:07 is still open
    assert holes(opens) == []


def test_the_request_uses_the_provider_symbol_from_the_catalog_mapping(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
) -> None:
    scanner, kraken, _, _ = world()
    only(scanner.scan_once())
    assert kraken.requests[0].url.params["pair"] == "XBTUSDT"  # Kraken's name for BTC


def test_a_series_that_is_up_to_date_makes_no_request_at_all(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
) -> None:
    scanner, kraken, _, _ = world()
    scanner.scan_once()
    requests_before = len(kraken.requests)

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.UP_TO_DATE
    assert len(kraken.requests) == requests_before


def test_a_few_new_candles_are_fetched_and_only_the_new_ones_are_added(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    scanner, kraken, _, clock = world()
    scanner.scan_once()
    advance(clock, kraken, NOW + 3 * MINUTE)

    report = only(scanner.scan_once())

    assert (report.outcome, report.inserted) == (ScanOutcome.SYNCED, 3)
    assert holes(stored_opens(market_data_engine)) == []


# -- catching up after the service slept ----------------------------------------------


def test_a_sleep_within_what_kraken_still_serves_is_caught_up_without_a_hole(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    scanner, kraken, _, clock = world()
    scanner.scan_once()
    advance(clock, kraken, NOW + 600 * MINUTE)  # 10 h: more than a "recent" pass, less than 12 h

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.SYNCED
    assert report.requests == 1
    assert holes(stored_opens(market_data_engine)) == []


def test_a_sleep_beyond_kraken_s_horizon_leaves_a_declared_hole_never_invented_candles(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    """Kraken keeps only its latest 720 candles (12 h of 1m). After a longer sleep the
    older ones are out of reach: the scanner takes what Kraken still has, in ONE request
    (never more than a page of 720), and the series shows an honest hole."""
    scanner, kraken, _, clock = world()
    scanner.scan_once()
    last_before = stored_opens(market_data_engine)[-1]
    advance(clock, kraken, NOW + 2000 * MINUTE)  # far beyond 12 h

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.SYNCED
    assert (report.inserted, report.requests) == (HISTORY_CANDLES, 1)
    opens = stored_opens(market_data_engine)
    (hole,) = holes(opens)
    assert hole[0] == last_before
    # Exactly the candles Kraken cannot serve any more are missing: nothing was made up to
    # fill them and nothing came from another source.
    newest = opens[-1]
    oldest_served = newest - (HISTORY_CANDLES - 1) * MINUTE
    assert opens[opens.index(last_before) + 1] == oldest_served
    assert hole[1] == int((oldest_served - last_before) / MINUTE) - 1
    # No request asked for anything older than what Kraken can serve.
    since = int(kraken.requests[-1].url.params["since"])
    assert since == int(oldest_served.timestamp()) - 1


def test_the_hole_is_visible_to_readers_as_a_gap(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    scanner, kraken, _, clock = world()
    scanner.scan_once()
    advance(clock, kraken, NOW + 2000 * MINUTE)
    scanner.scan_once()

    with create_session_factory(market_data_engine)() as session:
        series = market_data_query_service.get_candle_series(
            session,
            instrument_id=_instrument_id(session),
            data_source_code=KRAKEN,
            timeframe_code="1m",
            start=None,
            end=None,
            limit=1000,
            now=clock.now,
        )
    assert series.gaps, "a hole in the stored series must be reported, not hidden"


def _instrument_id(session: Session) -> UUID:
    found: UUID = session.execute(
        text("SELECT instrument_id FROM freyja2_instruments WHERE canonical_symbol = 'BTC/USDT'")
    ).scalar_one()
    return found


# -- failures ----------------------------------------------------------------------------


def test_a_kraken_outage_is_reported_and_recorded_and_stores_nothing(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    kraken = SyntheticKraken(errors_by_call={1: ["EGeneral:Too many requests"]})
    scanner, _, _, _ = world(kraken=kraken)

    report = only(scanner.scan_once())

    assert report.outcome is ScanOutcome.PROVIDER_UNAVAILABLE
    assert stored_opens(market_data_engine) == []
    with create_session_factory(market_data_engine)() as session:
        (state,) = session.execute(select(MarketDataSyncState)).scalars().all()
        assert state.consecutive_failures == 1  # the API can say "provider failing"


def test_a_series_that_failed_recovers_on_the_next_pass(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    kraken = SyntheticKraken(errors_by_call={1: ["EService:Unavailable"]})
    scanner, _, _, _ = world(kraken=kraken)

    assert only(scanner.scan_once()).outcome is ScanOutcome.PROVIDER_UNAVAILABLE
    assert only(scanner.scan_once()).outcome is ScanOutcome.SYNCED
    assert len(stored_opens(market_data_engine)) == 500


# -- two sources, two series -----------------------------------------------------------------


def test_the_same_instrument_and_period_from_two_sources_are_two_separate_series(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    scanner, kraken, binance, clock = world([target(BINANCE), target(KRAKEN)])

    reports = scanner.scan_once()

    assert [(r.target.source_code, r.outcome) for r in reports] == [
        (BINANCE, ScanOutcome.SYNCED),
        (KRAKEN, ScanOutcome.SYNCED),
    ]
    binance_opens = stored_opens(market_data_engine, BINANCE)
    kraken_opens = stored_opens(market_data_engine, KRAKEN)
    # Each source keeps what it sent: Binance's 499 and Kraken's 500 are not merged, and
    # neither replaced the other even though they cover the same instrument and period.
    assert (len(binance_opens), len(kraken_opens)) == (499, 500)
    assert len(binance.requests) == 1
    assert len(kraken.requests) == 1

    # A later pass that only Kraken needs does not touch Binance's series.
    advance(clock, kraken, NOW + 2 * MINUTE)
    binance.set_now(NOW + 2 * MINUTE)
    scanner.scan_once()
    assert len(stored_opens(market_data_engine, KRAKEN)) == 502
    assert len(stored_opens(market_data_engine, BINANCE)) == 501


def test_kraken_being_down_does_not_affect_binance_s_series(
    world: Callable[..., tuple[CandleScanner, SyntheticKraken, SyntheticExchange, Time]],
    market_data_engine: Engine,
) -> None:
    kraken = SyntheticKraken(errors_by_call={1: ["EService:Unavailable"]})
    scanner, _, _, _ = world([target(KRAKEN), target(BINANCE)], kraken=kraken)

    outcomes = {r.target.source_code: r.outcome for r in scanner.scan_once()}

    assert outcomes == {KRAKEN: ScanOutcome.PROVIDER_UNAVAILABLE, BINANCE: ScanOutcome.SYNCED}
    assert stored_opens(market_data_engine, KRAKEN) == []
    assert len(stored_opens(market_data_engine, BINANCE)) == 499
