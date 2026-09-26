"""Fibonacci: the search for impulses (FIB-DETECT-001, first part).

Contract in ``docs/domain/fibonacci-retroceso.md`` (sections 2 and 16). This module decides **which
pairs of pivots are considered impulses** and nothing else: it says nothing about zones,
confirmation of a rejection, entry, expiry or any signal, and it does not yet manage the life of an
instance over time (the second part of the task).

Policy `fibonacci-search-v1`, the **dominant leg** ending at each confirmed swing: for every swing
`B` (a high gives a bullish impulse, a low a bearish one) the impulse starts at the **earliest**
opposite swing `A`, no further back than `search_window_candles` candles from `B`, such that
`check_impulse` accepts the pair (no wick beyond the extremes from A's candle to B's, and the size
is enough). That is the lowest low (highest high, if bearish) since the price last went beyond `B`.
Bounding the look-back makes the answer depend only on the candles around `B`, never on where the
supplied history happens to begin.

Everything is a pure function of closed candles and of ``observed_at``: the same candles always give
the same impulses, and only pivots confirmed by ``observed_at`` are used.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from freyja_backend.domain.fibonacci import (
    DEFAULT_FIBONACCI_PARAMS,
    FibonacciParams,
    Impulse,
    check_impulse,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason, build_observable_context
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    InstrumentRef,
    InvalidMarketDataError,
    Timeframe,
    _require_utc,
    assess_candles,
)
from freyja_backend.domain.market_structure import Pivot, detect_pivots, swing_points


def find_impulses(
    closed: Sequence[Candle],
    swings: Sequence[Pivot],
    params: FibonacciParams = DEFAULT_FIBONACCI_PARAMS,
) -> tuple[Impulse, ...]:
    """The impulses of `fibonacci-search-v1` among these swings and closed candles, oldest first.

    `swings` are confirmed swing points (`swing_points`), alternating high and low. Each swing `B`
    yields at most one impulse: the dominant leg that ends at it, if there is one."""
    index = {candle.open_time: position for position, candle in enumerate(closed)}
    found: list[Impulse] = []
    for position, end in enumerate(swings):
        end_index = index.get(end.open_time)
        if end_index is None:
            continue
        # No further back than the look-back. Anything that a wick beyond B, or a lower low than A,
        # would rule out is ruled out by `check_impulse` itself: the earliest start that passes is,
        # by that rule, the lowest low (highest high) since the price last went beyond B.
        oldest = end_index - params.search_window_candles  # (negative: no limit yet)
        for start in swings[:position]:
            start_index = index.get(start.open_time)
            if start_index is None or start_index < oldest:
                continue
            check = check_impulse(closed, start, end, params)
            if check.impulse is not None:
                found.append(check.impulse)
                break  # the earliest that passes is the dominant leg
    return tuple(found)


@dataclass(frozen=True, slots=True)
class FibonacciSeries:
    """What the search needs to know about the series it reads, at one instant."""

    instrument_id: str
    instrument: InstrumentRef
    schedule: MarketSchedule
    data_source: str
    authorized_sources: frozenset[str]
    timeframe: Timeframe
    observed_at: datetime
    params: FibonacciParams = DEFAULT_FIBONACCI_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE

    def at(self, observed_at: datetime) -> "FibonacciSeries":
        return replace(self, observed_at=observed_at)


@dataclass(frozen=True, slots=True)
class ImpulseSearch:
    """What the search saw at one instant. If the data was not fit to judge, there are no impulses
    and the reasons say why: an impulse is never guessed from unfit data."""

    impulses: tuple[Impulse, ...]
    unfit_reasons: tuple[MissingDataReason, ...]
    # Close of the newest closed candle read; None if there was none.
    as_of: datetime | None


def search_impulses(series: FibonacciSeries, candles: Sequence[Candle]) -> ImpulseSearch:
    """The impulses visible at `series.observed_at`, from the candles closed by then. Candles that
    close later, and the one in progress, are ignored. Bad data never raises: it yields no impulses
    and the reasons. Only a wrong request raises."""
    params = series.params
    _require_utc(series.observed_at, "observed_at")  # a wrong request, not bad data
    try:
        closed = assess_candles(
            candles,
            timeframe=series.timeframe,
            now=series.observed_at,
            publication_grace=series.publication_grace,
        ).candles
    except InvalidMarketDataError:
        return ImpulseSearch((), (MissingDataReason.INVALID_CANDLES,), None)
    observable = build_observable_context(
        instrument_id=series.instrument_id,
        instrument=series.instrument,
        schedule=series.schedule,
        signal_timeframe=series.timeframe,
        context_timeframe=series.timeframe,
        observed_at=series.observed_at,
        data_source=series.data_source,
        authorized_sources=series.authorized_sources,
        candles=candles,
        min_history=params.range_window_candles,
        publication_grace=series.publication_grace,
    )
    as_of = closed[-1].close_time if closed else None
    if not observable.is_sufficient:
        return ImpulseSearch((), observable.missing_data_reasons, as_of)
    swings = swing_points(
        detect_pivots(
            closed,
            timeframe=series.timeframe,
            observed_at=series.observed_at,
            params=params.pivot_params,
        ).confirmed
    )
    return ImpulseSearch(find_impulses(tuple(closed), swings, params), (), as_of)
