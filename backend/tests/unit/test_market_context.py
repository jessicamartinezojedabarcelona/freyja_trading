"""POINT2-CONTEXT-001: the observable context of a series.

Candles are built by hand on the real timeframe grid, so what is fresh, stale, missing
or closed can be read off the numbers.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from freyja_backend.domain.market_calendar import (
    MarketSchedule,
    MarketSession,
    is_forex_open,
)
from freyja_backend.domain.market_context import (
    CONTEXT_VERSION,
    DataFreshness,
    InvalidContextRequestError,
    MissingDataReason,
    ObservableContext,
    build_observable_context,
)
from freyja_backend.domain.market_data import (
    Candle,
    DataQuality,
    InstrumentRef,
    InvalidMarketDataError,
    Timeframe,
)

TF = Timeframe.M5
STEP = TF.duration
SOURCE = "BINANCE"
AUTHORIZED = frozenset({SOURCE})
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")
EURUSD = InstrumentRef("FOREX", "SPOT", "EUR/USD")
OTC = InstrumentRef("FOREX", "BINARY_OPTION", "EUR/USD OTC")

# A winter Wednesday, half a minute after the 12:00 UTC candle boundary: the candle
# that opened at 11:55 has just closed and is the newest one that must exist.
NOW = datetime(2026, 1, 14, 12, 0, 30, tzinfo=UTC)
LAST_OPEN = datetime(2026, 1, 14, 11, 55, tzinfo=UTC)


def make(open_time: datetime, step: timedelta = STEP) -> Candle:
    return Candle(
        open_time=open_time,
        close_time=open_time + step,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def series(last_open: datetime, count: int) -> list[Candle]:
    return [make(last_open - STEP * i) for i in range(count - 1, -1, -1)]


def forex_series(last_open: datetime, count: int) -> list[Candle]:
    """`count` candles going back from `last_open`, only where the market was open."""
    out: list[Candle] = []
    moment = last_open
    while len(out) < count:
        if is_forex_open(moment):
            out.append(make(moment))
        moment -= STEP
    return out[::-1]


def context(
    candles: list[Candle],
    *,
    observed_at: datetime = NOW,
    instrument: InstrumentRef = BTC,
    schedule: MarketSchedule = MarketSchedule.CONTINUOUS_24_7,
    source: str = SOURCE,
    authorized: frozenset[str] = AUTHORIZED,
    signal: Timeframe = TF,
    context_tf: Timeframe = TF,
    min_history: int = 100,
) -> ObservableContext:
    return build_observable_context(
        instrument_id="00000000-0000-0000-0000-000000000001",
        instrument=instrument,
        schedule=schedule,
        signal_timeframe=signal,
        context_timeframe=context_tf,
        observed_at=observed_at,
        data_source=source,
        authorized_sources=authorized,
        candles=candles,
        min_history=min_history,
    )


# --- The happy path ------------------------------------------------------------------


def test_a_complete_fresh_series_gives_a_sufficient_context() -> None:
    ctx = context(series(LAST_OPEN, 120))

    assert ctx.is_sufficient
    assert ctx.missing_data_reasons == ()
    assert ctx.data_freshness is DataFreshness.FRESH
    assert ctx.data_quality_status is DataQuality.OK
    assert ctx.window_candles == 100
    assert ctx.last_closed_candle_at == LAST_OPEN + STEP
    assert ctx.context_version == CONTEXT_VERSION == "context-v1"


def test_it_carries_everything_the_task_requires() -> None:
    ctx = context(series(LAST_OPEN, 100))

    assert ctx.observed_at == NOW
    assert ctx.instrument_id == "00000000-0000-0000-0000-000000000001"
    assert ctx.product_type == "SPOT"
    assert ctx.signal_timeframe is TF
    assert ctx.context_timeframe is TF
    assert ctx.data_source == SOURCE
    assert ctx.timezone == "UTC"


def test_crypto_records_the_utc_day_and_hour_and_never_invents_a_session() -> None:
    ctx = context(series(LAST_OPEN, 100))

    assert ctx.market_open is True
    assert ctx.market_session is None  # not applicable, and never a borrowed Forex one
    assert ctx.weekday_utc == 2  # Wednesday
    assert ctx.hour_utc == 12
    assert ctx.calendar_version is None


def test_the_context_decides_no_signal() -> None:
    fields = set(ObservableContext.__dataclass_fields__)

    forbidden = {"signal", "direction", "trend", "state", "opportunity", "recommendation"}
    assert fields.isdisjoint(forbidden)


def test_it_is_deterministic() -> None:
    candles = series(LAST_OPEN, 130)

    assert context(candles) == context(list(candles))


# --- The open candle is never used ---------------------------------------------------


def test_a_candle_still_in_progress_is_not_used() -> None:
    candles = [*series(LAST_OPEN, 100), make(LAST_OPEN + STEP)]  # opens 12:00, closes 12:05

    ctx = context(candles)

    assert ctx.last_closed_candle_at == LAST_OPEN + STEP  # 12:00, not 12:05
    assert ctx.window_candles == 100
    assert ctx.is_sufficient


def test_a_candle_that_closes_exactly_at_observed_at_is_used() -> None:
    ctx = context(series(LAST_OPEN, 100), observed_at=LAST_OPEN + STEP)

    assert ctx.last_closed_candle_at == LAST_OPEN + STEP


# --- Freshness, and no silent reuse of an old context ---------------------------------


def test_data_that_is_too_old_is_stale_and_insufficient() -> None:
    old = series(LAST_OPEN - timedelta(minutes=30), 100)

    ctx = context(old)

    assert ctx.data_freshness is DataFreshness.STALE
    assert MissingDataReason.STALE_DATA in ctx.missing_data_reasons
    assert ctx.data_quality_status is DataQuality.DEGRADED
    assert not ctx.is_sufficient


def test_an_older_valid_context_is_never_reused_for_a_later_instant() -> None:
    candles = series(LAST_OPEN, 100)

    earlier = context(candles)
    later = context(candles, observed_at=NOW + timedelta(hours=1))

    assert earlier.is_sufficient
    assert not later.is_sufficient  # same candles, an hour on: they no longer count
    assert later.observed_at == NOW + timedelta(hours=1)
    assert MissingDataReason.STALE_DATA in later.missing_data_reasons
    assert earlier.is_sufficient  # and the earlier answer is untouched


def test_the_grace_period_keeps_a_just_closed_candle_from_being_required_too_early() -> None:
    # 5 seconds after the boundary the 11:55 candle may not be published yet, so the
    # newest one that must exist is the 11:50 one.
    candles = series(LAST_OPEN - STEP, 100)

    ctx = context(candles, observed_at=datetime(2026, 1, 14, 12, 0, 5, tzinfo=UTC))

    assert ctx.data_freshness is DataFreshness.FRESH


# --- History depth and gaps ------------------------------------------------------------


def test_fewer_candles_than_the_minimum_history_is_insufficient() -> None:
    ctx = context(series(LAST_OPEN, 99))

    assert MissingDataReason.INSUFFICIENT_HISTORY in ctx.missing_data_reasons
    assert not ctx.is_sufficient
    assert context(series(LAST_OPEN, 100)).is_sufficient


def test_the_minimum_history_can_be_set() -> None:
    assert context(series(LAST_OPEN, 30), min_history=30).is_sufficient
    assert not context(series(LAST_OPEN, 29), min_history=30).is_sufficient


def test_a_gap_inside_the_evaluated_window_is_insufficient() -> None:
    candles = series(LAST_OPEN, 120)
    del candles[-50]

    ctx = context(candles)

    assert MissingDataReason.GAPS_IN_WINDOW in ctx.missing_data_reasons
    assert ctx.data_quality_status is DataQuality.DEGRADED
    assert not ctx.is_sufficient


def test_a_gap_older_than_the_window_does_not_matter() -> None:
    candles = series(LAST_OPEN, 150)
    del candles[5]  # far before the last 100

    ctx = context(candles)

    assert ctx.is_sufficient
    assert ctx.data_quality_status is DataQuality.OK


# --- Missing and bad data ---------------------------------------------------------------


def test_no_candles_at_all_is_no_data() -> None:
    ctx = context([])

    assert ctx.data_freshness is DataFreshness.NO_DATA
    assert ctx.data_quality_status is DataQuality.UNAVAILABLE
    assert ctx.missing_data_reasons == (MissingDataReason.NO_DATA,)
    assert ctx.last_closed_candle_at is None


def test_only_open_candles_is_no_data() -> None:
    ctx = context([make(LAST_OPEN + STEP)])

    assert ctx.missing_data_reasons == (MissingDataReason.NO_DATA,)


def test_candles_that_contradict_each_other_give_an_insufficient_context_not_an_error() -> None:
    good = series(LAST_OPEN, 100)
    conflicting = Candle(
        open_time=good[-1].open_time,
        close_time=good[-1].close_time,
        open=Decimal("100"),
        high=Decimal("150"),
        low=Decimal("99"),
        close=Decimal("140"),
        volume=Decimal("1"),
    )

    ctx = context([*good, conflicting])

    assert ctx.missing_data_reasons == (MissingDataReason.INVALID_CANDLES,)
    assert ctx.data_quality_status is DataQuality.UNAVAILABLE


def test_a_candle_off_the_timeframe_grid_is_invalid_not_ignored() -> None:
    off_grid = make(LAST_OPEN + timedelta(minutes=1))

    ctx = context([*series(LAST_OPEN, 100), off_grid])

    assert ctx.missing_data_reasons == (MissingDataReason.INVALID_CANDLES,)


def test_duplicates_are_dropped_but_reported_as_degraded_data() -> None:
    candles = series(LAST_OPEN, 100)

    ctx = context([*candles, candles[-1]])

    assert MissingDataReason.DEGRADED_DATA in ctx.missing_data_reasons
    assert ctx.data_quality_status is DataQuality.DEGRADED


# --- Source authorisation -----------------------------------------------------------------


def test_a_source_that_is_not_authorised_is_insufficient_even_with_perfect_data() -> None:
    ctx = context(series(LAST_OPEN, 100), source="SOMEWHERE_ELSE")

    assert ctx.missing_data_reasons == (MissingDataReason.SOURCE_NOT_AUTHORIZED,)
    assert ctx.data_freshness is DataFreshness.UNKNOWN
    assert ctx.last_closed_candle_at is None  # its candles were not even read
    assert ctx.window_candles == 0


def test_no_authorised_source_at_all_is_insufficient() -> None:
    ctx = context(series(LAST_OPEN, 100), authorized=frozenset())

    assert MissingDataReason.SOURCE_NOT_AUTHORIZED in ctx.missing_data_reasons


# --- OTC is not excluded; its hours belong to the broker -----------------------------------


def test_an_otc_instrument_is_not_rejected_for_being_otc() -> None:
    # A schedule that is known makes it an ordinary series like any other.
    ctx = context(series(LAST_OPEN, 100), instrument=OTC, schedule=MarketSchedule.CONTINUOUS_24_7)

    assert ctx.is_sufficient
    assert ctx.product_type == "BINARY_OPTION"


def test_a_broker_defined_schedule_is_unknown_until_an_adapter_supplies_it() -> None:
    ctx = context(series(LAST_OPEN, 100), instrument=OTC, schedule=MarketSchedule.BROKER_DEFINED)

    assert ctx.missing_data_reasons == (MissingDataReason.SCHEDULE_UNKNOWN,)
    assert ctx.market_open is None  # not guessed
    assert ctx.market_session is None
    assert ctx.data_freshness is DataFreshness.UNKNOWN


# --- Forex: week, sessions, weekends ----------------------------------------------------------


def test_forex_records_the_session_and_the_calendar_version() -> None:
    observed = datetime(2026, 1, 14, 13, 30, 30, tzinfo=UTC)  # overlap, winter
    candles = forex_series(datetime(2026, 1, 14, 13, 25, tzinfo=UTC), 100)

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert ctx.market_open is True
    assert ctx.market_session is MarketSession.OVERLAP_LONDON_NEW_YORK
    assert ctx.calendar_version == "forex-sessions-v1"
    assert ctx.is_sufficient


def test_on_a_weekend_the_market_is_closed_and_data_from_friday_is_still_fresh() -> None:
    observed = datetime(2026, 1, 17, 12, 0, 30, tzinfo=UTC)  # Saturday
    candles = forex_series(datetime(2026, 1, 16, 21, 55, tzinfo=UTC), 100)  # last before close

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert ctx.market_open is False
    assert ctx.market_session is MarketSession.CLOSED
    assert ctx.data_freshness is DataFreshness.FRESH
    assert ctx.is_sufficient


def test_on_a_weekend_data_that_stopped_before_friday_is_still_stale() -> None:
    observed = datetime(2026, 1, 17, 12, 0, 30, tzinfo=UTC)
    candles = forex_series(datetime(2026, 1, 15, 12, 0, tzinfo=UTC), 100)  # a day too early

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert MissingDataReason.STALE_DATA in ctx.missing_data_reasons


def test_a_window_that_crosses_a_weekend_has_no_gap() -> None:
    observed = datetime(
        2026, 1, 19, 2, 0, 30, tzinfo=UTC
    )  # Monday, market reopened at Sunday 22:00
    candles = forex_series(datetime(2026, 1, 19, 1, 55, tzinfo=UTC), 100)
    assert candles[0].open_time < datetime(2026, 1, 16, 22, 0, tzinfo=UTC)  # crosses the weekend

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert MissingDataReason.GAPS_IN_WINDOW not in ctx.missing_data_reasons
    assert ctx.is_sufficient


def test_a_missing_candle_while_the_forex_market_was_open_is_a_gap() -> None:
    observed = datetime(2026, 1, 19, 2, 0, 30, tzinfo=UTC)
    candles = forex_series(datetime(2026, 1, 19, 1, 55, tzinfo=UTC), 100)
    del candles[-10]

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert MissingDataReason.GAPS_IN_WINDOW in ctx.missing_data_reasons


def test_forex_data_from_friday_is_stale_once_the_market_has_reopened() -> None:
    observed = datetime(2026, 1, 19, 10, 0, 30, tzinfo=UTC)  # Monday morning
    candles = forex_series(datetime(2026, 1, 16, 21, 55, tzinfo=UTC), 100)

    ctx = context(
        candles,
        observed_at=observed,
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
    )

    assert ctx.market_open is True
    assert MissingDataReason.STALE_DATA in ctx.missing_data_reasons


# --- The request itself ---------------------------------------------------------------------


def test_a_context_timeframe_finer_than_the_signal_timeframe_is_rejected() -> None:
    with pytest.raises(InvalidContextRequestError):
        context(series(LAST_OPEN, 100), signal=Timeframe.H1, context_tf=Timeframe.M5)


def test_equal_or_coarser_context_timeframes_are_accepted() -> None:
    candles_1h = [
        make(datetime(2026, 1, 14, 11, 0, tzinfo=UTC) - timedelta(hours=i), timedelta(hours=1))
        for i in range(99, -1, -1)
    ]

    same = context(candles_1h, signal=Timeframe.H1, context_tf=Timeframe.H1)
    coarser = context(candles_1h, signal=Timeframe.M15, context_tf=Timeframe.H1)

    assert same.is_sufficient
    assert coarser.is_sufficient
    assert coarser.signal_timeframe is Timeframe.M15
    assert coarser.context_timeframe is Timeframe.H1


def test_observed_at_must_be_utc() -> None:
    with pytest.raises(InvalidMarketDataError):
        context(series(LAST_OPEN, 100), observed_at=datetime(2026, 1, 14, 12, 0, 30))


def test_the_minimum_history_must_be_positive() -> None:
    with pytest.raises(InvalidContextRequestError):
        context(series(LAST_OPEN, 100), min_history=0)
