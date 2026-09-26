"""FIB-DETECT-001 (second part): the life of a Fibonacci over time.

Expected records are written from the contract (``docs/domain/fibonacci-retroceso.md``, sections 3,
5 and 17): when an instance is born, when it is extended, when a gap without an active Fibonacci
opens and closes, and the two times each record carries. Series are built leg by leg (ten candles
per leg); instants are counted in candles from ``T0``. A swing "at 140" has its high at 140.5.
"""

import ast
import dataclasses
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import fibonacci_lifecycle
from freyja_backend.domain.fibonacci import ImpulseDirection
from freyja_backend.domain.fibonacci_detection import FibonacciSeries
from freyja_backend.domain.fibonacci_lifecycle import (
    FibonacciHistory,
    FibonacciInstance,
    GapClosure,
    InstanceState,
    InvalidLifecycleRecordError,
    LifecycleKind,
    LifecycleRecord,
    replay_lifecycle,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_data import Candle, Timeframe
from tests.unit.test_market_trend import AUTHORIZED, BTC, SOURCE, T0, UP, candle_at, zigzag

D = Decimal
REPO = Path(__file__).resolve().parents[3]
BULLISH, BEARISH = ImpulseDirection.BULLISH, ImpulseDirection.BEARISH
STEP = Timeframe.M5.duration
K = 3

# The staircase, a pullback to 118, the high of 140 (B, candle 130), a pullback to 126, a rally to
# 150 (B', candle 150, beyond B) and a fall to 135. The first candle to go beyond B = 140.5 is the
# one that opens at candle 146 (mid 141.2, high 141.7? see below), and it closes at candle 147.
EXTENDED: list[int | str] = [*UP, 118, 140, 126, 150, 135]


def mirror(extremes: Sequence[int | str]) -> list[int | str]:
    return [str(D(300) - D(str(e))) for e in extremes]


def series_for(candles: Sequence[Candle], timeframe: Timeframe = Timeframe.M5) -> FibonacciSeries:
    return FibonacciSeries(
        instrument_id="instrument-1",
        instrument=BTC,
        schedule=MarketSchedule.CONTINUOUS_24_7,
        data_source=SOURCE,
        authorized_sources=AUTHORIZED,
        timeframe=timeframe,
        observed_at=candles[-1].close_time,
    )


def at(candles_from_t0: int, step: timedelta = STEP) -> datetime:
    return T0 + step * candles_from_t0


def instance_with(
    history: FibonacciHistory, direction: ImpulseDirection, start: str, end: str
) -> FibonacciInstance:
    (found,) = [
        i
        for i in history.instances
        if i.direction is direction
        and str(i.impulse.start.price) == start
        and str(i.impulse.end.price) == end
    ]
    return found


def records_of(history: FibonacciHistory, instance: FibonacciInstance) -> list[LifecycleRecord]:
    return [r for r in history.records if r.instance_id == instance.instance_id]


def delivered(
    candles: Sequence[Candle],
    delay: timedelta = timedelta(0),
    late: dict[datetime, timedelta] | None = None,
) -> dict[datetime, datetime]:
    """When each finished candle reached Freyja: `delay` after it closed, and more for some."""
    extra = late or {}
    return {
        c.open_time: c.close_time + delay + extra.get(c.open_time, timedelta(0)) for c in candles
    }


# -- the life of the Fibonacci that gets extended -----------------------------------------------


def test_an_instance_is_born_when_its_pivot_is_confirmed() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    # B is candle 130; its three following candles close at candle 134: that is when the pivot is
    # confirmed in the market, and (nothing being said about receipts) all that is known.
    assert old.pivot_confirmed_market_time == at(134)
    assert old.pivot_received_at is None and old.known_at is None
    (born,) = [r for r in records_of(history, old) if r.kind is LifecycleKind.INSTANCE_BORN]
    assert born.recorded_at == at(134) and born.market_time == at(134)
    assert history.state_of(old.instance_id) is InstanceState.EXTENDED  # see the next test
    assert old.parameter_version == "fibonacci-params-v1"
    assert old.search_version == "fibonacci-search-v1" and old.convention_version.startswith("fib")


def test_a_candle_beyond_b_extends_the_instance_and_opens_a_gap_with_its_times() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    # The rally from 126 (candle 140) to 150 (candle 150) rises 2.4 a candle: the first candle whose
    # high (mid + 0.5) is above 140.5 is the one that opens at candle 146 (mid 140.4, high 140.9).
    extension = history.extension_of(old.instance_id)
    assert extension is not None and extension.kind is LifecycleKind.EXTENSION_DETECTED
    assert extension.coverage_end == at(146)  # the old instance observes nothing from here on
    assert extension.market_time == at(147)  # the candle closes: the market has gone beyond B
    assert extension.recorded_at == at(147)  # and that is when Freyja learned it (no receipts)
    assert extension.received_at is None
    kinds = [r.kind for r in records_of(history, old)]
    assert kinds == [
        LifecycleKind.INSTANCE_BORN,
        LifecycleKind.EXTENSION_DETECTED,
        LifecycleKind.GAP_OPENED,
        LifecycleKind.GAP_CLOSED,
    ]
    opened = records_of(history, old)[2]
    assert opened.market_time == at(147) and opened.recorded_at == at(147)


def test_the_gap_closes_when_the_new_instance_is_known_and_that_moment_is_recorded() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    new = instance_with(history, BULLISH, "110.5", "150.5")
    # B' is candle 150; its three following candles close at candle 154.
    assert new.pivot_confirmed_market_time == at(154)
    closed = records_of(history, old)[-1]
    assert closed.kind is LifecycleKind.GAP_CLOSED
    assert closed.closure is GapClosure.NEW_INSTANCE and closed.successor_id == new.instance_id
    assert closed.recorded_at == at(154) and closed.market_time == at(154)
    # The new instance has its own start: the old low fell out of the search window. It is another
    # Fibonacci, not the old one redrawn.
    assert new.impulse.start.price != old.impulse.start.price
    assert new.instance_id != old.instance_id
    assert history.state_of(new.instance_id) is InstanceState.ACTIVE
    # Between the extension (147) and the birth of the new one (154) nothing was active for B.
    (gap,) = [g for g in history.gaps() if g.instance_id == old.instance_id]
    assert not gap.is_open and gap.opened.recorded_at == at(147)
    assert gap.closed is not None and gap.closed.recorded_at == at(154)


def test_the_extended_instance_is_kept_whole_and_never_rewritten() -> None:
    candles = zigzag(EXTENDED)
    full = replay_lifecycle(series_for(candles), candles)
    old = instance_with(full, BULLISH, "106.5", "140.5")
    # The same instance, exactly, in a history that stops before the extension.
    before = candles[:145]
    early = replay_lifecycle(series_for(before), before)
    assert instance_with(early, BULLISH, "106.5", "140.5") == old
    assert early.state_of(old.instance_id) is InstanceState.ACTIVE
    assert early.extension_of(old.instance_id) is None
    # And what was recorded before is a prefix of what is recorded later (append-only).
    known = [r for r in full.records if r.recorded_at <= before[-1].close_time]
    assert list(early.records) == known


# -- an instance that is never extended ---------------------------------------------------------


def test_an_instance_the_price_never_goes_beyond_stays_active_with_only_its_birth() -> None:
    candles = zigzag([*UP, 118, 140, 126, 133, 128])
    history = replay_lifecycle(series_for(candles), candles)
    top = instance_with(history, BULLISH, "106.5", "140.5")
    assert history.state_of(top.instance_id) is InstanceState.ACTIVE
    assert [r.kind for r in records_of(history, top)] == [LifecycleKind.INSTANCE_BORN]
    assert not [g for g in history.gaps() if g.instance_id == top.instance_id]


# -- the two times ------------------------------------------------------------------------------


def test_with_receipts_the_instance_is_known_when_the_confirming_candle_arrived() -> None:
    candles = zigzag(EXTENDED)
    confirming = candles[133]  # the third candle after B: it closes at candle 134
    late = {confirming.open_time: timedelta(seconds=150)}
    receipts = delivered(candles, late=late)
    history = replay_lifecycle(series_for(candles), candles, received_at=receipts)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    assert old.pivot_confirmed_market_time == at(134)  # the market's, unchanged
    assert old.pivot_received_at == at(134) + timedelta(seconds=150)
    assert old.known_at == old.pivot_received_at
    (born,) = [r for r in records_of(history, old) if r.kind is LifecycleKind.INSTANCE_BORN]
    assert born.market_time == at(134) and born.received_at == old.pivot_received_at
    assert born.recorded_at == old.pivot_received_at  # learned when it arrived, not when it closed


def test_a_late_extension_candle_leaves_a_visible_interval_of_uncertainty() -> None:
    candles = zigzag(EXTENDED)
    extension_candle = candles[146]  # the first candle beyond B: opens at 146, closes at 147
    late = {extension_candle.open_time: timedelta(seconds=200)}
    receipts = delivered(candles, late=late)
    history = replay_lifecycle(series_for(candles), candles, received_at=receipts)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    extension = history.extension_of(old.instance_id)
    assert extension is not None
    assert extension.coverage_end == at(146)
    assert extension.market_time == at(147)  # the market went beyond B here...
    assert extension.received_at == at(147) + timedelta(seconds=200)  # ...Freyja learned it here
    assert extension.recorded_at == extension.received_at
    (gap,) = [g for g in history.gaps() if g.instance_id == old.instance_id]
    # For Freyja the old instance looked valid until 147:03:20: an interval that stays visible.
    assert gap.uncertainty == (at(146), at(147) + timedelta(seconds=200))
    assert gap.opened.received_at == extension.received_at


def test_a_history_with_receipts_is_the_same_story_in_market_time() -> None:
    candles = zigzag(EXTENDED)
    plain = replay_lifecycle(series_for(candles), candles)
    receipts = replay_lifecycle(series_for(candles), candles, received_at=delivered(candles))

    def story(history: FibonacciHistory) -> list[Any]:
        return [(r.kind, r.market_time, r.recorded_at, r.closure) for r in history.records]

    assert story(receipts) == story(plain)  # instant delivery changes nothing but adds receipts
    assert all(r.received_at is not None for r in receipts.records)


# -- the candidate is replaced or abandoned -----------------------------------------------------


def path(prefix: list[int | str], mids: list[str]) -> list[Candle]:
    """The series of `prefix` (without its tail), then one candle per mid in `mids`."""
    base = zigzag(prefix, tail=0)
    start = len(base)
    extra = [candle_at(T0 + STEP * (start + n), D(m), STEP) for n, m in enumerate(mids)]
    return [*base, *extra]


def test_a_higher_extreme_before_the_candidate_is_confirmed_replaces_it() -> None:
    """The rally to 150 does not stop there: 151 and 153 follow at once, so 150 never becomes a
    pivot (a higher wick comes within three candles). The candidate is the peak of 153. Nothing is
    ever born for the discarded one, and the gap stays open until the final peak is known."""
    candles = path(
        [*UP, 118, 140, 126, 150],
        ["149", "151", "152", "153", "150", "148", "146", "144", "142", "140"],
    )
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    assert not [i for i in history.instances if str(i.impulse.end.price) == "150.5"]
    (peak,) = [i for i in history.instances if str(i.impulse.end.price) == "153.5"]
    closes = [r for r in records_of(history, old) if r.kind is LifecycleKind.GAP_CLOSED]
    assert len(closes) == 1 and closes[0].successor_id == peak.instance_id
    # The peak is at candle 154 (150 is 150, then 149, 151, 152 and 153 at candle 154); it is
    # confirmed when the third candle after it closes.
    assert closes[0].recorded_at == peak.pivot_confirmed_market_time
    assert closes[0].recorded_at > at(150 + K + 1)  # later than it would have been for 150


def test_the_price_going_beyond_a_before_the_new_extreme_is_known_abandons_the_candidate() -> None:
    """The rally to 145 peaks at candle 150 and the next candle already falls to 90, below the old
    start (106.5). That happens before the peak is confirmed (candle 154), so the gap closes as an
    abandoned candidate. The peak is still a valid impulse and, once known, is born on its own: it
    does not close a gap that is already closed."""
    candles = path([*UP, 118, 140, 126, 145], ["90", "88", "86", "85"])
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    kinds = [(r.kind, r.closure) for r in records_of(history, old)]
    assert kinds == [
        (LifecycleKind.INSTANCE_BORN, None),
        (LifecycleKind.EXTENSION_DETECTED, None),
        (LifecycleKind.GAP_OPENED, None),
        (LifecycleKind.GAP_CLOSED, GapClosure.CANDIDATE_ABANDONED),
    ]
    abandoned = records_of(history, old)[-1]
    assert abandoned.market_time == at(152)  # the candle of 90 opens at 151 and closes at 152
    assert abandoned.recorded_at == at(152) and abandoned.successor_id is None
    peak = [i for i in history.instances if str(i.impulse.end.price) == "145.5"]
    assert peak and peak[0].pivot_confirmed_market_time == at(154)
    closures = [
        r
        for r in history.records
        if r.closure is GapClosure.NEW_INSTANCE and r.recorded_at >= at(154)
    ]
    assert not closures  # the gap had closed already: nothing left for the peak to close


@pytest.mark.parametrize("upside_down", [False, True])
def test_a_wick_exactly_at_b_is_not_beyond_it(upside_down: bool) -> None:
    """A second high of exactly 140.5 (a double top) does not extend the first one: an equal wick is
    not beyond, in the search and in the lifecycle. Upside down, the same for a double bottom."""
    extremes: list[int | str] = [*UP, 118, 140, 126, 140, 130]
    candles = zigzag(mirror(extremes) if upside_down else extremes)
    history = replay_lifecycle(series_for(candles), candles)
    direction = BEARISH if upside_down else BULLISH
    end = "159.5" if upside_down else "140.5"
    tops = [
        i for i in history.instances if i.direction is direction and str(i.impulse.end.price) == end
    ]
    assert len(tops) == 2
    for top in tops:
        assert history.extension_of(top.instance_id) is None
        assert history.state_of(top.instance_id) is InstanceState.ACTIVE


@pytest.mark.parametrize("upside_down", [False, True])
def test_a_wick_exactly_at_a_does_not_abandon_the_candidate_but_one_beyond_it_does(
    upside_down: bool,
) -> None:
    """After the rally to 145 (the candidate), a candle whose low is exactly the old start (106.5)
    is not beyond it; the next one, a tenth lower, is. Upside down, the same at the top."""
    extremes: list[int | str] = [*UP, 118, 140, 126, 145]
    exact, beyond = ["107", "106.9"]
    if upside_down:
        extremes = mirror(extremes)
        exact, beyond = [str(D(300) - D(exact)), str(D(300) - D(beyond))]
    touching = path(extremes, [exact])
    history = replay_lifecycle(series_for(touching), touching)
    direction = BEARISH if upside_down else BULLISH
    old = instance_with(
        history, direction, "193.5" if upside_down else "106.5", "159.5" if upside_down else "140.5"
    )
    assert not [r for r in records_of(history, old) if r.closure is GapClosure.CANDIDATE_ABANDONED]
    crossing = path(extremes, [exact, beyond])
    history = replay_lifecycle(series_for(crossing), crossing)
    closes = [r for r in records_of(history, old) if r.closure is GapClosure.CANDIDATE_ABANDONED]
    assert len(closes) == 1 and closes[0].market_time == crossing[-1].close_time


def test_a_candle_that_goes_beyond_b_and_beyond_a_at_once_extends_and_abandons_together() -> None:
    base = zigzag([*UP, 118, 140, 126], tail=0)
    wide = dataclasses.replace(
        candle_at(base[-1].close_time, D("125"), STEP), high=D("150"), low=D("100")
    )
    candles = [*base, wide]
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    kinds = [(r.kind, r.closure) for r in records_of(history, old)]
    assert kinds == [
        (LifecycleKind.INSTANCE_BORN, None),
        (LifecycleKind.EXTENSION_DETECTED, None),
        (LifecycleKind.GAP_OPENED, None),
        (LifecycleKind.GAP_CLOSED, GapClosure.CANDIDATE_ABANDONED),
    ]
    assert {r.recorded_at for r in records_of(history, old)[1:]} == {wide.close_time}


def test_a_single_spike_that_is_itself_the_peak_becomes_the_successor() -> None:
    """The candle that first goes beyond B is also the new extreme (a spike). Its own candle opens
    where the coverage of the old instance ends, and it is the B' that closes the gap."""
    candles = path([*UP, 118, 140, 126], ["146", "132", "130", "128", "126", "124"])
    history = replay_lifecycle(series_for(candles), candles)
    old = instance_with(history, BULLISH, "106.5", "140.5")
    extension = history.extension_of(old.instance_id)
    assert extension is not None
    (spike,) = [i for i in history.instances if str(i.impulse.end.price) == "146.5"]
    assert spike.impulse.end.open_time == extension.coverage_end  # the same candle
    closed = records_of(history, old)[-1]
    assert closed.closure is GapClosure.NEW_INSTANCE and closed.successor_id == spike.instance_id


def test_two_successive_extensions_each_close_the_gap_of_their_own_instance_once() -> None:
    candles = zigzag([*UP, 118, 140, 126, 150, 138, 160, 145])
    history = replay_lifecycle(series_for(candles), candles)
    first = instance_with(history, BULLISH, "106.5", "140.5")
    closes = [r for r in records_of(history, first) if r.kind is LifecycleKind.GAP_CLOSED]
    assert len(closes) == 1  # closed by the first successor and never again by the second
    second = next(i for i in history.instances if str(i.impulse.end.price) == "150.5")
    assert closes[0].successor_id == second.instance_id
    later = [r for r in records_of(history, second) if r.kind is LifecycleKind.GAP_CLOSED]
    assert len(later) == 1 and later[0].successor_id != second.instance_id


def test_a_late_extension_candle_is_not_read_before_it_arrives() -> None:
    """The first candle beyond B arrives 400 s late (more than a whole candle): the candle after it
    arrives first. Until the late one is received nothing is claimed about it."""
    candles = zigzag(EXTENDED)
    extension_candle = candles[146]
    late = {extension_candle.open_time: timedelta(seconds=400)}
    history = replay_lifecycle(
        series_for(candles), candles, received_at=delivered(candles, late=late)
    )
    old = instance_with(history, BULLISH, "106.5", "140.5")
    extension = history.extension_of(old.instance_id)
    assert extension is not None
    arrival = at(147) + timedelta(seconds=400)
    assert extension.received_at == arrival and extension.recorded_at == arrival
    assert extension.coverage_end == at(146) and extension.market_time == at(147)


def test_two_fibonaccis_with_the_same_start_have_different_identities() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    by_start: dict[tuple[str, datetime], list[FibonacciInstance]] = {}
    for instance in history.instances:
        key = (instance.direction.value, instance.impulse.start.open_time)
        by_start.setdefault(key, []).append(instance)
    shared = [group for group in by_start.values() if len(group) > 1]
    assert shared  # the staircase gives several impulses from the same low
    for group in shared:
        assert len({i.instance_id for i in group}) == len(group)


# -- both directions, every timeframe -----------------------------------------------------------


def shape_of(history: FibonacciHistory, step: timedelta, origin: datetime) -> list[Any]:
    return [
        (
            r.kind.value,
            (r.recorded_at - origin) // step,
            (r.market_time - origin) // step if r.market_time else None,
            (r.coverage_end - origin) // step if r.coverage_end else None,
            r.closure.value if r.closure else None,
        )
        for r in history.records
    ]


def test_a_bearish_lifecycle_is_the_bullish_one_upside_down() -> None:
    up = zigzag(EXTENDED)
    down = zigzag(mirror(EXTENDED))
    up_history = replay_lifecycle(series_for(up), up)
    down_history = replay_lifecycle(series_for(down), down)
    assert shape_of(down_history, STEP, T0) == shape_of(up_history, STEP, T0)
    old = instance_with(down_history, BEARISH, "193.5", "159.5")  # 300 - 106.5, 300 - 140.5
    assert down_history.extension_of(old.instance_id) is not None
    assert instance_with(down_history, BEARISH, "189.5", "149.5")  # 300 - 110.5, 300 - 150.5


@pytest.mark.parametrize("timeframe", list(Timeframe), ids=lambda t: t.value)
def test_the_same_shape_has_the_same_life_on_every_timeframe(timeframe: Timeframe) -> None:
    origin = timeframe.floor(T0)
    reference = replay_lifecycle(series_for(zigzag(EXTENDED)), zigzag(EXTENDED))
    candles = zigzag(EXTENDED, timeframe=timeframe, start=origin)
    history = replay_lifecycle(series_for(candles, timeframe), candles)
    assert shape_of(history, timeframe.duration, origin) == shape_of(reference, STEP, T0)


# -- no look-ahead, append-only, determinism ----------------------------------------------------


def wild(candles: Sequence[Candle], after: datetime) -> list[Candle]:
    return [
        c if c.close_time <= after else candle_at(c.open_time, D(1 + i % 2) * 5000)
        for i, c in enumerate(candles)
    ]


def test_the_history_at_an_instant_depends_only_on_what_had_arrived_by_then() -> None:
    candles = zigzag(EXTENDED)
    full = replay_lifecycle(series_for(candles), candles)
    for cut in (110, 134, 147, 150, 154, 160):
        upto = candles[:cut]
        instant = upto[-1].close_time
        prefix = replay_lifecycle(series_for(upto), upto)
        assert list(prefix.records) == [r for r in full.records if r.recorded_at <= instant], cut
        future_is_noise = wild(candles, instant)[:cut] + wild(candles, instant)[cut:]
        noisy = replay_lifecycle(series_for(future_is_noise), future_is_noise)
        assert [r for r in noisy.records if r.recorded_at <= instant] == list(prefix.records), cut


def test_records_are_only_ever_appended_and_numbered_in_order() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    assert [r.sequence for r in history.records] == list(range(len(history.records)))
    times = [r.recorded_at for r in history.records]
    assert times == sorted(times)
    with pytest.raises(dataclasses.FrozenInstanceError):
        history.records[0].kind = LifecycleKind.GAP_OPENED  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        history.instances[0].known_at = at(1)  # type: ignore[misc]


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag(EXTENDED)
    assert replay_lifecycle(series_for(candles), candles) == replay_lifecycle(
        series_for(candles), candles
    )


def test_unordered_candles_give_the_same_history() -> None:
    candles = zigzag(EXTENDED)
    shuffled = list(reversed(candles))
    assert replay_lifecycle(series_for(candles), shuffled) == replay_lifecycle(
        series_for(candles), candles
    )


def test_while_the_data_is_not_fit_nothing_is_claimed() -> None:
    candles = zigzag(EXTENDED)
    holed = [c for i, c in enumerate(candles) if i != 105]
    history = replay_lifecycle(series_for(candles), holed)
    # With a hole inside the window the data is unfit for a hundred candles: no record is made in
    # that stretch (and what happens meanwhile is recorded once the data is fit again).
    unfit = [r for r in history.records if at(105) <= r.recorded_at < at(205)]
    assert unfit == []


def test_identities_depend_on_the_versions_and_the_anchors() -> None:
    candles = zigzag(EXTENDED)
    history = replay_lifecycle(series_for(candles), candles)
    ids = [i.instance_id for i in history.instances]
    assert len(set(ids)) == len(ids) and all(isinstance(i, uuid.UUID) for i in ids)
    tuned = dataclasses.replace(
        series_for(candles),
        params=dataclasses.replace(
            series_for(candles).params, search_version="fibonacci-search-v2"
        ),
    )
    other = replay_lifecycle(tuned, candles)
    assert {i.instance_id for i in other.instances}.isdisjoint(
        ids
    )  # another policy, other identities


# -- the records themselves ---------------------------------------------------------------------


def record(kind: LifecycleKind, **fields: Any) -> LifecycleRecord:
    base: dict[str, Any] = {
        "sequence": 0,
        "kind": kind,
        "recorded_at": at(1),
        "instance_id": uuid.uuid4(),
        "market_time": at(1),
        "received_at": None,
    }
    return LifecycleRecord(**{**base, **fields})


def test_a_record_must_be_coherent() -> None:
    record(LifecycleKind.INSTANCE_BORN)
    record(LifecycleKind.EXTENSION_DETECTED, coverage_end=at(0))
    record(LifecycleKind.GAP_CLOSED, closure=GapClosure.CANDIDATE_ABANDONED)
    record(LifecycleKind.GAP_CLOSED, closure=GapClosure.NEW_INSTANCE, successor_id=uuid.uuid4())
    naive = datetime(2026, 1, 5, 10, 0)
    for bad in (
        {"kind": LifecycleKind.EXTENSION_DETECTED},  # no coverage_end
        {"kind": LifecycleKind.INSTANCE_BORN, "coverage_end": at(0)},
        {"kind": LifecycleKind.GAP_CLOSED},  # no closure
        {"kind": LifecycleKind.GAP_OPENED, "closure": GapClosure.NEW_INSTANCE},
        {"kind": LifecycleKind.GAP_CLOSED, "closure": GapClosure.NEW_INSTANCE},  # no successor
        {
            "kind": LifecycleKind.GAP_CLOSED,
            "closure": GapClosure.CANDIDATE_ABANDONED,
            "successor_id": uuid.uuid4(),
        },
        {"kind": LifecycleKind.INSTANCE_BORN, "sequence": -1},
        {"kind": LifecycleKind.INSTANCE_BORN, "sequence": True},
        {"kind": LifecycleKind.INSTANCE_BORN, "recorded_at": naive},
        {"kind": LifecycleKind.INSTANCE_BORN, "market_time": naive},
        {"kind": LifecycleKind.INSTANCE_BORN, "received_at": at(0)},  # before it closed
    ):
        with pytest.raises(InvalidLifecycleRecordError):
            record(**bad)


def test_nothing_in_a_record_or_an_instance_attributes_entry_or_a_signal() -> None:
    forbidden = {
        "side_of_trade",
        "action",
        "position",
        "entry",
        "order",
        "signal",
        "confidence",
        "score",
        "probability",
        "recommendation",
        "target",
        "stop_loss",
        "take_profit",
        "expiry",
        "zone",
        "confirmation",
    }
    names = {f.name for f in dataclasses.fields(LifecycleRecord)}
    names |= {f.name for f in dataclasses.fields(FibonacciInstance)}
    assert names.isdisjoint(forbidden)


def test_the_lifecycle_only_reads_the_domain_never_a_pattern_an_indicator_or_a_float() -> None:
    allowed = {"enum", "uuid", "collections.abc", "dataclasses", "datetime", "decimal"}
    source = Path(str(fibonacci_lifecycle.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    assert not any(
        any(w in m for w in ("indicators", "pattern_", "market_trend")) for m in imported
    )
    assert "float(" not in source


def test_the_documented_lifecycle_is_the_implemented_one() -> None:
    text = (REPO / "docs" / "domain" / "fibonacci-retroceso.md").read_text(encoding="utf-8")
    section = text.split("## 17.")[1]
    for word in (
        "INSTANCE_BORN",
        "EXTENSION_DETECTED",
        "GAP_OPENED",
        "GAP_CLOSED",
        "NEW_INSTANCE",
        "CANDIDATE_ABANDONED",
        "coverage_end",
        "fibonacci-extension-policy-v1",
    ):
        assert word in section, word
    assert fibonacci_lifecycle.FIBONACCI_EXTENSION_POLICY_VERSION == "fibonacci-extension-policy-v1"
