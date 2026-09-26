"""Fibonacci retracement tool: exact calculation (FIB-CALC-001).

Contract in ``docs/domain/fibonacci-retroceso.md``. This module **measures** and never decides:
given an impulse (two confirmed pivots) it computes the retracement levels for a bullish or a
bearish impulse, with the same rule for both and for every timeframe, and it states which candles
touched which level and when the Fibonacci became knowable. It has no zone, tolerance,
confirmation, entry, horizon, invalidation, target or signal: those belong to each StrategySpec.

Everything is a pure function of closed candles and of ``observed_at``: no clock, no database, no
indicator, no candlestick pattern. Prices are exact ``Decimal`` (never ``float``), rounded to the 12
decimals prices are stored with. The parameters are versioned; changing any changes the version.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from freyja_backend.domain.market_data import Candle, _require_utc
from freyja_backend.domain.market_structure import (
    DEFAULT_PIVOT_PARAMS,
    Pivot,
    PivotKind,
    PivotParams,
    PivotStatus,
)

FIBONACCI_PARAMETER_VERSION = "fibonacci-params-v1"
FIBONACCI_LEVELS_VERSION = "fibonacci-levels-v1"
FIBONACCI_CONVENTION_VERSION = "fibonacci-convention-v1"  # wick extremes, linear scale

# Exact decimal constants: they are not recomputed from the sequence. (The 0.5 is not a Fibonacci
# ratio; the trading tool includes it.)
DEFAULT_LEVEL_RATIOS: tuple[Decimal, ...] = (
    Decimal("0.236"),
    Decimal("0.382"),
    Decimal("0.5"),
    Decimal("0.618"),
    Decimal("0.786"),
)

# Prices are stored with 12 decimals (NUMERIC(38,12)): a computed level is never finer than that.
_PRICE_STEP = Decimal("0.000000000001")
_SIX = Decimal("0.000001")
_PRECISION = 60  # more than any price times any ratio needs: the products are exact


class InvalidFibonacciRequestError(ValueError):
    """The request itself is wrong (not the data): a configuration error to fix."""


@dataclass(frozen=True, slots=True)
class FibonacciParams:
    """Versioned parameters of the tool. Provisional and unvalidated (PARAMS-VALIDATION-001)."""

    version: str = FIBONACCI_PARAMETER_VERSION
    levels_version: str = FIBONACCI_LEVELS_VERSION
    convention_version: str = FIBONACCI_CONVENTION_VERSION
    ratios: tuple[Decimal, ...] = DEFAULT_LEVEL_RATIOS
    # The pivots an impulse is made of: the ones of `pivots-v1`.
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    # An impulse is at least this fraction of the price range of the `range_window_candles` candles
    # that end at its start. Relative, so it reads the same on any instrument.
    min_impulse_fraction: Decimal = Decimal("0.25")
    range_window_candles: int = 100

    def __post_init__(self) -> None:
        for name in ("version", "levels_version", "convention_version"):
            if not getattr(self, name).strip():
                raise InvalidFibonacciRequestError(f"{name} must be declared")
        if not self.ratios or any(
            not isinstance(r, Decimal) or not (Decimal(0) < r < Decimal(1)) for r in self.ratios
        ):
            raise InvalidFibonacciRequestError("ratios must be Decimals between 0 and 1")
        if any(
            later <= earlier for earlier, later in zip(self.ratios, self.ratios[1:], strict=False)
        ):
            raise InvalidFibonacciRequestError("ratios must be strictly increasing")
        fraction = self.min_impulse_fraction
        if not isinstance(fraction, Decimal) or not (Decimal(0) < fraction < Decimal(1)):
            raise InvalidFibonacciRequestError("min_impulse_fraction must be a Decimal in (0, 1)")
        window = self.range_window_candles
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise InvalidFibonacciRequestError(
                "range_window_candles must be an integer of at least 1"
            )


DEFAULT_FIBONACCI_PARAMS = FibonacciParams()


class ImpulseDirection(enum.StrEnum):
    """Which way the impulse went. A bearish impulse is a bullish one upside down."""

    BULLISH = "BULLISH"  # a low to a high; the retracement goes down, towards A
    BEARISH = "BEARISH"  # a high to a low; the retracement goes up, towards A

    @property
    def sign(self) -> int:
        return 1 if self is ImpulseDirection.BULLISH else -1

    @property
    def start_kind(self) -> PivotKind:
        return PivotKind.LOW if self is ImpulseDirection.BULLISH else PivotKind.HIGH

    @property
    def end_kind(self) -> PivotKind:
        return PivotKind.HIGH if self is ImpulseDirection.BULLISH else PivotKind.LOW


class ImpulseRejection(enum.StrEnum):
    """Why a pair of pivots is not an impulse. It is not adjusted, trimmed or "almost" accepted."""

    PIVOT_NOT_CONFIRMED = "PIVOT_NOT_CONFIRMED"
    WRONG_PIVOT_KINDS = "WRONG_PIVOT_KINDS"
    NOT_IN_ORDER = "NOT_IN_ORDER"
    CANDLES_MISSING = "CANDLES_MISSING"
    CANDLE_OUTSIDE_EXTREMES = "CANDLE_OUTSIDE_EXTREMES"
    NO_REFERENCE_RANGE = "NO_REFERENCE_RANGE"
    TOO_SMALL = "TOO_SMALL"


@dataclass(frozen=True, slots=True)
class Impulse:
    """A valid impulse: `start` (A) and `end` (B), confirmed pivots of one series."""

    direction: ImpulseDirection
    start: Pivot
    end: Pivot
    # Candles from the one of A to the one of B (recorded, never filtered).
    impulse_candles: int
    # The range the size was measured against: fixed when the impulse begins.
    reference_range: Decimal

    @property
    def size(self) -> Decimal:
        """`D = |B - A|`."""
        return abs(self.end.price - self.start.price)

    @property
    def known_at(self) -> datetime:
        """The instant the Fibonacci starts to exist: the confirmation of pivot B (the close of the
        k-th candle after it). A's was earlier. The publication latency of the provider is not added
        here: it applies when candles are read (`observed_at`)."""
        assert self.end.confirmed_at is not None  # checked when the impulse is built
        return self.end.confirmed_at


@dataclass(frozen=True, slots=True)
class ImpulseCheck:
    impulse: Impulse | None
    rejection: ImpulseRejection | None


def check_impulse(
    closed: Sequence[Candle],
    start: Pivot,
    end: Pivot,
    params: FibonacciParams = DEFAULT_FIBONACCI_PARAMS,
) -> ImpulseCheck:
    """Whether `start` and `end` are an impulse of the series `closed`, by the rules of section 2 of
    the contract. `closed` are closed candles, oldest first."""
    if (
        start.status is not PivotStatus.CONFIRMED
        or end.status is not PivotStatus.CONFIRMED
        or start.confirmed_at is None
        or end.confirmed_at is None
    ):
        return _rejected(ImpulseRejection.PIVOT_NOT_CONFIRMED)
    if start.kind is end.kind:
        return _rejected(ImpulseRejection.WRONG_PIVOT_KINDS)
    direction = (
        ImpulseDirection.BULLISH if start.kind is PivotKind.LOW else ImpulseDirection.BEARISH
    )
    if end.open_time <= start.open_time:
        return _rejected(ImpulseRejection.NOT_IN_ORDER)
    index = {candle.open_time: position for position, candle in enumerate(closed)}
    if start.open_time not in index or end.open_time not in index:
        return _rejected(ImpulseRejection.CANDLES_MISSING)
    first, last = index[start.open_time], index[end.open_time]

    # No candle from A's to B's (both included) has a wick beyond the extremes: not strict.
    stretch = closed[first : last + 1]
    if direction is ImpulseDirection.BULLISH:
        outside = any(c.low < start.price or c.high > end.price for c in stretch)
    else:
        outside = any(c.high > start.price or c.low < end.price for c in stretch)
    if outside:
        return _rejected(ImpulseRejection.CANDLE_OUTSIDE_EXTREMES)

    size = abs(end.price - start.price)
    window = closed[max(0, first - params.range_window_candles + 1) : first + 1]
    reference = max(c.high for c in window) - min(c.low for c in window)
    if reference <= 0:
        return _rejected(ImpulseRejection.NO_REFERENCE_RANGE)
    # (Zero is below any positive threshold, so a zero-size pair is refused here too.)
    if size < params.min_impulse_fraction * reference:
        return _rejected(ImpulseRejection.TOO_SMALL)
    return ImpulseCheck(Impulse(direction, start, end, last - first, reference), None)


def _rejected(reason: ImpulseRejection) -> ImpulseCheck:
    return ImpulseCheck(None, reason)


@dataclass(frozen=True, slots=True)
class FibonacciLevel:
    ratio: Decimal
    price: Decimal


def retracement_levels(
    impulse: Impulse, params: FibonacciParams = DEFAULT_FIBONACCI_PARAMS
) -> tuple[FibonacciLevel, ...]:
    """The retracement levels: `B - r * D` for a bullish impulse and `B + r * D` for a bearish one,
    exact `Decimal`, rounded to the 12 decimals prices are stored with. The bearish levels are the
    bullish ones upside down."""
    with localcontext() as context:
        context.prec = _PRECISION
        distance = impulse.size
        sign = impulse.direction.sign
        # The offset from B is rounded, not the level: the same offset serves both directions, so a
        # bearish level is exactly a bullish one upside down, ties included.
        return tuple(
            FibonacciLevel(
                ratio,
                impulse.end.price - sign * (ratio * distance).quantize(_PRICE_STEP),
            )
            for ratio in params.ratios
        )


def touches(level: Decimal, candle: Candle) -> bool:
    """A candle touches a level if the level lies within its range, both ends included:
    `low <= level <= high`. A fact about the range of the candle and nothing else: not in which
    order the price went through its values, not at what price anything could have been done, not
    a signal."""
    return candle.low <= level <= candle.high


def closed_beyond(direction: ImpulseDirection, level: Decimal, candle: Candle) -> bool:
    """A candle closes beyond a level, on the side of A: `close < level` for a bullish impulse
    (the retracement goes down) and `close > level` for a bearish one (it goes up). Strict: a
    close on the level is not beyond it (it is a touch)."""
    if direction is ImpulseDirection.BULLISH:
        return candle.close < level
    return candle.close > level


@dataclass(frozen=True, slots=True)
class LevelEvent:
    """When a fact happened. `retrospective` is true if its candle opened before the Fibonacci was
    known: it is then an observation about the past, never an operable historical signal."""

    candle_open_time: datetime
    candle_close_time: datetime
    retrospective: bool


@dataclass(frozen=True, slots=True)
class LevelObservation:
    level: FibonacciLevel
    first_touch: LevelEvent | None
    first_operable_touch: LevelEvent | None
    first_close_beyond: LevelEvent | None
    first_operable_close_beyond: LevelEvent | None


@dataclass(frozen=True, slots=True)
class FibonacciObservation:
    """What the price did against the levels, as of one instant."""

    impulse: Impulse
    observed_at: datetime
    candles_observed: int
    levels: tuple[LevelObservation, ...]
    # How far the price retraced, as a fraction of D (0 if it did not): by wicks and by closes.
    max_retracement_by_wicks: Decimal
    max_retracement_by_closes: Decimal
    # Distance from the last observed close to the nearest level, as a fraction of D.
    nearest_level_distance: Decimal | None


def observe(
    impulse: Impulse,
    closed: Sequence[Candle],
    *,
    observed_at: datetime,
    params: FibonacciParams = DEFAULT_FIBONACCI_PARAMS,
) -> FibonacciObservation:
    """The facts about the price against the levels, from the closed candles after B's and closed
    by `observed_at`. Asking before `known_at` is a wrong request: the Fibonacci does not exist
    yet. Candles that close later are ignored, so the answer at an instant never depends on the
    future."""
    _require_utc(observed_at, "observed_at")
    if observed_at < impulse.known_at:
        raise InvalidFibonacciRequestError("the Fibonacci is not known yet at observed_at")
    seen = sorted(
        (c for c in closed if c.open_time > impulse.end.open_time and c.close_time <= observed_at),
        key=lambda c: c.open_time,
    )
    levels = retracement_levels(impulse, params)
    known_at = impulse.known_at
    direction = impulse.direction

    def first(
        found: Sequence[Candle],
    ) -> tuple[LevelEvent | None, LevelEvent | None]:
        anyone = next(iter(found), None)
        operable = next((c for c in found if c.open_time >= known_at), None)

        def event(candle: Candle | None) -> LevelEvent | None:
            if candle is None:
                return None
            return LevelEvent(candle.open_time, candle.close_time, candle.open_time < known_at)

        return event(anyone), event(operable)

    observations = []
    for level in levels:
        touch, operable_touch = first([c for c in seen if touches(level.price, c)])
        beyond, operable_beyond = first(
            [c for c in seen if closed_beyond(direction, level.price, c)]
        )
        observations.append(LevelObservation(level, touch, operable_touch, beyond, operable_beyond))

    distance = impulse.size
    sign = direction.sign
    by_wicks = by_closes = Decimal(0)
    nearest: Decimal | None = None
    if seen:
        # How far the price went back towards A: from B, down if bullish, up if bearish.
        deepest_wick = min(c.low for c in seen) if sign > 0 else max(c.high for c in seen)
        deepest_close = min(c.close for c in seen) if sign > 0 else max(c.close for c in seen)
        by_wicks = _fraction(max(Decimal(0), sign * (impulse.end.price - deepest_wick)), distance)
        by_closes = _fraction(max(Decimal(0), sign * (impulse.end.price - deepest_close)), distance)
        last_close = seen[-1].close
        nearest = _fraction(min(abs(last_close - level.price) for level in levels), distance)
    return FibonacciObservation(
        impulse, observed_at, len(seen), tuple(observations), by_wicks, by_closes, nearest
    )


def _fraction(part: Decimal, whole: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _PRECISION
        return (part / whole).quantize(_SIX)
