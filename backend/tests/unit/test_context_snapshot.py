"""POINT2-SNAPSHOT-001: the immutable snapshot of a context.

Snapshots are captured from real candles (zigzags whose swings can be read off the numbers)
through the real classifier and the real policy: nothing is mocked or built by hand except
the records that are checked for validation.
"""

import ast
import dataclasses
import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import context_snapshot
from freyja_backend.domain.context_snapshot import (
    CONTEXT_SNAPSHOT_VERSION,
    ContextSnapshot,
    InvalidContextSnapshotError,
    capture_context_snapshot,
    snapshot_from_document,
)
from freyja_backend.domain.market_calendar import MarketSchedule, MarketSession, forex_session_at
from freyja_backend.domain.market_context import DataFreshness, MissingDataReason
from freyja_backend.domain.market_data import DataQuality, InvalidMarketDataError, Timeframe
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotStatus
from freyja_backend.domain.market_trend import (
    TREND_DEFINITION_VERSION,
    InsufficientDataReason,
    TrendParams,
    TrendState,
    TrendTimeframes,
)
from freyja_backend.domain.trend_policy import (
    ConflictRule,
    Orientation,
    PolicyOutcome,
    PolicyReason,
    TrendPolicy,
    TrendRelationship,
)
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    EURUSD,
    SOURCE,
    hourly,
    observed_after,
    zigzag,
)
from tests.unit.test_market_trend import DOWN as DOWN_EXTREMES
from tests.unit.test_market_trend import UP as UP_EXTREMES

SIGNAL_TF, CONTEXT_TF = Timeframe.M5, Timeframe.H1
TIMEFRAMES = TrendTimeframes(SIGNAL_TF, CONTEXT_TF, "cfg")
BULLISH, BEARISH = Orientation.BULLISH, Orientation.BEARISH
CLASSIFIABLE = frozenset(
    {
        TrendState.UPTREND,
        TrendState.DOWNTREND,
        TrendState.RANGE,
        TrendState.TRANSITION,
    }
)


def policy(**overrides: object) -> TrendPolicy:
    values: dict[str, object] = {
        "version": "strategy-x-trend-v1",
        "signal_timeframe": SIGNAL_TF,
        "context_timeframe": CONTEXT_TF,
        "relationship": TrendRelationship.WITH_TREND,
        "signal_states": CLASSIFIABLE,
        "context_states": frozenset({TrendState.UPTREND, TrendState.DOWNTREND}),
        "conflict_rule": ConflictRule.ALLOW_CONFLICT,
        "minimum_history": 100,
        "trend_definition_version": TREND_DEFINITION_VERSION,
    }
    values.update(overrides)
    return TrendPolicy(**values)  # type: ignore[arg-type]


class _Unset:
    """'Use the default policy' (None already means 'the strategy has no policy')."""


_UNSET = _Unset()


def capture(
    signal_extremes: list[int | str] = UP_EXTREMES,
    context_extremes: list[int | str] = UP_EXTREMES,
    *,
    trend_policy: TrendPolicy | None | _Unset = _UNSET,
    orientation: Orientation = BULLISH,
    computed_after: timedelta = timedelta(seconds=1),
    **overrides: Any,
) -> ContextSnapshot:
    signal = zigzag(signal_extremes)
    context = hourly(context_extremes, ending_with=signal)
    observed_at = overrides.pop("observed_at", observed_after(signal))
    inputs: dict[str, Any] = {
        "timeframes": TIMEFRAMES,
        "policy": policy() if isinstance(trend_policy, _Unset) else trend_policy,
        "orientation": orientation,
        "signal_candles": signal,
        "context_candles": context,
        "instrument_id": "instrument-1",
        "instrument": BTC,
        "schedule": MarketSchedule.CONTINUOUS_24_7,
        "observed_at": observed_at,
        "computed_at": observed_at + computed_after,
        "data_source": SOURCE,
        "authorized_sources": AUTHORIZED,
    }
    inputs.update(overrides)
    return capture_context_snapshot(**inputs)


# -- what a snapshot records ------------------------------------------------------------------


def test_a_compatible_snapshot_records_what_was_seen_and_why_it_fit() -> None:
    snapshot = capture()

    assert snapshot.snapshot_version == CONTEXT_SNAPSHOT_VERSION == "context-snapshot-v1"
    assert (snapshot.signal.timeframe, snapshot.context.timeframe) == (SIGNAL_TF, CONTEXT_TF)
    assert (snapshot.signal.trend, snapshot.context.trend) == (
        TrendState.UPTREND,
        TrendState.UPTREND,
    )
    assert snapshot.outcome is PolicyOutcome.COMPATIBLE
    assert snapshot.context_compatible is True
    assert snapshot.reasons == ()
    assert snapshot.required_relationship is TrendRelationship.WITH_TREND
    assert snapshot.policy_version == "strategy-x-trend-v1"
    assert snapshot.orientation is BULLISH
    assert snapshot.trend_definition_version == TREND_DEFINITION_VERSION
    assert snapshot.data_source == SOURCE and snapshot.product_type == "SPOT"
    assert snapshot.market_session is None  # crypto has no sessions, and none is borrowed
    assert snapshot.timezone == "UTC" and snapshot.calendar_version is None
    assert snapshot.observed_at.utcoffset() == timedelta(0)
    assert "signal 5m is UPTREND" in snapshot.explanation
    assert "context 1h is UPTREND" in snapshot.explanation
    assert "COMPATIBLE" in snapshot.explanation


def test_the_swings_the_states_rest_on_are_kept_exactly() -> None:
    snapshot = capture()

    for side in (snapshot.signal, snapshot.context):
        assert len(side.swings) == side.window_swings == 4
        assert all(isinstance(swing.price, Decimal) for swing in side.swings)
        assert all(swing.confirmed_at is not None for swing in side.swings)
        assert [s.kind for s in side.swings] == [
            PivotKind.LOW,
            PivotKind.HIGH,
            PivotKind.LOW,
            PivotKind.HIGH,
        ] or [s.kind for s in side.swings] == [
            PivotKind.HIGH,
            PivotKind.LOW,
            PivotKind.HIGH,
            PivotKind.LOW,
        ]
        assert side.evidence  # the human-readable facts that sustain the state
        assert side.significance == Decimal("0.15") and side.pivot_k == 3
        assert side.data_quality is DataQuality.OK and side.data_freshness is DataFreshness.FRESH
        assert side.as_of is not None and side.window_candles == 100


def test_an_incompatible_snapshot_says_why() -> None:
    snapshot = capture(UP_EXTREMES, DOWN_EXTREMES, orientation=BULLISH)

    assert (snapshot.signal.trend, snapshot.context.trend) == (
        TrendState.UPTREND,
        TrendState.DOWNTREND,
    )
    assert snapshot.outcome is PolicyOutcome.INCOMPATIBLE
    assert snapshot.context_compatible is False
    assert snapshot.reasons == (PolicyReason.RELATIONSHIP_NOT_SATISFIED,)
    assert "INCOMPATIBLE: RELATIONSHIP_NOT_SATISFIED" in snapshot.explanation


def test_a_conflict_is_recorded_with_the_rule_that_judged_it() -> None:
    reject = policy(
        relationship=TrendRelationship.ANY,
        context_states=CLASSIFIABLE,
        conflict_rule=ConflictRule.REJECT_ON_CONFLICT,
    )
    snapshot = capture(UP_EXTREMES, DOWN_EXTREMES, trend_policy=reject)

    assert snapshot.reasons == (PolicyReason.MULTITIMEFRAME_CONFLICT,)
    assert snapshot.required_relationship is TrendRelationship.ANY


def test_insufficient_data_is_recorded_with_its_reasons_never_as_a_label_alone() -> None:
    signal = zigzag(UP_EXTREMES)
    short_context = hourly(UP_EXTREMES, ending_with=signal)[-30:]  # 30 candles: < 100 needed
    snapshot = capture(context_candles=short_context)

    assert snapshot.context.trend is TrendState.INSUFFICIENT_DATA
    assert snapshot.context.insufficient_data_reasons == (
        InsufficientDataReason.INSUFFICIENT_HISTORY,
    )
    assert snapshot.context.missing_data_reasons == (MissingDataReason.INSUFFICIENT_HISTORY,)
    assert snapshot.context.swings == ()
    assert snapshot.signal.trend is TrendState.UPTREND  # the other timeframe is untouched
    assert snapshot.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert snapshot.context_compatible is None  # neither compatible nor incompatible
    assert PolicyReason.CONTEXT_TREND_INSUFFICIENT in snapshot.reasons
    assert "context 1h is INSUFFICIENT_DATA (INSUFFICIENT_HISTORY)" in snapshot.explanation


def test_a_series_without_a_single_candle_is_recorded_as_no_data() -> None:
    snapshot = capture(context_candles=[])

    assert snapshot.context.trend is TrendState.INSUFFICIENT_DATA
    assert snapshot.context.data_freshness is DataFreshness.NO_DATA
    assert snapshot.context.data_quality is DataQuality.UNAVAILABLE
    assert snapshot.context.as_of is None and snapshot.context.window_candles == 0
    assert snapshot.context.insufficient_data_reasons == (InsufficientDataReason.NO_DATA,)


def test_a_source_that_is_not_authorized_is_recorded_not_used() -> None:
    snapshot = capture(authorized_sources=frozenset({"SOMEONE_ELSE"}))

    for side in (snapshot.signal, snapshot.context):
        assert side.trend is TrendState.INSUFFICIENT_DATA
        assert side.missing_data_reasons == (MissingDataReason.SOURCE_NOT_AUTHORIZED,)
        assert side.swings == ()
    assert snapshot.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT


def test_a_strategy_without_a_policy_is_recorded_as_such() -> None:
    snapshot = capture(trend_policy=None)

    assert snapshot.policy_version is None and snapshot.required_relationship is None
    assert snapshot.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert snapshot.reasons == (PolicyReason.POLICY_MISSING,)
    assert snapshot.context_compatible is None
    assert "no trend policy was declared" in snapshot.explanation
    # What was observed is recorded all the same.
    assert snapshot.context.trend is TrendState.UPTREND


def test_forex_records_its_session_and_calendar_version() -> None:
    signal = zigzag(UP_EXTREMES)
    observed_at = observed_after(signal)
    snapshot = capture(
        instrument=EURUSD,
        schedule=MarketSchedule.FOREX_WEEKLY,
        observed_at=observed_at,
    )

    assert snapshot.market_session is forex_session_at(observed_at)
    assert isinstance(snapshot.market_session, MarketSession)
    assert snapshot.calendar_version is not None
    assert snapshot.market_open is True
    assert (snapshot.weekday_utc, snapshot.hour_utc) == (0, observed_at.hour)  # a Monday


# -- a snapshot is a record, not a calculation -----------------------------------------------


def test_it_is_written_and_read_back_exactly_as_it_was() -> None:
    for snapshot in (
        capture(),
        capture(UP_EXTREMES, DOWN_EXTREMES),
        capture(context_candles=[]),
        capture(trend_policy=None),
        capture(instrument=EURUSD, schedule=MarketSchedule.FOREX_WEEKLY),
    ):
        as_json = json.loads(json.dumps(snapshot.document()))  # what a database or API keeps
        assert snapshot_from_document(as_json) == snapshot
        assert snapshot_from_document(snapshot.document()) == snapshot


def test_reading_a_snapshot_recomputes_nothing() -> None:
    """A stored document is read as it is. If the trend it says is not what its own swings
    would give, the document is still what was known then: nothing is re-derived."""
    document = capture().document()
    document["observed"]["context"]["trend"] = "RANGE"

    restored = snapshot_from_document(document)

    assert restored.context.trend is TrendState.RANGE
    assert restored.context.swings == capture().context.swings


def test_the_document_holds_no_float_and_prices_are_exact_text() -> None:
    document = capture().document()

    def walk(value: object) -> None:
        assert not isinstance(value, float | Decimal)
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    swing = document["observed"]["signal"]["swings"][0]
    assert isinstance(swing["price"], str)
    assert Decimal(swing["price"]) == capture().signal.swings[0].price


def test_the_document_is_a_copy_nothing_written_to_it_reaches_the_snapshot() -> None:
    snapshot = capture()
    before = snapshot.content_hash
    document = snapshot.document()
    document["judged"]["outcome"] = "INCOMPATIBLE"
    document["observed"]["signal"]["swings"].clear()

    assert snapshot.outcome is PolicyOutcome.COMPATIBLE and snapshot.signal.swings
    assert snapshot.content_hash == before


def test_a_snapshot_is_immutable() -> None:
    snapshot = capture()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.outcome = PolicyOutcome.INCOMPATIBLE  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.signal.trend = TrendState.RANGE  # type: ignore[misc]
    assert isinstance(snapshot.signal.swings, tuple) and isinstance(snapshot.reasons, tuple)


# -- identity and reproducibility --------------------------------------------------------------


def test_the_same_observation_is_the_same_snapshot() -> None:
    first, second = capture(), capture()

    assert first == second
    assert first.content_hash == second.content_hash
    assert first.snapshot_id == second.snapshot_id
    assert len(first.content_hash) == 64


def test_when_it_was_computed_is_not_part_of_what_it_says() -> None:
    now, later = (
        capture(computed_after=timedelta(seconds=1)),
        capture(computed_after=timedelta(days=3)),
    )

    assert now.computed_at != later.computed_at
    assert (now.content_hash, now.snapshot_id) == (later.content_hash, later.snapshot_id)
    assert now.document(include_computed_at=False) == later.document(include_computed_at=False)
    assert "computed_at" not in now.document(include_computed_at=False)
    assert "computed_at" in now.document()


@pytest.mark.parametrize(
    "change",
    [
        {"orientation": BEARISH},
        {"trend_policy": policy(version="strategy-x-trend-v2")},
        {"trend_policy": policy(relationship=TrendRelationship.COUNTER_TREND)},
        {"trend_policy": None},
        {"instrument_id": "instrument-2"},
        {"data_source": "SOMEONE_ELSE", "authorized_sources": frozenset({"SOMEONE_ELSE"})},
        {"params": TrendParams(window_swings=4, significance=Decimal("0.25"))},
        {"context_extremes": DOWN_EXTREMES},
        {"signal_extremes": DOWN_EXTREMES},
        {"min_history": 90, "trend_policy": policy(minimum_history=90)},
    ],
    ids=lambda change: next(iter(change)),
)
def test_anything_that_changes_what_was_observed_or_judged_changes_the_snapshot(
    change: dict[str, Any],
) -> None:
    baseline = capture()
    changed = capture(**change)

    assert changed.content_hash != baseline.content_hash
    assert changed.snapshot_id != baseline.snapshot_id


def test_a_reclassification_makes_a_new_snapshot_and_leaves_the_old_one_alone() -> None:
    original = capture()
    original_document = original.document()

    reclassified = capture(params=TrendParams(window_swings=4, significance=Decimal("0.40")))

    assert reclassified.snapshot_id != original.snapshot_id
    assert original.document() == original_document
    assert original.signal.significance == Decimal("0.15")


def test_the_future_can_not_reach_the_snapshot() -> None:
    """Candles that close after the observed instant, and the one still open at it, are
    ignored: appending a wild stretch of future series cannot change what was known then."""
    signal = zigzag(UP_EXTREMES)
    context = hourly(UP_EXTREMES, ending_with=signal)
    observed_at = observed_after(signal)
    baseline = capture(observed_at=observed_at)

    future_signal = zigzag([50, 300], tail=0, start=signal[-1].close_time)
    future_context = zigzag([50, 300], tail=0, timeframe=Timeframe.H1, start=context[-1].close_time)
    assert future_signal[0].close_time > observed_at
    assert future_context[0].close_time > observed_at
    with_future = capture(
        observed_at=observed_at,
        signal_candles=[*signal, *future_signal],
        context_candles=[*context, *future_context],
    )

    assert with_future == baseline
    assert with_future.content_hash == baseline.content_hash


def test_snapshot_ids_are_stable_across_processes_by_construction() -> None:
    """The id is a name-based UUID of the content hash: no clock, no randomness."""
    snapshot = capture()
    assert snapshot.snapshot_id.version == 5
    assert snapshot.snapshot_id == capture().snapshot_id


# -- what a snapshot must never hold ------------------------------------------------------------

_FORBIDDEN = {
    "side",
    "action",
    "position",
    "entry",
    "order",
    "short",
    "long",
    "direction",
    "signal_action",
    "confidence",
    "score",
    "probability",
    "recommendation",
    "stop_loss",
    "take_profit",
}


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys |= _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _all_keys(item)
    return keys


def test_a_snapshot_holds_no_decision_no_execution_and_no_confidence() -> None:
    snapshot = capture()
    fields = {f.name for f in dataclasses.fields(ContextSnapshot)}
    fields |= {f.name for f in dataclasses.fields(type(snapshot.signal))}

    assert fields.isdisjoint(_FORBIDDEN)
    assert _all_keys(snapshot.document()).isdisjoint(_FORBIDDEN)


def test_observed_and_judged_are_kept_apart() -> None:
    document = capture().document()

    assert {"observed", "judged"} <= document.keys()
    assert "outcome" not in document["observed"] and "trend" not in document["judged"]
    assert not any(key.endswith("_trend") for key in document["judged"])


def test_the_module_only_depends_on_the_domain_layer() -> None:
    tree = ast.parse(Path(context_snapshot.__file__).read_text(encoding="utf-8"))
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
    stdlib = {"hashlib", "json", "uuid", "collections.abc", "dataclasses", "datetime", "decimal"}
    stdlib |= {"typing"}
    foreign = {
        m for m in imported if m not in stdlib and not m.startswith("freyja_backend.domain.")
    }
    assert foreign == set()


# -- a snapshot that contradicts itself can not exist -----------------------------------------


def _valid_fields() -> dict[str, Any]:
    snapshot = capture()
    return {f.name: getattr(snapshot, f.name) for f in dataclasses.fields(ContextSnapshot)}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"observed_at": datetime(2026, 1, 5, 12, 0)}, "observed_at"),
        ({"computed_at": datetime(2026, 1, 5, 14, 0)}, "computed_at"),
        (
            {"computed_at": datetime(2026, 1, 5, 14, 0, tzinfo=timezone(timedelta(hours=2)))},
            "computed_at",
        ),
        ({"explanation": "  "}, "explanation"),
        ({"reasons": (PolicyReason.POLICY_MISSING,)}, "reasons must be empty"),
        ({"outcome": PolicyOutcome.INCOMPATIBLE}, "reasons must be empty"),
        ({"policy_version": None}, "come together"),
        ({"required_relationship": None}, "come together"),
    ],
)
def test_an_incoherent_snapshot_is_refused(change: dict[str, Any], message: str) -> None:
    with pytest.raises(InvalidContextSnapshotError, match=message):
        ContextSnapshot(**{**_valid_fields(), **change})


def test_it_cannot_be_computed_before_the_instant_it_observes() -> None:
    fields = _valid_fields()
    fields["computed_at"] = fields["observed_at"] - timedelta(seconds=1)
    with pytest.raises(InvalidContextSnapshotError, match="before the instant"):
        ContextSnapshot(**fields)


def test_the_context_can_not_be_finer_than_the_signal() -> None:
    with pytest.raises(InvalidContextSnapshotError, match="finer"):
        ContextSnapshot(
            **{**_valid_fields(), "signal": capture().context, "context": capture().signal}
        )


@pytest.mark.parametrize("field", ["observed_at", "computed_at"])
def test_capturing_needs_utc_instants(field: str) -> None:
    signal = zigzag(UP_EXTREMES)
    with pytest.raises((InvalidContextSnapshotError, InvalidMarketDataError)):
        capture(**{field: observed_after(signal).replace(tzinfo=None)})  # type: ignore[arg-type]


def test_a_provisional_swing_is_never_recorded_as_evidence() -> None:
    """The classifier only hands over confirmed swings; the record refuses anything else even
    if a caller were to build one by hand: a swing that may still move proves nothing."""
    provisional = Pivot(
        kind=PivotKind.HIGH,
        status=PivotStatus.PROVISIONAL,
        open_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        price=Decimal("110.5"),
        confirmed_at=None,
    )
    with pytest.raises(InvalidContextSnapshotError, match="provisional"):
        context_snapshot._swing(provisional)


# -- reading a document that is not a snapshot -------------------------------------------------


def _corrupt(mutate: Any) -> dict[str, Any]:
    document = capture().document()
    mutate(document)
    return document


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("observed"),
        lambda d: d.pop("computed_at"),
        lambda d: d["judged"].pop("outcome"),
        lambda d: d["observed"]["signal"].pop("swings"),
        lambda d: d["judged"].update(outcome="MAYBE"),
        lambda d: d["observed"]["context"].update(trend="SIDEWAYS"),
        lambda d: d["observed"]["signal"]["swings"][0].update(price="not a price"),
        lambda d: d.update(observed_at="2026-01-05T10:00:00"),  # naive
        lambda d: d.update(observed_at="2026-01-05T10:00:00+02:00"),  # not UTC
        lambda d: d.update(computed_at="yesterday"),
        lambda d: d["judged"].update(reasons=["MADE_UP_REASON"]),
    ],
    ids=[
        "no-observed",
        "no-computed-at",
        "no-outcome",
        "no-swings",
        "unknown-outcome",
        "unknown-trend",
        "bad-price",
        "naive-instant",
        "offset-instant",
        "bad-instant",
        "unknown-reason",
    ],
)
def test_a_document_that_is_not_a_snapshot_is_refused_never_repaired(mutate: Any) -> None:
    with pytest.raises(InvalidContextSnapshotError):
        snapshot_from_document(_corrupt(mutate))


def test_a_document_that_contradicts_itself_is_refused() -> None:
    document = capture().document()
    document["judged"]["reasons"] = ["POLICY_MISSING"]  # COMPATIBLE with a reason
    with pytest.raises(InvalidContextSnapshotError):
        snapshot_from_document(document)
