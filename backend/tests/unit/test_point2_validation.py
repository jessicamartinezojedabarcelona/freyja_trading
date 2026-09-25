"""POINT2-TEST-001: validation of the whole of point 2 (context, trend, policy, snapshot).

The pieces are tested one by one in their own files. This file proves what only the whole
pipeline can: that with controlled temporal data Freyja decides *only* with what was
available at each instant, that the calendar facts it records are right on the days the clocks
change, and that none of it reaches outside the process. It also keeps the traceability
matrix of the task honest: every required check names the test that proves it, and that test
must still exist.
"""

import ast
import random
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import (
    context_snapshot,
    market_calendar,
    market_context,
    market_structure,
    market_trend,
    trend_policy,
)
from freyja_backend.domain.context_snapshot import (
    ContextSnapshot,
    capture_context_snapshot,
    snapshot_from_document,
)
from freyja_backend.domain.market_calendar import MarketSchedule, MarketSession
from freyja_backend.domain.market_data import Candle, Timeframe
from freyja_backend.domain.market_trend import TrendState, TrendTimeframes
from freyja_backend.domain.trend_policy import Orientation, PolicyOutcome
from tests.unit.test_context_snapshot import (
    CONTEXT_TF,
    SIGNAL_TF,
    TIMEFRAMES,
    capture,
    policy,
)
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    EURUSD,
    SOURCE,
    T0,
    candle_at,
    hourly,
    observed_after,
    zigzag,
)
from tests.unit.test_market_trend import UP as UP_EXTREMES

TESTS = Path(__file__).resolve().parents[1]
BULLISH = Orientation.BULLISH

# -- the pipeline, on controlled temporal data ------------------------------------------------


def walk(seed: int, count: int, timeframe: Timeframe, start: datetime) -> list[Candle]:
    """A seeded random walk on the timeframe's grid: reproducible, and it does trend."""
    rng = random.Random(seed)
    price = 100_000  # cents
    out: list[Candle] = []
    for i in range(count):
        opened = price
        price = max(1000, price + rng.randint(-300, 300))
        out.append(
            Candle(
                open_time=start + timeframe.duration * i,
                close_time=start + timeframe.duration * (i + 1),
                open=Decimal(opened) / 100,
                high=Decimal(max(opened, price) + rng.randint(0, 150)) / 100,
                low=Decimal(min(opened, price) - rng.randint(0, 150)) / 100,
                close=Decimal(price) / 100,
                volume=Decimal("1"),
            )
        )
    return out


def snapshot_at(
    signal: list[Candle], context: list[Candle], observed_at: datetime, **overrides: Any
) -> ContextSnapshot:
    inputs: dict[str, Any] = {
        "timeframes": TIMEFRAMES,
        "policy": policy(),
        "orientation": BULLISH,
        "signal_candles": signal,
        "context_candles": context,
        "instrument_id": "instrument-1",
        "instrument": BTC,
        "schedule": MarketSchedule.CONTINUOUS_24_7,
        "observed_at": observed_at,
        "computed_at": observed_at + timedelta(minutes=30),
        "data_source": SOURCE,
        "authorized_sources": AUTHORIZED,
    }
    inputs.update(overrides)
    return capture_context_snapshot(**inputs)


def wild(candles: list[Candle], timeframe: Timeframe, after: datetime) -> list[Candle]:
    """The same series, but every candle that closes after `after` replaced by an extreme one."""
    return [
        c
        if c.close_time <= after
        else candle_at(c.open_time, Decimal(1 + i % 2) * 5000, timeframe.duration)
        for i, c in enumerate(candles)
    ]


_ANY_TREND = policy(
    version="strategy-any-trend-v1",
    relationship=trend_policy.TrendRelationship.ANY,
    context_states=frozenset(
        {TrendState.UPTREND, TrendState.DOWNTREND, TrendState.RANGE, TrendState.TRANSITION}
    ),
)


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_the_whole_pipeline_decides_only_with_what_was_available_at_each_instant(
    seed: int,
) -> None:
    """From candles to snapshot, at every instant: the snapshot made from the whole series
    (future included) is exactly the snapshot made from only the candles closed by then, and
    it does not change even if everything that happens later is rewritten."""
    signal_all = walk(seed, 400, SIGNAL_TF, T0 + timedelta(hours=150))
    context_all = walk(seed + 100, 200, CONTEXT_TF, T0)
    seen: set[tuple[TrendState, TrendState]] = set()
    outcomes: set[PolicyOutcome] = set()

    for i in range(100, 401, 3):
        observed_at = signal_all[i - 1].close_time + timedelta(seconds=15)
        past_signal = signal_all[:i]
        past_context = [c for c in context_all if c.close_time <= observed_at]
        rewritten_signal = wild(signal_all, SIGNAL_TF, observed_at)
        rewritten_context = wild(context_all, CONTEXT_TF, observed_at)

        for chosen in (policy(), _ANY_TREND):
            with_future = snapshot_at(signal_all, context_all, observed_at, policy=chosen)
            only_past = snapshot_at(past_signal, past_context, observed_at, policy=chosen)
            rewritten = snapshot_at(rewritten_signal, rewritten_context, observed_at, policy=chosen)

            assert with_future == only_past, f"seed {seed}, instant {i}"
            assert rewritten == only_past, f"seed {seed}, instant {i}: the future was read"
            assert with_future.content_hash == only_past.content_hash
            seen.add((with_future.signal.trend, with_future.context.trend))
            outcomes.add(with_future.outcome)

    # Not vacuous: the walks reach different states and the policies judge them differently.
    assert len(seen) >= 4
    assert len(outcomes) >= 2


def test_every_state_the_pipeline_can_reach_is_reached_and_recorded() -> None:
    reached: set[TrendState] = set()
    for seed in range(11, 21):
        signal_all = walk(seed, 400, SIGNAL_TF, T0 + timedelta(hours=150))
        context_all = walk(seed + 100, 200, CONTEXT_TF, T0)
        for i in range(100, 401, 5):
            observed_at = signal_all[i - 1].close_time + timedelta(seconds=15)
            snapshot = snapshot_at(
                signal_all[:i], [c for c in context_all if c.close_time <= observed_at], observed_at
            )
            reached |= {snapshot.signal.trend, snapshot.context.trend}
    reached |= {capture(context_candles=[]).context.trend}  # INSUFFICIENT_DATA: no candles
    assert reached == set(TrendState)


def test_a_snapshot_is_the_same_before_and_after_it_travels_through_json() -> None:
    signal_all = walk(11, 400, SIGNAL_TF, T0 + timedelta(hours=150))
    context_all = walk(111, 200, CONTEXT_TF, T0)
    for i in range(100, 401, 20):
        observed_at = signal_all[i - 1].close_time + timedelta(seconds=15)
        snapshot = snapshot_at(
            signal_all[:i], [c for c in context_all if c.close_time <= observed_at], observed_at
        )
        assert snapshot_from_document(snapshot.document()) == snapshot


# -- crypto has no weekend and no session --------------------------------------------------------


@pytest.mark.parametrize(
    ("saturday_or_sunday", "weekday"),
    [(datetime(2026, 1, 10, 3, 0, tzinfo=UTC), 5), (datetime(2026, 1, 11, 3, 0, tzinfo=UTC), 6)],
    ids=["saturday", "sunday"],
)
def test_crypto_at_the_weekend_is_open_classified_and_has_no_invented_session(
    saturday_or_sunday: datetime, weekday: int
) -> None:
    signal = zigzag(UP_EXTREMES, start=saturday_or_sunday)
    context = hourly(UP_EXTREMES, ending_with=signal)
    snapshot = capture(
        signal_candles=signal, context_candles=context, observed_at=observed_after(signal)
    )

    assert snapshot.weekday_utc == weekday
    assert snapshot.market_open is True  # crypto never closes
    assert snapshot.market_session is None  # and has no session to borrow from Forex
    assert snapshot.calendar_version is None
    assert (snapshot.signal.trend, snapshot.context.trend) == (
        TrendState.UPTREND,
        TrendState.UPTREND,
    )
    assert snapshot.outcome is PolicyOutcome.COMPATIBLE  # a weekend is not a reason to refuse


# -- Forex: sessions, the closed market and the days the clocks change ---------------------------

_MONDAY_WINTER = datetime(2026, 1, 5, tzinfo=UTC)


def forex_snapshot_at(instant: datetime) -> ContextSnapshot:
    """What is recorded about the calendar at `instant`, whatever the candles say."""
    return capture(
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
        signal_candles=[],
        context_candles=[],
        observed_at=instant,
    )


@pytest.mark.parametrize(
    ("instant", "session", "why"),
    [
        # The US changed its clocks on 8 March and the UK only on 29 March 2026, so for three
        # weeks the London/New York overlap is an hour earlier than in winter or in summer.
        (datetime(2026, 1, 7, 12, 30, tzinfo=UTC), MarketSession.LONDON, "winter: NY not open"),
        (datetime(2026, 1, 7, 13, 30, tzinfo=UTC), MarketSession.OVERLAP_LONDON_NEW_YORK, "winter"),
        (datetime(2026, 3, 5, 12, 30, tzinfo=UTC), MarketSession.LONDON, "before the US changes"),
        (
            datetime(2026, 3, 10, 12, 30, tzinfo=UTC),
            MarketSession.OVERLAP_LONDON_NEW_YORK,
            "US on DST, UK not",
        ),
        (
            datetime(2026, 4, 1, 12, 30, tzinfo=UTC),
            MarketSession.OVERLAP_LONDON_NEW_YORK,
            "both on DST",
        ),
        (
            datetime(2026, 9, 23, 12, 30, tzinfo=UTC),
            MarketSession.OVERLAP_LONDON_NEW_YORK,
            "summer",
        ),
        (
            datetime(2026, 9, 23, 6, 30, tzinfo=UTC),
            MarketSession.ASIA,
            "summer: London opens 07:00 UTC",
        ),
        (datetime(2026, 9, 23, 7, 30, tzinfo=UTC), MarketSession.LONDON, "summer: London open"),
        (
            datetime(2026, 10, 28, 12, 30, tzinfo=UTC),
            MarketSession.OVERLAP_LONDON_NEW_YORK,
            "UK back to GMT, US not",
        ),
        (
            datetime(2026, 11, 4, 12, 30, tzinfo=UTC),
            MarketSession.LONDON,
            "both back on winter time",
        ),
        (
            datetime(2026, 1, 7, 18, 30, tzinfo=UTC),
            MarketSession.NEW_YORK,
            "winter: New York (EST) is open until 22:00 UTC",
        ),
        (datetime(2026, 1, 7, 23, 30, tzinfo=UTC), MarketSession.ASIA, "winter: both shut"),
        (
            datetime(2026, 9, 23, 20, 30, tzinfo=UTC),
            MarketSession.NEW_YORK,
            "summer: New York (EDT) is open until 21:00 UTC",
        ),
        (datetime(2026, 9, 23, 21, 30, tzinfo=UTC), MarketSession.ASIA, "summer: both shut"),
    ],
)
def test_the_recorded_session_follows_the_local_clocks_on_every_side_of_a_clock_change(
    instant: datetime, session: MarketSession, why: str
) -> None:
    snapshot = forex_snapshot_at(instant)
    assert snapshot.market_session is session, why
    assert snapshot.market_open is True
    assert snapshot.calendar_version == market_calendar.FOREX_CALENDAR_VERSION
    assert snapshot.timezone == "UTC"  # what is recorded is in UTC; the clocks only decide


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        # Winter (EST, UTC-5): the week runs Sunday 22:00 UTC to Friday 22:00 UTC.
        (datetime(2026, 1, 4, 21, 59, tzinfo=UTC), False),
        (datetime(2026, 1, 4, 22, 0, tzinfo=UTC), True),
        (datetime(2026, 1, 9, 21, 59, tzinfo=UTC), True),
        (datetime(2026, 1, 9, 22, 0, tzinfo=UTC), False),
        # Summer (EDT, UTC-4): an hour earlier.
        (datetime(2026, 9, 27, 20, 59, tzinfo=UTC), False),
        (datetime(2026, 9, 27, 21, 0, tzinfo=UTC), True),
        (datetime(2026, 9, 25, 20, 59, tzinfo=UTC), True),
        (datetime(2026, 9, 25, 21, 0, tzinfo=UTC), False),
    ],
)
def test_the_week_opens_and_closes_an_hour_apart_in_winter_and_in_summer(
    instant: datetime, is_open: bool
) -> None:
    snapshot = forex_snapshot_at(instant)
    assert snapshot.market_open is is_open
    assert (snapshot.market_session is MarketSession.CLOSED) is (not is_open)


@pytest.mark.parametrize(
    "friday_close",
    [datetime(2026, 1, 9, 22, 0, tzinfo=UTC), datetime(2026, 9, 25, 21, 0, tzinfo=UTC)],
    ids=["winter", "summer"],
)
def test_a_closed_forex_weekend_is_not_a_reason_to_call_the_data_stale(
    friday_close: datetime,
) -> None:
    signal = zigzag(UP_EXTREMES, start=friday_close - Timeframe.M5.duration * 115)
    context = hourly(UP_EXTREMES, ending_with=signal)
    assert signal[-1].close_time == friday_close
    saturday = friday_close + timedelta(hours=14)

    snapshot = capture(
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
        signal_candles=signal,
        context_candles=context,
        observed_at=saturday,
    )

    assert snapshot.market_open is False
    assert snapshot.market_session is MarketSession.CLOSED
    assert (snapshot.signal.trend, snapshot.context.trend) == (
        TrendState.UPTREND,
        TrendState.UPTREND,
    )
    assert snapshot.context.data_freshness.value == "FRESH"
    assert snapshot.outcome is PolicyOutcome.COMPATIBLE


# -- nothing outside the process is ever reached ---------------------------------------------------

_POINT2_MODULES = (
    market_calendar,
    market_structure,
    market_context,
    market_trend,
    trend_policy,
    context_snapshot,
)
_STDLIB_ALLOWED = {
    "enum",
    "dataclasses",
    "datetime",
    "decimal",
    "itertools",
    "typing",
    "collections.abc",
    "zoneinfo",
    "hashlib",
    "json",
    "uuid",
}


@pytest.mark.parametrize("module", _POINT2_MODULES, ids=lambda module: module.__name__)
def test_each_module_of_point_2_imports_only_the_standard_library_and_the_domain(
    module: Any,
) -> None:
    tree = ast.parse(Path(str(module.__file__)).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    foreign = {
        name
        for name in imported
        if name not in _STDLIB_ALLOWED and not name.startswith("freyja_backend.domain")
    }
    assert foreign == set(), f"{module.__name__} reaches outside the domain: {foreign}"


def test_loading_point_2_loads_no_network_email_database_broker_or_application_code() -> None:
    """In a clean interpreter, importing everything of point 2 pulls in nothing that could
    talk to a broker, an executor, a database or an outside channel, not even indirectly."""
    program = (
        "import sys\n"
        "import freyja_backend.domain.market_calendar, freyja_backend.domain.market_structure\n"
        "import freyja_backend.domain.market_context, freyja_backend.domain.market_trend\n"
        "import freyja_backend.domain.trend_policy, freyja_backend.domain.context_snapshot\n"
        "forbidden = ('httpx', 'httpx2', 'requests', 'urllib3', 'aiohttp', 'smtplib', 'ssl',\n"
        "             'socket', 'sqlalchemy', 'psycopg', 'fastapi', 'starlette', 'websockets',\n"
        "             'freyja_backend.infrastructure', 'freyja_backend.application',\n"
        "             'freyja_backend.db', 'freyja_backend.api', 'freyja_backend.core.email')\n"
        "loaded = sorted(m for m in sys.modules if m in forbidden or m.startswith(\n"
        "    tuple(f + '.' for f in forbidden)))\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", result.stdout


def test_the_whole_pipeline_runs_with_the_network_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the pipeline tried to reach the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    signal = zigzag(UP_EXTREMES)
    context = hourly(UP_EXTREMES, ending_with=signal)
    snapshot = snapshot_at(signal, context, observed_after(signal))
    assert snapshot.outcome is PolicyOutcome.COMPATIBLE
    assert snapshot_from_document(snapshot.document()) == snapshot


def test_no_module_of_point_2_names_a_broker_client_an_executor_or_a_channel() -> None:
    """Names of what would act: `BROKER_DEFINED` (whose hours a schedule follows) is only a
    label, but a client, an executor, an order or a message sender would be a way out."""
    words = (
        "broker_client",
        "brokerclient",
        "executor",
        "execute_order",
        "place_order",
        "send_message",
        "send_email",
        "notify",
        "webhook",
        "smtp",
    )
    for module in _POINT2_MODULES:
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        names |= {
            node.name.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.ClassDef)
        }
        assert not {n for n in names if any(word in n for word in words)}, module.__name__


# -- traceability: every required check names the test that proves it --------------------

_MT = "unit/test_market_trend.py"
_MS = "unit/test_market_structure.py"
_MC = "unit/test_market_context.py"
_CAL = "unit/test_market_calendar.py"
_POL = "unit/test_trend_policy.py"
_SNAP = "unit/test_context_snapshot.py"
_PERSIST = "integration/test_context_snapshot_persistence.py"
_ARCH = "unit/test_architecture_guards.py"
_VAL = "unit/test_point2_validation.py"

TRACEABILITY: dict[str, list[tuple[str, str]]] = {
    "UPTREND, DOWNTREND, RANGE, TRANSITION and INSUFFICIENT_DATA": [
        (_MT, "test_higher_highs_and_higher_lows_are_an_uptrend"),
        (_MT, "test_lower_highs_and_lower_lows_are_a_downtrend"),
        (_MT, "test_limits_touched_again_and_again_are_a_range"),
        (_MT, "test_a_conflict_between_highs_and_lows_is_a_transition"),
        (_MT, "test_too_few_confirmed_swings_is_insufficient_data_not_a_guess"),
        (_VAL, "test_every_state_the_pipeline_can_reach_is_reached_and_recorded"),
    ],
    "provisional pivots against confirmed ones": [
        (_MS, "test_a_pivot_is_provisional_until_the_kth_candle_after_it_closes"),
        (_MS, "test_a_provisional_pivot_can_vanish_when_the_next_candle_beats_it"),
        (_MS, "test_a_confirmed_pivot_never_disappears_later"),
        (_MS, "test_swing_points_ignore_provisional_pivots"),
        (_SNAP, "test_a_provisional_swing_is_never_recorded_as_evidence"),
    ],
    "no look-ahead": [
        (_MS, "test_confirmed_pivots_at_any_instant_equal_those_computed_on_only_the_past"),
        (_MS, "test_changing_the_future_never_changes_what_was_already_knowable"),
        (_MT, "test_the_answer_at_any_instant_never_depends_on_what_came_after"),
        (_SNAP, "test_the_future_can_not_reach_the_snapshot"),
        (_VAL, "test_the_whole_pipeline_decides_only_with_what_was_available_at_each_instant"),
    ],
    "the open candle is excluded": [
        (_MS, "test_candles_closing_after_observed_at_are_ignored_not_used"),
        (_MC, "test_a_candle_still_in_progress_is_not_used"),
        (_MT, "test_a_candle_still_open_at_the_observed_instant_is_ignored"),
    ],
    "missing or late data": [
        (_MC, "test_data_that_is_too_old_is_stale_and_insufficient"),
        (_MC, "test_a_gap_inside_the_evaluated_window_is_insufficient"),
        (_MC, "test_no_candles_at_all_is_no_data"),
        (_MT, "test_stale_data_is_insufficient_data"),
        (_SNAP, "test_a_series_without_a_single_candle_is_recorded_as_no_data"),
    ],
    "both timeframes are classified independently": [
        (_MT, "test_signal_and_context_are_classified_independently_and_can_disagree"),
        (_MT, "test_one_timeframe_never_reads_the_other_s_candles"),
        (_MT, "test_an_insufficient_context_does_not_make_the_signal_insufficient"),
    ],
    "conflict between signal_trend and context_trend": [
        (_POL, "test_a_conflict_between_two_trends_is_judged_by_the_declared_rule"),
        (_SNAP, "test_a_conflict_is_recorded_with_the_rule_that_judged_it"),
    ],
    "the five trend relationships": [
        (_POL, "test_every_cell_of_the_contract_matrix"),
        (_POL, "test_any_never_admits_a_context_without_data"),
    ],
    "Forex sessions, closed market and summer/winter clock changes": [
        (_CAL, "test_sessions_follow_the_local_clocks_of_london_and_new_york"),
        (_CAL, "test_the_weekly_open_moves_an_hour_when_the_us_changes_its_clocks"),
        (_MC, "test_forex_records_the_session_and_the_calendar_version"),
        (_MC, "test_on_a_weekend_the_market_is_closed_and_data_from_friday_is_still_fresh"),
        (
            _VAL,
            "test_the_recorded_session_follows_the_local_clocks_on_every_side_of_a_clock_change",
        ),
        (_VAL, "test_the_week_opens_and_closes_an_hour_apart_in_winter_and_in_summer"),
        (_VAL, "test_a_closed_forex_weekend_is_not_a_reason_to_call_the_data_stale"),
    ],
    "crypto at the weekend, with no invented session": [
        (_MC, "test_crypto_records_the_utc_day_and_hour_and_never_invents_a_session"),
        (_VAL, "test_crypto_at_the_weekend_is_open_classified_and_has_no_invented_session"),
    ],
    "the snapshot is immutable and versioned": [
        (_SNAP, "test_a_snapshot_is_immutable"),
        (_SNAP, "test_a_reclassification_makes_a_new_snapshot_and_leaves_the_old_one_alone"),
        (_PERSIST, "test_no_column_of_a_stored_snapshot_can_be_rewritten"),
        (_PERSIST, "test_a_reclassification_is_a_new_snapshot_and_the_old_one_is_untouched"),
    ],
    "a strategy without a policy fails closed": [
        (_POL, "test_a_strategy_without_a_policy_answers_insufficient_context"),
        (_SNAP, "test_a_strategy_without_a_policy_is_recorded_as_such"),
    ],
    "no broker, executor or outside message is activated": [
        (_VAL, "test_each_module_of_point_2_imports_only_the_standard_library_and_the_domain"),
        (
            _VAL,
            "test_loading_point_2_loads_no_network_email_database_broker_or_application_code",
        ),
        (_VAL, "test_the_whole_pipeline_runs_with_the_network_switched_off"),
        (_VAL, "test_no_module_of_point_2_names_a_broker_client_an_executor_or_a_channel"),
        (_ARCH, "test_no_real_broker_or_exchange_client_code_exists"),
    ],
    "fixtures and mocks live only in tests": [
        (_ARCH, "test_no_production_code_imports_test_only_tooling"),
    ],
}


def _test_names(relative: str) -> set[str]:
    tree = ast.parse((TESTS / relative).read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_every_required_check_points_at_tests_that_exist() -> None:
    missing = [
        f"{requirement}: {relative}::{name}"
        for requirement, proofs in TRACEABILITY.items()
        for relative, name in proofs
        if name not in _test_names(relative)
    ]
    assert missing == [], "a required check lost its proof:\n" + "\n".join(missing)


def test_every_required_check_has_at_least_one_proof() -> None:
    assert all(proofs for proofs in TRACEABILITY.values())
    assert len(TRACEABILITY) == 14  # the fourteen mandatory checks of the task, none dropped


def test_the_timeframes_used_here_are_the_ones_the_policy_declares() -> None:
    assert TrendTimeframes(SIGNAL_TF, CONTEXT_TF, "cfg") == TIMEFRAMES
    assert policy().timeframes.signal is SIGNAL_TF
