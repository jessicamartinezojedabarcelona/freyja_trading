"""POINT4-MODEL-001: the candle pattern instance model.

The catalogue is checked against the contract document (`patrones-de-vela.md`), which is parsed
here and never derived from the code under test. Lifecycle transitions are checked against a table
written out on its own.
"""

import dataclasses
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import candlestick_pattern
from freyja_backend.domain.candlestick_pattern import (
    CANDLE_PATTERN_CATALOGUE,
    CANDLE_PATTERN_MODEL_VERSION,
    CandleAnchor,
    CandleBias,
    CandlePatternEvaluation,
    CandlePatternInstance,
    CandlePatternState,
    CandlePatternType,
    InvalidationReason,
    InvalidCandlePatternError,
    candle_pattern_instance_from_document,
    derive_candle_pattern_instance_id,
    start_candle_pattern_instance,
)
from freyja_backend.domain.chart_pattern import evidence
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle, Timeframe

REPO = Path(__file__).resolve().parents[3]
STEP = timedelta(minutes=1)
TF = Timeframe.M1
T0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
S = CandlePatternState


# -- builders -------------------------------------------------------------------------------


def candle_anchor(
    index: int, open_: str, high: str, low: str, close: str, label: str
) -> CandleAnchor:
    opened = T0 + STEP * index
    return CandleAnchor(
        opened, opened + STEP, Decimal(open_), Decimal(high), Decimal(low), Decimal(close), label
    )


def morning_star_anchors(count: int = 3) -> tuple[CandleAnchor, ...]:
    """A textbook morning star: bearish, small indecisive body, bullish closing into candle 1."""
    return (
        candle_anchor(0, "110", "111", "95", "96", "FIRST"),
        candle_anchor(1, "94", "95", "90", "94.5", "SECOND"),
        candle_anchor(2, "96", "109", "95", "108", "THIRD"),
    )[:count]


def context_evidence() -> Any:
    return evidence("CONTEXT", "tendencia previa bajista", prior_trend="DOWN")


def evaluation_in(
    state: CandlePatternState,
    step: int = 0,
    anchors: tuple[CandleAnchor, ...] | None = None,
    **overrides: Any,
) -> CandlePatternEvaluation:
    """A coherent evaluation in `state`, `step` evaluations after the anchors were known."""
    anchors = anchors if anchors is not None else morning_star_anchors()
    timing = anchors or morning_star_anchors()
    evaluated_at = timing[-1].close_time + STEP * step
    values: dict[str, Any] = {
        "evaluated_at": evaluated_at,
        "as_of": evaluated_at,
        "state": state,
        "anchors": anchors,
    }
    if state in (
        S.CONTEXT_VALID,
        S.PENDING_CONFIRMATION,
        S.CONFIRMED,
        S.FAILED,
    ):
        values["evidence"] = (context_evidence(),)
    if state is S.INVALIDATED:
        values["invalidation_reasons"] = (InvalidationReason.GEOMETRY_BROKEN,)
    if state is S.INSUFFICIENT_DATA:
        values["insufficient_data_reasons"] = (MissingDataReason.NO_DATA,)
    values.update(overrides)
    return CandlePatternEvaluation(**values)


def instance_from(*states: CandlePatternState, **overrides: Any) -> CandlePatternInstance:
    """A pattern that went through `states`, one evaluation each."""
    pattern_type = overrides.pop("pattern_type", CandlePatternType.MORNING_STAR)
    anchors = overrides.pop("anchors", None)
    first_evaluation = overrides.pop("first_evaluation", None)
    if first_evaluation is None:
        first_evaluation = evaluation_in(states[0], anchors=anchors)
    built = start_candle_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=overrides.pop("instrument_id", "instrument-1"),
        data_source=overrides.pop("data_source", "BINANCE"),
        timeframe=overrides.pop("timeframe", TF),
        detector_version=overrides.pop("detector_version", "morning-star-detector-v1"),
        parameter_version=overrides.pop("parameter_version", "params-v1"),
        first_evaluation=first_evaluation,
    )
    for step, state in enumerate(states[1:], start=1):
        built = built.advance(evaluation_in(state, step, anchors=first_evaluation.anchors))
    return built


# -- the catalogue against the contract document ---------------------------------------------

_DOC = REPO / "docs" / "domain" / "patrones-de-vela.md"
_SECTION_COUNTS = {"### 5.1": 1, "### 5.2": 2, "### 5.3": 3}


def parse_contract() -> dict[str, tuple[int, str, bool]]:
    """identifier -> (candle_count, bias, requires_confirmation), read from the contract tables."""
    parsed: dict[str, tuple[int, str, bool]] = {}
    count: int | None = None
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        for heading, value in _SECTION_COUNTS.items():
            if line.startswith(heading):
                count = value
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if count is None or len(cells) != 6 or not re.fullmatch(r"`[A-Z_]+`", cells[0]):
            continue
        bias = re.findall(r"`([A-Z_]+)`", cells[3])[0]
        confirms = cells[5].startswith("Sí")
        parsed[cells[0].strip("`")] = (count, bias, confirms)
    return parsed


def test_the_document_lists_the_twenty_three_approved_patterns() -> None:
    assert len(parse_contract()) == 23


def test_the_catalogue_is_exactly_what_the_contract_says() -> None:
    contract = parse_contract()
    assert (
        set(contract)
        == {t.value for t in CandlePatternType}
        == {t.value for t in CANDLE_PATTERN_CATALOGUE}
    )
    for pattern_type, definition in CANDLE_PATTERN_CATALOGUE.items():
        count, bias, confirms = contract[pattern_type.value]
        assert definition.pattern_type is pattern_type
        assert definition.candle_count == count, pattern_type
        assert definition.traditional_bias.value == bias, pattern_type
        assert definition.requires_confirmation == confirms, pattern_type


def test_nine_eight_and_six_by_candle_count() -> None:
    counts = {1: 0, 2: 0, 3: 0}
    for definition in CANDLE_PATTERN_CATALOGUE.values():
        counts[definition.candle_count] += 1
    assert counts == {1: 9, 2: 8, 3: 6}


def test_only_three_candle_patterns_require_confirmation() -> None:
    for definition in CANDLE_PATTERN_CATALOGUE.values():
        assert definition.requires_confirmation == (definition.candle_count == 3)


def test_a_definition_is_immutable_and_the_catalogue_read_only() -> None:
    definition = CANDLE_PATTERN_CATALOGUE[CandlePatternType.HAMMER]
    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.candle_count = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        CANDLE_PATTERN_CATALOGUE[CandlePatternType.HAMMER] = definition  # type: ignore[index]


# -- CandleAnchor -----------------------------------------------------------------------------


def test_an_anchor_is_a_closed_candle_at_exact_prices() -> None:
    good = candle_anchor(0, "10", "12", "9", "11", "FIRST")
    assert good.body == Decimal("1") and good.range == Decimal("3")
    assert good.upper_wick == Decimal("1") and good.lower_wick == Decimal("1")
    assert good.is_bullish and not good.is_bearish
    with pytest.raises(InvalidCandlePatternError, match="exact Decimal"):
        CandleAnchor(T0, T0 + STEP, 10.0, Decimal(12), Decimal(9), Decimal(11), "FIRST")  # type: ignore[arg-type]
    with pytest.raises(InvalidCandlePatternError, match="UTC"):
        CandleAnchor(
            datetime(2026, 1, 5),
            T0 + STEP,
            Decimal(10),
            Decimal(12),
            Decimal(9),
            Decimal(11),
            "FIRST",
        )
    with pytest.raises(InvalidCandlePatternError, match="closes after it opens"):
        CandleAnchor(T0, T0, Decimal(10), Decimal(12), Decimal(9), Decimal(11), "FIRST")
    with pytest.raises(InvalidCandlePatternError, match="do not bound"):
        CandleAnchor(T0, T0 + STEP, Decimal(10), Decimal(9), Decimal(9), Decimal(11), "FIRST")
    with pytest.raises(InvalidCandlePatternError, match="UPPER_SNAKE_CASE"):
        candle_anchor(0, "10", "12", "9", "11", "first")


def test_from_candle_carries_the_ohlc_across() -> None:
    raw = Candle(T0, T0 + STEP, Decimal(10), Decimal(12), Decimal(9), Decimal(11), Decimal(100))
    built = CandleAnchor.from_candle(raw, "FIRST")
    assert (built.open, built.high, built.low, built.close) == (
        Decimal(10),
        Decimal(12),
        Decimal(9),
        Decimal(11),
    )


# -- CandlePatternEvaluation: content and no look-ahead ----------------------------------------


def test_an_evaluation_needs_at_least_one_anchor() -> None:
    with pytest.raises(InvalidCandlePatternError, match="at least one anchor"):
        CandlePatternEvaluation(T0, T0, S.FORMING, ())


def test_anchors_must_be_in_strict_chronological_order() -> None:
    a, b = morning_star_anchors(2)
    with pytest.raises(InvalidCandlePatternError, match="chronological"):
        CandlePatternEvaluation(T0 + STEP * 10, T0 + STEP * 10, S.FORMING, (b, a))


def test_an_anchor_that_has_not_closed_cannot_be_used() -> None:
    anchors = morning_star_anchors()
    with pytest.raises(InvalidCandlePatternError, match="had not closed"):
        CandlePatternEvaluation(anchors[-1].open_time, None, S.FORMING, anchors)


def test_as_of_cannot_be_after_the_evaluation() -> None:
    anchors = morning_star_anchors(1)
    with pytest.raises(InvalidCandlePatternError, match="closes after the evaluation"):
        CandlePatternEvaluation(T0 + STEP, T0 + STEP * 5, S.FORMING, anchors)


def test_invalidation_reasons_exist_exactly_when_invalidated() -> None:
    anchors = morning_star_anchors()
    with pytest.raises(InvalidCandlePatternError, match="exactly when INVALIDATED"):
        evaluation_in(S.INVALIDATED, anchors=anchors, invalidation_reasons=())
    with pytest.raises(InvalidCandlePatternError, match="exactly when INVALIDATED"):
        evaluation_in(
            S.FORMING,
            anchors=anchors[:1],
            invalidation_reasons=(InvalidationReason.GEOMETRY_BROKEN,),
        )


def test_insufficient_data_reasons_exist_exactly_when_that_state() -> None:
    anchors = morning_star_anchors()
    with pytest.raises(InvalidCandlePatternError, match="exactly when it is"):
        evaluation_in(S.INSUFFICIENT_DATA, anchors=anchors, insufficient_data_reasons=())


@pytest.mark.parametrize("state", [S.CONTEXT_VALID, S.PENDING_CONFIRMATION, S.CONFIRMED, S.FAILED])
def test_context_evidence_is_mandatory_from_context_valid_onward(state: CandlePatternState) -> None:
    with pytest.raises(InvalidCandlePatternError, match="CONTEXT evidence"):
        evaluation_in(state, evidence=())


@pytest.mark.parametrize("state", [S.FORMING, S.MORPHOLOGICALLY_VALID, S.INSUFFICIENT_DATA])
def test_context_evidence_is_not_required_before_context_valid(state: CandlePatternState) -> None:
    evaluation_in(
        state, anchors=morning_star_anchors(1) if state is S.FORMING else None, evidence=()
    )


# -- lifecycle --------------------------------------------------------------------------------

_TRANSITIONS: dict[CandlePatternState, frozenset[CandlePatternState]] = {
    S.FORMING: frozenset(
        {
            S.MORPHOLOGICALLY_VALID,
            S.CONTEXT_VALID,
            S.PENDING_CONFIRMATION,
            S.CONFIRMED,
            S.FAILED,
            S.INVALIDATED,
        }
    ),
    S.MORPHOLOGICALLY_VALID: frozenset(
        {S.CONTEXT_VALID, S.PENDING_CONFIRMATION, S.CONFIRMED, S.FAILED, S.INVALIDATED}
    ),
    S.CONTEXT_VALID: frozenset({S.PENDING_CONFIRMATION, S.CONFIRMED, S.FAILED, S.INVALIDATED}),
    S.PENDING_CONFIRMATION: frozenset({S.CONFIRMED, S.FAILED, S.INVALIDATED}),
    S.CONFIRMED: frozenset({S.INVALIDATED}),
    S.FAILED: frozenset(),
    S.INVALIDATED: frozenset(),
}


@pytest.mark.parametrize(
    ("start", "target"),
    [(s, t) for s in _TRANSITIONS for t in _TRANSITIONS[s]],
)
def test_every_allowed_transition_is_accepted(
    start: CandlePatternState, target: CandlePatternState
) -> None:
    instance_from(start, target)


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (s, t)
        for s, t in product(_TRANSITIONS, _TRANSITIONS)
        if t not in _TRANSITIONS[s] and t is not s
    ],
)
def test_every_forbidden_transition_is_refused(
    start: CandlePatternState, target: CandlePatternState
) -> None:
    with pytest.raises(InvalidCandlePatternError):
        instance_from(start, target)


def test_a_terminal_state_accepts_nothing_afterwards() -> None:
    for terminal in (S.FAILED, S.INVALIDATED):
        built = instance_from(terminal)
        with pytest.raises(InvalidCandlePatternError, match="final"):
            built.advance(evaluation_in(S.INVALIDATED, step=1))


def test_insufficient_data_is_a_pause_not_a_dead_end() -> None:
    built = instance_from(
        S.MORPHOLOGICALLY_VALID, S.INSUFFICIENT_DATA, S.CONTEXT_VALID, S.CONFIRMED
    )
    assert built.state is S.CONFIRMED


def test_three_candle_patterns_skip_pending_confirmation_straight_to_confirmed() -> None:
    """No pattern in the v1 catalogue needs a candle beyond its own definition to confirm."""
    built = instance_from(S.MORPHOLOGICALLY_VALID, S.CONTEXT_VALID, S.CONFIRMED)
    assert built.state is S.CONFIRMED


def test_evaluations_move_strictly_forward_in_time() -> None:
    built = instance_from(S.FORMING)
    with pytest.raises(InvalidCandlePatternError, match="strictly forward"):
        built.advance(evaluation_in(S.MORPHOLOGICALLY_VALID, step=0))


def test_anchors_may_only_be_added() -> None:
    built = instance_from(S.FORMING, anchors=morning_star_anchors(2))
    changed = evaluation_in(
        S.MORPHOLOGICALLY_VALID,
        step=1,
        anchors=(morning_star_anchors(2)[0], morning_star_anchors()[2]),
    )
    with pytest.raises(InvalidCandlePatternError, match="anchors may only be added"):
        built.advance(changed)


# -- exact candle count -------------------------------------------------------------------------


def test_morphologically_valid_needs_exactly_the_catalogues_candle_count() -> None:
    with pytest.raises(InvalidCandlePatternError, match="needs exactly 3 anchors"):
        instance_from(S.MORPHOLOGICALLY_VALID, anchors=morning_star_anchors(2))


def test_forming_may_have_fewer_anchors_than_the_catalogue() -> None:
    built = instance_from(S.FORMING, anchors=morning_star_anchors(1))
    assert len(built.latest.anchors) == 1


def test_a_pattern_cannot_have_more_anchors_than_its_catalogue_count() -> None:
    extra = (*morning_star_anchors(), candle_anchor(3, "108", "112", "107", "110", "FOURTH"))
    with pytest.raises(InvalidCandlePatternError, match="cannot have more"):
        instance_from(S.FORMING, anchors=extra)


def test_one_candle_patterns_need_exactly_one_anchor() -> None:
    hammer_anchor = (candle_anchor(0, "100", "101", "90", "100.5", "FIRST"),)
    built = instance_from(
        S.MORPHOLOGICALLY_VALID,
        S.CONTEXT_VALID,
        S.CONFIRMED,
        pattern_type=CandlePatternType.HAMMER,
        first_evaluation=evaluation_in(S.MORPHOLOGICALLY_VALID, anchors=hammer_anchor),
    )
    assert built.state is S.CONFIRMED
    assert len(built.latest.anchors) == 1


# -- identity -----------------------------------------------------------------------------------


def test_the_same_pattern_found_again_is_the_same_instance() -> None:
    first = instance_from(S.MORPHOLOGICALLY_VALID)
    second = instance_from(S.MORPHOLOGICALLY_VALID, S.CONTEXT_VALID)
    assert first.candle_pattern_instance_id == second.candle_pattern_instance_id


def test_a_different_start_detector_or_parameters_is_another_instance() -> None:
    base = instance_from(S.MORPHOLOGICALLY_VALID)
    other_detector = instance_from(S.MORPHOLOGICALLY_VALID, detector_version="v2")
    other_params = instance_from(S.MORPHOLOGICALLY_VALID, parameter_version="v2")
    other_type = instance_from(
        S.MORPHOLOGICALLY_VALID,
        pattern_type=CandlePatternType.EVENING_STAR,
        first_evaluation=evaluation_in(S.MORPHOLOGICALLY_VALID),
    )
    ids = {
        base.candle_pattern_instance_id,
        other_detector.candle_pattern_instance_id,
        other_params.candle_pattern_instance_id,
        other_type.candle_pattern_instance_id,
    }
    assert len(ids) == 4


def test_derive_candle_pattern_instance_id_is_deterministic() -> None:
    kwargs = {
        "pattern_type": CandlePatternType.HAMMER,
        "instrument_id": "instrument-1",
        "data_source": "BINANCE",
        "timeframe": TF,
        "started_at": T0,
        "detector_version": "v1",
        "parameter_version": "p1",
    }
    assert derive_candle_pattern_instance_id(**kwargs) == derive_candle_pattern_instance_id(
        **kwargs
    )


# -- no signal, no probability ------------------------------------------------------------------


def test_no_field_carries_a_side_target_confidence_or_probability() -> None:
    forbidden = {"side", "entry", "target", "confidence", "probability", "signal"}
    instance_fields = {f.name for f in dataclasses.fields(CandlePatternInstance)}
    evaluation_fields = {f.name for f in dataclasses.fields(CandlePatternEvaluation)}
    assert forbidden.isdisjoint(instance_fields)
    assert forbidden.isdisjoint(evaluation_fields)


def test_the_catalogue_carries_no_probability_either() -> None:
    definition_fields = {
        f.name for f in dataclasses.fields(next(iter(CANDLE_PATTERN_CATALOGUE.values())))
    }
    assert {"probability", "confidence", "win_rate"}.isdisjoint(definition_fields)


# -- serialization --------------------------------------------------------------------------------


def test_document_round_trips_through_from_document() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID, S.CONTEXT_VALID, S.CONFIRMED)
    document = built.document()
    restored = candle_pattern_instance_from_document(document)
    assert restored == built
    assert document["model_version"] == CANDLE_PATTERN_MODEL_VERSION
    assert document["candle_pattern_instance_id"] == str(built.candle_pattern_instance_id)


def test_document_has_no_floats_anywhere() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID, S.CONTEXT_VALID, S.CONFIRMED)

    def walk(value: Any) -> None:
        assert not isinstance(value, float)
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(built.document())


def test_from_document_rejects_a_tampered_identity() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID)
    document = dict(built.document())
    document["candle_pattern_instance_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(InvalidCandlePatternError, match="identity"):
        candle_pattern_instance_from_document(document)


def test_from_document_rejects_an_unknown_model_version() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID)
    document = dict(built.document())
    document["model_version"] = "some-other-version"
    with pytest.raises(InvalidCandlePatternError, match="unsupported model version"):
        candle_pattern_instance_from_document(document)


def test_from_document_rejects_a_missing_field() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID)
    document = dict(built.document())
    del document["instrument_id"]
    with pytest.raises(InvalidCandlePatternError, match="not a candle pattern instance document"):
        candle_pattern_instance_from_document(document)


# -- traditional bias comes from the catalogue, never the detector ------------------------------


def test_traditional_bias_and_requires_confirmation_come_from_the_catalogue() -> None:
    built = instance_from(S.MORPHOLOGICALLY_VALID)
    assert built.traditional_bias is CandleBias.BULLISH
    assert built.requires_confirmation is True
    hammer = instance_from(
        S.MORPHOLOGICALLY_VALID,
        pattern_type=CandlePatternType.HAMMER,
        first_evaluation=evaluation_in(S.MORPHOLOGICALLY_VALID, anchors=morning_star_anchors(1)),
    )
    assert hammer.traditional_bias is CandleBias.CONTEXT_DEPENDENT
    assert hammer.requires_confirmation is False


def test_a_pattern_type_outside_the_catalogue_is_refused() -> None:
    with pytest.raises(InvalidCandlePatternError, match="catalogue"):
        CandlePatternInstance(
            "NOT_A_TYPE",  # type: ignore[arg-type]
            "instrument-1",
            "BINANCE",
            TF,
            "v1",
            "p1",
            (evaluation_in(S.FORMING),),
        )


def test_module_constants_are_exposed() -> None:
    assert candlestick_pattern.CANDLE_PATTERN_MODEL_VERSION == "candle-pattern-instance-v1"
    assert candlestick_pattern.CANDLE_PATTERN_CATALOGUE_VERSION == "candle-patterns-v1"
