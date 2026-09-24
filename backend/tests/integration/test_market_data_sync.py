"""Market-data sync and backfill against real PostgreSQL.

The provider is the only simulated part (see tests/market_data_support.py): the
real adapter parses its answers, the real services validate and store them, and
every assertion reads back from a real database migrated to head.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from freyja_backend.application import market_data_service
from freyja_backend.application.market_data_service import (
    MarketDataConfigurationError,
    MarketDataIntegrityError,
    backfill_candles,
    sync_candles,
)
from freyja_backend.db.models import Candle, MarketDataSyncState
from freyja_backend.domain.market_data import (
    CandleBatch,
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    MetadataResult,
    Provenance,
    QualityIssueCode,
    Timeframe,
)
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from tests.market_data_support import BTC, ETH, M1, M5, NOW, Rows, SyntheticExchange, at

SOURCE = "BINANCE"
WINDOW_START = at(11, 0)
WINDOW_END = at(11, 50)  # ten 5-minute candles: 11:00 .. 11:45


@pytest.fixture
def make_provider() -> Iterator[Callable[..., BinanceSpotRestClient]]:
    created: list[BinanceSpotRestClient] = []

    def build(
        handler: Callable[[httpx2.Request], httpx2.Response], *, now: datetime = NOW
    ) -> BinanceSpotRestClient:
        client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(handler),
            clock=lambda: now,
            sleep=lambda _seconds: None,
        )
        created.append(client)
        return client

    yield build
    for client in created:
        client.close()


def stored(session: Session) -> list[Candle]:
    query = select(Candle).order_by(Candle.open_time).execution_options(populate_existing=True)
    return list(session.execute(query).scalars())


def state(session: Session) -> MarketDataSyncState:
    query = select(MarketDataSyncState).execution_options(populate_existing=True)
    return session.execute(query).scalar_one()


def snapshot(session: Session) -> list[tuple[object, ...]]:
    return [
        (
            c.open_time,
            c.close_time,
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.quality,
            c.received_at,
        )
        for c in stored(session)
    ]


def sync_recent(
    session: Session,
    provider: BinanceSpotRestClient,
    *,
    instrument: InstrumentRef = BTC,
    timeframe: Timeframe = M1,
    limit: int = 5,
) -> market_data_service.SyncResult:
    return sync_candles(
        session,
        provider,
        source_code=SOURCE,
        instrument=instrument,
        timeframe=timeframe,
        limit=limit,
    )


# -- storing what the provider delivered ---------------------------------------------


def test_stores_closed_candles_exactly_with_provenance(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    result = sync_recent(market_data_session, make_provider(SyntheticExchange()))

    # limit=5 covers 12:03..12:07; the 12:07 candle is still open, so it is not stored.
    assert (result.inserted, result.unchanged, result.revised) == (4, 0, ())
    assert result.quality is DataQuality.OK
    assert [i.code for i in result.issues] == [QualityIssueCode.OPEN_CANDLE_EXCLUDED]

    candles = stored(market_data_session)
    assert [c.open_time for c in candles] == [at(12, m) for m in (3, 4, 5, 6)]
    assert all(c.open_time.utcoffset() == timedelta(0) for c in candles)
    assert all(c.close_time - c.open_time == timedelta(minutes=1) for c in candles)
    first = candles[0]
    open_ms = int(first.open_time.timestamp() * 1000)
    base = SyntheticExchange.price(open_ms, 60_000)
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        Decimal(f"{base}.1"),
        Decimal(base + 2),
        Decimal(base - 1),
        Decimal(base + 1),
        Decimal("10.5"),
    )
    assert all(c.quality is DataQuality.OK for c in candles)
    assert all(c.received_at == NOW for c in candles)
    assert {str(c.data_source_id) for c in candles} == {
        str(market_data_session.execute(text("SELECT id FROM freyja2_data_sources")).scalar_one())
    }


def test_repeating_the_same_ingestion_changes_nothing(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    provider = make_provider(SyntheticExchange())
    sync_recent(market_data_session, provider)
    before = snapshot(market_data_session)

    again = sync_recent(market_data_session, provider)

    assert (again.inserted, again.unchanged, again.revised) == (0, 4, ())
    assert again.quality is DataQuality.OK
    assert snapshot(market_data_session) == before
    assert market_data_session.execute(select(func.count()).select_from(Candle)).scalar_one() == 4


def test_overlapping_windows_add_only_the_new_candles_and_never_touch_old_ones(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    sync_recent(market_data_session, make_provider(SyntheticExchange()))
    before = snapshot(market_data_session)
    later = NOW + timedelta(minutes=2)  # 12:09:30 -> 12:07 and 12:08 have closed

    result = sync_recent(
        market_data_session, make_provider(SyntheticExchange(now=later), now=later), limit=7
    )

    assert (result.inserted, result.unchanged) == (2, 4)
    candles = stored(market_data_session)
    assert [c.open_time for c in candles] == [at(12, m) for m in (3, 4, 5, 6, 7, 8)]
    assert snapshot(market_data_session)[:4] == before  # old rows, including received_at, untouched
    assert [c.received_at for c in candles[4:]] == [later, later]


def test_a_different_value_for_a_stored_candle_is_reported_never_applied(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    sync_recent(market_data_session, make_provider(SyntheticExchange()))
    before = snapshot(market_data_session)
    target = int(at(12, 5).timestamp() * 1000)

    def revise(rows: Rows) -> Rows:
        return [
            [*r[:5], "99.00000000", *r[6:]] if r[0] == target else r for r in rows
        ]  # different volume

    result = sync_recent(market_data_session, make_provider(SyntheticExchange(mutate=revise)))

    assert (result.inserted, result.unchanged, result.revised) == (0, 3, (at(12, 5),))
    assert result.quality is DataQuality.DEGRADED
    assert QualityIssueCode.REVISED_CANDLE in {i.code for i in result.issues}
    assert snapshot(market_data_session) == before  # the confirmed candle was not rewritten
    recorded = state(market_data_session)
    assert recorded.last_status is DataQuality.DEGRADED
    assert "REVISED_CANDLE" in recorded.last_issue_codes


def test_a_degraded_batch_is_stored_marked_degraded_and_flagged_in_the_state(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    missing = int(at(12, 4).timestamp() * 1000)

    def drop_one(rows: Rows) -> Rows:
        return [r for r in rows if r[0] != missing]

    result = sync_recent(market_data_session, make_provider(SyntheticExchange(mutate=drop_one)))

    assert result.quality is DataQuality.DEGRADED
    candles = stored(market_data_session)
    assert [c.open_time for c in candles] == [at(12, 3), at(12, 5), at(12, 6)]
    assert all(c.quality is DataQuality.DEGRADED for c in candles)
    recorded = state(market_data_session)
    assert recorded.last_status is DataQuality.DEGRADED
    assert set(recorded.last_issue_codes) == {"GAP", "OPEN_CANDLE_EXCLUDED"}
    assert recorded.last_detail is not None and "1 candle(s) missing" in recorded.last_detail
    assert recorded.consecutive_failures == 0
    assert recorded.last_success_at == NOW


# -- provider failures ------------------------------------------------------------------


def test_failed_syncs_store_nothing_and_are_counted_until_one_succeeds(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    provider = make_provider(SyntheticExchange(failing_calls=frozenset({1, 2})))

    first = sync_recent(market_data_session, provider)
    assert first.quality is DataQuality.UNAVAILABLE
    assert (first.inserted, first.unchanged) == (0, 0)
    assert stored(market_data_session) == []
    recorded = state(market_data_session)
    assert recorded.last_status is DataQuality.UNAVAILABLE
    assert recorded.last_issue_codes == ["PROVIDER_ERROR"]
    assert (recorded.consecutive_failures, recorded.last_success_at) == (1, None)

    sync_recent(market_data_session, provider)
    assert state(market_data_session).consecutive_failures == 2

    recovered = sync_recent(market_data_session, provider)
    assert recovered.quality is DataQuality.OK
    recorded = state(market_data_session)
    assert (recorded.consecutive_failures, recorded.last_success_at) == (0, NOW)
    assert len(stored(market_data_session)) == 4


def test_a_failure_after_a_success_keeps_the_last_success_time(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    sync_recent(market_data_session, make_provider(SyntheticExchange()))
    later = NOW + timedelta(minutes=5)
    failing = make_provider(SyntheticExchange(now=later, failing_calls=frozenset({1})), now=later)

    sync_recent(market_data_session, failing)

    recorded = state(market_data_session)
    assert recorded.last_status is DataQuality.UNAVAILABLE
    assert recorded.last_attempt_at == later
    assert recorded.last_success_at == NOW
    assert recorded.consecutive_failures == 1
    assert len(stored(market_data_session)) == 4  # the earlier candles are still there


def test_an_invalid_response_stores_nothing(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    def truncate_rows(rows: Rows) -> Rows:
        return [r[:6] for r in rows]

    result = sync_recent(
        market_data_session, make_provider(SyntheticExchange(mutate=truncate_rows))
    )

    assert result.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in result.issues] == [QualityIssueCode.INVALID_RESPONSE]
    assert stored(market_data_session) == []
    assert state(market_data_session).last_issue_codes == ["INVALID_RESPONSE"]


# -- series never mix -----------------------------------------------------------------------


def test_series_are_kept_apart_by_instrument_and_timeframe(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    provider = make_provider(SyntheticExchange())
    sync_recent(market_data_session, provider, instrument=BTC, timeframe=M1)
    sync_recent(market_data_session, provider, instrument=BTC, timeframe=M5, limit=3)
    sync_recent(market_data_session, provider, instrument=ETH, timeframe=M1)

    rows = market_data_session.execute(
        text(
            "SELECT i.canonical_symbol || ' ' || t.code, count(*) FROM freyja2_candles c "
            "JOIN freyja2_instruments i ON i.instrument_id = c.instrument_id "
            "JOIN freyja2_timeframes t ON t.id = c.timeframe_id GROUP BY 1"
        )
    ).all()
    counts = {str(label): int(count) for label, count in rows}
    assert counts == {"BTC/USDT 1m": 4, "BTC/USDT 5m": 2, "ETH/USDT 1m": 4}
    assert (
        market_data_session.execute(
            select(func.count()).select_from(MarketDataSyncState)
        ).scalar_one()
        == 3
    )


# -- what may be synced at all -------------------------------------------------------------


@contextmanager
def altered(engine: Engine, change: str, restore: str) -> Iterator[None]:
    with engine.begin() as connection:
        connection.execute(text(change))
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text(restore))


def test_unknown_or_unmapped_series_are_refused_before_anything_is_fetched(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    exchange = SyntheticExchange()
    provider = make_provider(exchange)

    with pytest.raises(MarketDataConfigurationError, match="'KRAKEN' is not active"):
        sync_candles(
            market_data_session,
            provider,
            source_code="KRAKEN",
            instrument=BTC,
            timeframe=M1,
            limit=5,
        )
    unknown = InstrumentRef("CRYPTO", "SPOT", "DOGE/USDT")
    with pytest.raises(MarketDataConfigurationError, match="not active in the catalog"):
        sync_recent(market_data_session, provider, instrument=unknown)
    forex = InstrumentRef("FOREX", "SPOT", "EUR/USD")  # in the catalog, but BINANCE has no mapping
    with pytest.raises(MarketDataConfigurationError, match="no active analysis mapping"):
        sync_recent(market_data_session, provider, instrument=forex)

    assert exchange.requests == []
    assert stored(market_data_session) == []


def test_inactive_source_mapping_or_timeframe_association_is_refused(
    market_data_session: Session,
    market_data_engine: Engine,
    make_provider: Callable[..., BinanceSpotRestClient],
) -> None:
    exchange = SyntheticExchange()
    provider = make_provider(exchange)

    with (
        altered(
            market_data_engine,
            "UPDATE freyja2_data_sources SET is_active = false WHERE code = 'BINANCE'",
            "UPDATE freyja2_data_sources SET is_active = true WHERE code = 'BINANCE'",
        ),
        pytest.raises(MarketDataConfigurationError, match="not active"),
    ):
        sync_recent(market_data_session, provider)

    with (
        altered(
            market_data_engine,
            "UPDATE freyja2_data_source_instruments SET is_active = false",
            "UPDATE freyja2_data_source_instruments SET is_active = true",
        ),
        pytest.raises(MarketDataConfigurationError, match="no active analysis mapping"),
    ):
        sync_recent(market_data_session, provider)

    with (
        altered(
            market_data_engine,
            "UPDATE freyja2_instrument_timeframes SET is_active = false WHERE timeframe_id = "
            "(SELECT id FROM freyja2_timeframes WHERE code = '1m')",
            "UPDATE freyja2_instrument_timeframes SET is_active = true WHERE timeframe_id = "
            "(SELECT id FROM freyja2_timeframes WHERE code = '1m')",
        ),
        pytest.raises(MarketDataConfigurationError, match="not enabled for BTC/USDT"),
    ):
        sync_recent(market_data_session, provider)

    assert exchange.requests == []
    assert stored(market_data_session) == []


class _MislabelledProvider:
    """A provider that answers for another symbol than the catalog maps."""

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
        provenance = Provenance(SOURCE, "klines", "ETHUSDT", NOW, NOW, 1)
        return CandleBatch(instrument, timeframe, (), DataQuality.OK, (), provenance)

    def get_instrument_metadata(self, instrument: InstrumentRef) -> MetadataResult:
        raise NotImplementedError


def test_an_answer_that_does_not_match_the_catalog_mapping_is_rejected(
    market_data_session: Session,
) -> None:
    with pytest.raises(MarketDataIntegrityError, match="expected BINANCE/BTCUSDT"):
        sync_candles(
            market_data_session,
            _MislabelledProvider(),
            source_code=SOURCE,
            instrument=BTC,
            timeframe=M1,
        )
    assert stored(market_data_session) == []
    assert (
        market_data_session.execute(
            select(func.count()).select_from(MarketDataSyncState)
        ).scalar_one()
        == 0
    )


# -- backfill ---------------------------------------------------------------------------------


def backfill(
    session: Session,
    provider: BinanceSpotRestClient,
    *,
    start: datetime = WINDOW_START,
    end: datetime = WINDOW_END,
    page_limit: int = 3,
    max_candles: int = 10_000,
) -> market_data_service.BackfillResult:
    return backfill_candles(
        session,
        provider,
        source_code=SOURCE,
        instrument=BTC,
        timeframe=M5,
        start=start,
        end=end,
        page_limit=page_limit,
        max_candles=max_candles,
        clock=lambda: NOW,
    )


def test_backfill_fills_the_window_page_by_page_and_is_repeatable(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    exchange = SyntheticExchange()
    provider = make_provider(exchange)

    first = backfill(market_data_session, provider)

    assert (first.pages, first.inserted, first.unchanged, first.revised) == (4, 10, 0, 0)
    assert first.completed and first.quality is DataQuality.OK
    candles = stored(market_data_session)
    assert [c.open_time for c in candles] == [at(11, 5 * n) for n in range(10)]
    # Every page is a bounded request for exactly its own window.
    starts = [int(r.url.params["startTime"]) for r in exchange.requests]
    assert starts == [int(at(11, m).timestamp() * 1000) for m in (0, 15, 30, 45)]
    assert all(int(r.url.params["limit"]) == 3 for r in exchange.requests)

    before = snapshot(market_data_session)
    again = backfill(market_data_session, provider)
    assert (again.pages, again.inserted, again.unchanged) == (4, 0, 10)
    assert snapshot(market_data_session) == before


def test_an_interrupted_backfill_keeps_its_progress_and_resumes(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    broken = make_provider(SyntheticExchange(failing_calls=frozenset({3})))

    partial = backfill(market_data_session, broken)

    assert (partial.pages, partial.inserted, partial.completed) == (3, 6, False)
    assert partial.quality is DataQuality.UNAVAILABLE
    assert len(stored(market_data_session)) == 6  # the two good pages were committed
    assert state(market_data_session).last_status is DataQuality.UNAVAILABLE

    resumed = backfill(market_data_session, make_provider(SyntheticExchange()))
    assert (resumed.inserted, resumed.unchanged, resumed.completed) == (4, 6, True)
    assert len(stored(market_data_session)) == 10
    assert state(market_data_session).last_status is DataQuality.OK


def test_backfill_never_reaches_into_candles_that_have_not_closed(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    result = backfill(
        market_data_session,
        make_provider(SyntheticExchange()),
        start=at(11, 50),
        end=at(13, 0),  # asks for the future
        page_limit=1000,
    )
    # 12:05 is still open at 12:07:30, so the last stored candle is 12:00.
    assert result.completed
    assert [c.open_time for c in stored(market_data_session)][-1] == at(12, 0)
    assert all(c.close_time <= NOW for c in stored(market_data_session))


def test_backfill_of_a_window_with_no_closed_candle_is_a_completed_no_op(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    exchange = SyntheticExchange()
    result = backfill(
        market_data_session, make_provider(exchange), start=at(12, 5), end=at(12, 30), page_limit=10
    )
    assert (result.pages, result.completed) == (0, True)
    assert exchange.requests == []


def test_backfill_is_bounded_and_validates_its_window(
    market_data_session: Session, make_provider: Callable[..., BinanceSpotRestClient]
) -> None:
    exchange = SyntheticExchange()
    provider = make_provider(exchange)

    with pytest.raises(MarketDataRequestError, match="exceeds the limit of 5"):
        backfill(market_data_session, provider, max_candles=5)
    with pytest.raises(MarketDataRequestError, match="start must be timezone-aware UTC"):
        backfill(market_data_session, provider, start=datetime(2026, 9, 24, 11, 0))
    with pytest.raises(MarketDataRequestError, match="end must be timezone-aware UTC"):
        backfill(market_data_session, provider, end=datetime(2026, 9, 24, 11, 50))
    with pytest.raises(MarketDataRequestError, match="start must be timezone-aware UTC"):
        backfill(
            market_data_session,
            provider,
            start=datetime(2026, 9, 24, 11, 0, tzinfo=timezone(timedelta(hours=2))),
        )

    assert exchange.requests == []
    assert stored(market_data_session) == []
