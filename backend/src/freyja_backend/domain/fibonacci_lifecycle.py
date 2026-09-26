"""Fibonacci: the life of an instance over time (FIB-DETECT-001, second part).

Contract in ``docs/domain/fibonacci-retroceso.md`` (sections 3, 5 and 17). This module follows the
impulses that `fibonacci_detection.search_impulses` finds, instant by instant, and keeps an
**append-only record** of what happened to each Fibonacci:

* an instance is **born** when Freyja knows it (pivot B confirmed and its confirming candle
  received);
* it is **extended** when a candle goes beyond B by its wick: the instance is kept whole and stops
  recording, and a **gap without an active Fibonacci** opens;
* the gap **closes** when a new instance in the same direction, whose B lies beyond the old one, is
  born, or when the price goes beyond A by its wick before the new extreme is confirmed (the
  candidate is abandoned).

Every record carries the market time of the event and the instant Freyja received the candle that
proved it (None if unknown): the interval between the two stays visible and is never rewritten.
Nothing here is a zone, a confirmation of a rejection, an entry, an expiry or a signal.

The replay is a reference implementation (it searches again at every instant): correct and simple,
not incremental.
"""

import enum
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from freyja_backend.domain.fibonacci import Impulse, ImpulseDirection
from freyja_backend.domain.fibonacci_detection import FibonacciSeries, search_impulses
from freyja_backend.domain.market_data import Candle, Timeframe

FIBONACCI_EXTENSION_POLICY_VERSION = "fibonacci-extension-policy-v1"

_NAMESPACE = uuid.UUID("6d1a9f42-3c7e-5b08-a4d3-91e2c0b7f581")


class InvalidLifecycleRecordError(ValueError):
    """A record that breaks the rules of the lifecycle: a defect, never bad data."""


class LifecycleKind(enum.StrEnum):
    INSTANCE_BORN = "INSTANCE_BORN"
    EXTENSION_DETECTED = "EXTENSION_DETECTED"
    GAP_OPENED = "GAP_OPENED"
    GAP_CLOSED = "GAP_CLOSED"


class GapClosure(enum.StrEnum):
    NEW_INSTANCE = "NEW_INSTANCE"
    CANDIDATE_ABANDONED = "CANDIDATE_ABANDONED"


class InstanceState(enum.StrEnum):
    ACTIVE = "ACTIVE"
    EXTENDED = "EXTENDED"  # final: the instance is kept whole and records nothing more


def _require_utc(moment: datetime | None, name: str) -> None:
    if moment is not None and (moment.tzinfo is None or moment.utcoffset() is None):
        raise InvalidLifecycleRecordError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class FibonacciInstance:
    """A Fibonacci as it became known. Immutable: it is never recalculated or redrawn."""

    instance_id: uuid.UUID
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    impulse: Impulse
    parameter_version: str
    levels_version: str
    convention_version: str
    search_version: str
    # Both times, kept apart (contract, section 3).
    pivot_confirmed_market_time: datetime
    pivot_received_at: datetime | None
    known_at: datetime | None

    @property
    def direction(self) -> ImpulseDirection:
        return self.impulse.direction


def derive_instance_id(series: FibonacciSeries, impulse: Impulse) -> uuid.UUID:
    """The identity of a Fibonacci: the series, the two anchors and the versions behind it."""
    params = series.params
    key = "|".join(
        (
            series.instrument_id,
            series.data_source,
            series.timeframe.value,
            impulse.direction.value,
            impulse.start.open_time.isoformat(),
            impulse.start.kind.value,
            impulse.end.open_time.isoformat(),
            impulse.end.kind.value,
            params.version,
            params.levels_version,
            params.convention_version,
            params.search_version,
        )
    )
    return uuid.uuid5(_NAMESPACE, key)


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    """One fact about the life of a Fibonacci, appended when Freyja learned it (`recorded_at`)."""

    sequence: int
    kind: LifecycleKind
    recorded_at: datetime
    instance_id: uuid.UUID
    # When the event happened in the market, and when Freyja received the candle that proved it.
    market_time: datetime | None
    received_at: datetime | None
    # EXTENSION_DETECTED: the opening of the candle that went beyond B; the old instance observes
    # nothing from there on.
    coverage_end: datetime | None = None
    # GAP_CLOSED only.
    closure: GapClosure | None = None
    successor_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        for name in ("recorded_at", "market_time", "received_at", "coverage_end"):
            _require_utc(getattr(self, name), name)
        if isinstance(self.sequence, bool) or self.sequence < 0:
            raise InvalidLifecycleRecordError("sequence must be a non-negative integer")
        if (self.kind is LifecycleKind.EXTENSION_DETECTED) != (self.coverage_end is not None):
            raise InvalidLifecycleRecordError("only an extension has a coverage_end, and it must")
        if (self.kind is LifecycleKind.GAP_CLOSED) != (self.closure is not None):
            raise InvalidLifecycleRecordError("only a closed gap has a closure, and it must")
        if (self.closure is GapClosure.NEW_INSTANCE) != (self.successor_id is not None):
            raise InvalidLifecycleRecordError("a successor exists when a gap closes with one")
        if (
            self.received_at is not None
            and self.market_time is not None
            and self.received_at < self.market_time
        ):
            raise InvalidLifecycleRecordError("a candle cannot be received before it closes")


@dataclass(frozen=True, slots=True)
class Gap:
    """An interval without an active Fibonacci, derived from the records, never stored apart."""

    instance_id: uuid.UUID
    extension: LifecycleRecord
    opened: LifecycleRecord
    closed: LifecycleRecord | None

    @property
    def is_open(self) -> bool:
        return self.closed is None

    @property
    def uncertainty(self) -> tuple[datetime | None, datetime | None]:
        """`(coverage_end, extension_received_at)`: in that interval the old instance still looked
        valid to Freyja though the market had already gone beyond B. `extension_received_at` is None
        if the receipt is unknown."""
        return (self.extension.coverage_end, self.extension.received_at)


@dataclass(frozen=True, slots=True)
class FibonacciHistory:
    instances: tuple[FibonacciInstance, ...]
    records: tuple[LifecycleRecord, ...]

    def state_of(self, instance_id: uuid.UUID) -> InstanceState:
        extended = any(
            r.instance_id == instance_id and r.kind is LifecycleKind.EXTENSION_DETECTED
            for r in self.records
        )
        return InstanceState.EXTENDED if extended else InstanceState.ACTIVE

    def extension_of(self, instance_id: uuid.UUID) -> LifecycleRecord | None:
        return next(
            (
                r
                for r in self.records
                if r.instance_id == instance_id and r.kind is LifecycleKind.EXTENSION_DETECTED
            ),
            None,
        )

    def gaps(self) -> tuple[Gap, ...]:
        found = []
        for opened in (r for r in self.records if r.kind is LifecycleKind.GAP_OPENED):
            closed = next(
                (
                    r
                    for r in self.records
                    if r.kind is LifecycleKind.GAP_CLOSED and r.instance_id == opened.instance_id
                ),
                None,
            )
            extension = next(
                r
                for r in self.records
                if r.kind is LifecycleKind.EXTENSION_DETECTED
                and r.instance_id == opened.instance_id
            )
            found.append(Gap(opened.instance_id, extension, opened, closed))
        return tuple(found)


def _beyond(direction: ImpulseDirection, candle: Candle, price: Decimal) -> bool:
    """A wick beyond a price, on the side the impulse points to: above a bullish B, below a bearish
    one. Strict: an equal wick is not beyond."""
    if direction is ImpulseDirection.BULLISH:
        return candle.high > price
    return candle.low < price


def _beyond_start(direction: ImpulseDirection, candle: Candle, price: Decimal) -> bool:
    """A wick beyond A, against the impulse: below a bullish A, above a bearish one."""
    if direction is ImpulseDirection.BULLISH:
        return candle.low < price
    return candle.high > price


@dataclass(slots=True)
class _Open:
    """A gap that is open: what closes it depends on where the extension happened."""

    old: FibonacciInstance
    extension_open: datetime


def replay_lifecycle(
    series: FibonacciSeries,
    candles: Sequence[Candle],
    *,
    received_at: Mapping[datetime, datetime] | None = None,
) -> FibonacciHistory:
    """The history a live watcher would have built by following the series as it arrived.

    The instants are those at which Freyja learned something: the close of each candle or, if
    `received_at` maps each candle's open time to when Freyja really received it, those receipts. At
    each instant only the candles closed **and received** by then are read, so nothing depends on
    what came later, and the records only ever grow. When the data is not fit to judge at an
    instant, nothing is claimed at it (fail-closed): what it would have shown appears when the data
    is fit again, recorded at that later instant."""
    ordered = sorted(candles, key=lambda c: c.open_time)
    receipts = None if received_at is None else dict(received_at)
    if receipts is None:
        instants = sorted({c.close_time for c in ordered})
    else:
        instants = sorted({receipts[c.open_time] for c in ordered if c.open_time in receipts})

    instances: dict[uuid.UUID, FibonacciInstance] = {}
    records: list[LifecycleRecord] = []
    extended: dict[uuid.UUID, Candle] = {}
    open_gaps: dict[uuid.UUID, _Open] = {}

    def receipt_of(candle: Candle) -> datetime | None:
        return None if receipts is None else receipts.get(candle.open_time)

    def add(
        kind: LifecycleKind,
        at: datetime,
        instance_id: uuid.UUID,
        *,
        market_time: datetime,
        received_at: datetime | None,
        coverage_end: datetime | None = None,
        closure: GapClosure | None = None,
        successor_id: uuid.UUID | None = None,
    ) -> None:
        records.append(
            LifecycleRecord(
                len(records),
                kind,
                at,
                instance_id,
                market_time,
                received_at,
                coverage_end,
                closure,
                successor_id,
            )
        )

    for now in instants:
        visible = [
            c
            for c in ordered
            if c.close_time <= now
            and (receipts is None or (c.open_time in receipts and receipts[c.open_time] <= now))
        ]
        if not visible:
            continue
        found = search_impulses(series.at(now), visible)
        if found.unfit_reasons:
            continue

        # 1. A candle beyond B: the instance is extended and a gap opens.
        for instance in list(instances.values()):
            if instance.instance_id in extended:
                continue
            end = instance.impulse.end
            beyond = next(
                (
                    c
                    for c in visible
                    if c.open_time > end.open_time and _beyond(instance.direction, c, end.price)
                ),
                None,
            )
            if beyond is None:
                continue
            extended[instance.instance_id] = beyond
            add(
                LifecycleKind.EXTENSION_DETECTED,
                now,
                instance.instance_id,
                market_time=beyond.close_time,
                received_at=receipt_of(beyond),
                coverage_end=beyond.open_time,
            )
            add(
                LifecycleKind.GAP_OPENED,
                now,
                instance.instance_id,
                market_time=beyond.close_time,
                received_at=receipt_of(beyond),
            )
            open_gaps[instance.instance_id] = _Open(instance, beyond.open_time)

        # 2. The price beyond A before the new extreme is confirmed: the candidate is abandoned.
        for instance_id, gap in list(open_gaps.items()):
            start = gap.old.impulse.start
            broke = next(
                (
                    c
                    for c in visible
                    if c.open_time >= gap.extension_open
                    and _beyond_start(gap.old.direction, c, start.price)
                ),
                None,
            )
            if broke is None:
                continue
            add(
                LifecycleKind.GAP_CLOSED,
                now,
                instance_id,
                market_time=broke.close_time,
                received_at=receipt_of(broke),
                closure=GapClosure.CANDIDATE_ABANDONED,
            )
            del open_gaps[instance_id]

        # 3. Impulses that are now known: new instances, and the gaps they close.
        for impulse in found.impulses:
            instance_id = derive_instance_id(series, impulse)
            if instance_id in instances:
                continue
            confirming = next(
                (c for c in visible if c.close_time == impulse.pivot_confirmed_market_time), None
            )
            pivot_received = None if confirming is None else receipt_of(confirming)
            known = (
                None
                if pivot_received is None
                else max(impulse.pivot_confirmed_market_time, pivot_received)
            )
            params = series.params
            born = FibonacciInstance(
                instance_id,
                series.instrument_id,
                series.data_source,
                series.timeframe,
                impulse,
                params.version,
                params.levels_version,
                params.convention_version,
                params.search_version,
                impulse.pivot_confirmed_market_time,
                pivot_received,
                known,
            )
            instances[instance_id] = born
            add(
                LifecycleKind.INSTANCE_BORN,
                now,
                instance_id,
                market_time=impulse.pivot_confirmed_market_time,
                received_at=pivot_received,
            )
            for old_id, gap in list(open_gaps.items()):
                old = gap.old
                further = (
                    impulse.end.price > old.impulse.end.price
                    if old.direction is ImpulseDirection.BULLISH
                    else impulse.end.price < old.impulse.end.price
                )
                if (
                    impulse.direction is old.direction
                    and further
                    and impulse.end.open_time >= gap.extension_open
                ):
                    add(
                        LifecycleKind.GAP_CLOSED,
                        now,
                        old_id,
                        market_time=impulse.pivot_confirmed_market_time,
                        received_at=pivot_received,
                        closure=GapClosure.NEW_INSTANCE,
                        successor_id=instance_id,
                    )
                    del open_gaps[old_id]

    return FibonacciHistory(tuple(instances.values()), tuple(records))
