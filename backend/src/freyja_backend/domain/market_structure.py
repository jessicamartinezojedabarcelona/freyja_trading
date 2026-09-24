"""Price structure: pivots and swing points (POINT2-STRUCTURE-001).

The contract lives in ``docs/domain/estructura-de-precio.md``; this is its
reference implementation. Pure and free of I/O: the same candles, the same
``observed_at`` and the same parameters always give the same pivots.

A *pivot* is a candle whose high (or low) is an extreme among the ``k`` closed
candles on each side of it. It is only *knowable* once the ``k``-th candle after
it has closed, so a pivot is ``PROVISIONAL`` until then and ``CONFIRMED`` after.
Only confirmed pivots may feed any decision; nothing here looks past
``observed_at``.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from freyja_backend.domain.market_data import (
    Candle,
    InvalidMarketDataError,
    Timeframe,
    _require_utc,
)

# Bump on ANY change to how pivots or swing points are derived, so a stored
# result can always be traced to the exact algorithm that produced it.
STRUCTURE_ALGORITHM_VERSION = "pivots-v1"

# Candles needed before a series has enough structure to be worth reading.
# See "Profundidad mínima" in the contract for why this number.
MIN_HISTORY_CANDLES = 100


class PivotKind(enum.StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class PivotStatus(enum.StrEnum):
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True, slots=True)
class PivotParams:
    """``k``: closed candles required on EACH side of a pivot candle."""

    k: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.k, bool) or not isinstance(self.k, int) or self.k < 1:
            raise ValueError("k must be an integer >= 1")


DEFAULT_PIVOT_PARAMS = PivotParams()


@dataclass(frozen=True, slots=True)
class Pivot:
    kind: PivotKind
    status: PivotStatus
    open_time: datetime
    price: Decimal
    # Close of the k-th candle after the pivot: the first instant it is knowable.
    # None while PROVISIONAL.
    confirmed_at: datetime | None


@dataclass(frozen=True, slots=True)
class PivotResult:
    pivots: tuple[Pivot, ...]
    observed_at: datetime
    params: PivotParams
    algorithm_version: str
    candles_used: int

    @property
    def confirmed(self) -> tuple[Pivot, ...]:
        return tuple(p for p in self.pivots if p.status is PivotStatus.CONFIRMED)


def detect_pivots(
    candles: Sequence[Candle],
    *,
    timeframe: Timeframe,
    observed_at: datetime,
    params: PivotParams = DEFAULT_PIVOT_PARAMS,
) -> PivotResult:
    """Pivots of a closed-candle series as they are knowable at ``observed_at``.

    Only candles closed at or before ``observed_at`` are read. Candles must be
    oldest first with strictly increasing ``open_time`` on the timeframe grid;
    anything else raises ``InvalidMarketDataError`` (nothing is repaired or
    guessed). Missing candles (gaps) are allowed, but no pivot is produced
    whose neighbourhood of ``k`` candles on each side contains one.

    Results are ordered by ``open_time``, and a candle that is both a high and a
    low pivot yields both, high first.
    """
    _require_utc(observed_at, "observed_at")
    known = _known_candles(candles, timeframe=timeframe, observed_at=observed_at)
    k = params.k
    step = timeframe.duration
    count = len(known)

    def contiguous(first: int, last: int) -> bool:
        return all(known[i + 1].open_time - known[i].open_time == step for i in range(first, last))

    pivots: list[Pivot] = []
    for i in range(k, count):
        right = min(k, count - 1 - i)
        if not contiguous(i - k, i + right):
            continue  # a missing candle inside the neighbourhood: never guess
        left_candles = known[i - k : i]
        right_candles = known[i + 1 : i + 1 + right]
        confirmed = right == k
        confirmed_at = known[i + k].close_time if confirmed else None
        status = PivotStatus.CONFIRMED if confirmed else PivotStatus.PROVISIONAL
        candle = known[i]
        # Ties: strictly beyond everything on the left, at least level on the right.
        # A plateau of equal extremes therefore yields exactly one pivot: its first.
        if candle.high > max(c.high for c in left_candles) and all(
            candle.high >= c.high for c in right_candles
        ):
            pivots.append(
                Pivot(PivotKind.HIGH, status, candle.open_time, candle.high, confirmed_at)
            )
        if candle.low < min(c.low for c in left_candles) and all(
            candle.low <= c.low for c in right_candles
        ):
            pivots.append(Pivot(PivotKind.LOW, status, candle.open_time, candle.low, confirmed_at))
    return PivotResult(
        pivots=tuple(pivots),
        observed_at=observed_at,
        params=params,
        algorithm_version=STRUCTURE_ALGORITHM_VERSION,
        candles_used=count,
    )


def _known_candles(
    candles: Sequence[Candle], *, timeframe: Timeframe, observed_at: datetime
) -> list[Candle]:
    step = timeframe.duration
    for previous, current in pairwise(candles):
        if current.open_time <= previous.open_time:
            raise InvalidMarketDataError("candles must have strictly increasing open_time")
    for candle in candles:
        if candle.close_time - candle.open_time != step or timeframe.floor(candle.open_time) != (
            candle.open_time
        ):
            raise InvalidMarketDataError("a candle is not aligned to the timeframe grid")
    return [c for c in candles if c.close_time <= observed_at]


def swing_points(pivots: Sequence[Pivot]) -> tuple[Pivot, ...]:
    """Confirmed pivots reduced to a strictly alternating high/low sequence.

    Provisional pivots are ignored. Consecutive pivots of the same kind collapse
    into the most extreme one (the earliest on a tie). A candle that is both a
    high and a low pivot is left out: the order of its high and low inside the
    candle cannot be known, so putting either first would invent information.

    The sequence can change at its tail as later pivots confirm; that is why a
    result is always tied to its ``observed_at``.
    """
    confirmed = [p for p in pivots if p.status is PivotStatus.CONFIRMED]
    both = {
        p.open_time
        for p in confirmed
        if any(q.open_time == p.open_time and q.kind is not p.kind for q in confirmed)
    }
    swings: list[Pivot] = []
    for pivot in confirmed:
        if pivot.open_time in both:
            continue
        if swings and swings[-1].kind is pivot.kind:
            last = swings[-1]
            more_extreme = (
                pivot.price > last.price
                if pivot.kind is PivotKind.HIGH
                else pivot.price < last.price
            )
            if more_extreme:
                swings[-1] = pivot
        else:
            swings.append(pivot)
    return tuple(swings)
