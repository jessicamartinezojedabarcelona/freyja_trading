"""POINT3-MODEL-001: the chart pattern instance model.

The catalogue is checked against the contract document, which is parsed here and never
derived from the code under test. Lifecycle transitions are checked against a table written
out on its own. Real pivots from the structure module anchor one of the figures.
"""

import ast
import dataclasses
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import chart_pattern
from freyja_backend.domain.chart_pattern import (
    PATTERN_CATALOGUE,
    PATTERN_MODEL_VERSION,
    AnchorPivot,
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    Breakout,
    BreakoutDirection,
    InvalidationReason,
    InvalidPatternError,
    PatternBias,
    PatternEvaluation,
    PatternGroup,
    PatternInstance,
    PatternRole,
    PatternState,
    PatternType,
    derive_pattern_instance_id,
    evidence,
    pattern_instance_from_document,
    start_pattern_instance,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_structure import (
    Pivot,
    PivotKind,
    PivotStatus,
    detect_pivots,
    swing_points,
)
from tests.unit.test_market_trend import T0, observed_after, zigzag

REPO = Path(__file__).resolve().parents[3]
STEP = timedelta(minutes=5)
TF = Timeframe.M5
S = PatternState
HIGH, LOW = PivotKind.HIGH, PivotKind.LOW


# -- builders -----------------------------------------------------------------------------------


def anchor(index: int, kind: PivotKind, price: str, label: str = "POINT") -> AnchorPivot:
    opened = T0 + STEP * 10 * index
    return AnchorPivot(kind, opened, Decimal(price), opened + STEP * 4, label)


def double_top_anchors(count: int = 3) -> tuple[AnchorPivot, ...]:
    return (
        anchor(0, HIGH, "110.0", "FIRST_PEAK"),
        anchor(1, LOW, "100.0", "TROUGH"),
        anchor(2, HIGH, "110.2", "SECOND_PEAK"),
    )[:count]


def neckline(anchors: tuple[AnchorPivot, ...]) -> Boundary:
    trough = anchors[1]
    return Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(trough.open_time, trough.price),
            BoundaryPoint(anchors[-1].open_time, trough.price),
        ),
        (trough.open_time,),
    )


def evaluation_in(
    state: PatternState,
    step: int = 0,
    anchors: tuple[AnchorPivot, ...] | None = None,
    **overrides: Any,
) -> PatternEvaluation:
    """A coherent evaluation in `state`, `step` evaluations after the anchors were known."""
    anchors = anchors if anchors is not None else double_top_anchors()
    timing = anchors or double_top_anchors()  # an empty tuple is a case under test
    evaluated_at = timing[-1].confirmed_at + STEP * (step + 1)
    values: dict[str, Any] = {
        "evaluated_at": evaluated_at,
        "as_of": evaluated_at,
        "candle_count": 20 + step,
        "state": state,
        "anchors": anchors,
    }
    if state not in (S.FORMING, S.INVALIDATED, S.INSUFFICIENT_DATA):
        values["boundaries"] = (neckline(timing),)
    breakout_directions = {
        S.BREAKOUT_PENDING_CONFIRMATION: (BreakoutDirection.DOWN, False),
        S.CONFIRMED_UP: (BreakoutDirection.UP, True),
        S.CONFIRMED_DOWN: (BreakoutDirection.DOWN, True),
        S.FAILED_BREAKOUT: (BreakoutDirection.DOWN, False),
    }
    if state in breakout_directions:
        direction, confirmed = breakout_directions[state]
        values["breakout"] = Breakout(
            direction,
            BoundaryRole.NECKLINE,
            evaluated_at - STEP,
            evaluated_at,
            Decimal("99.5"),
            confirmed,
        )
    if state is S.INVALIDATED:
        values["invalidation_reasons"] = (InvalidationReason.GEOMETRY_BROKEN,)
    if state is S.INSUFFICIENT_DATA:
        values["insufficient_data_reasons"] = (MissingDataReason.NO_DATA,)
    values.update(overrides)
    return PatternEvaluation(**values)


def instance_from(*states: PatternState, **overrides: Any) -> PatternInstance:
    """A figure that went through `states`, one evaluation each."""
    built = start_pattern_instance(
        pattern_type=overrides.pop("pattern_type", PatternType.DOUBLE_TOP),
        instrument_id="instrument-1",
        data_source="BINANCE",
        timeframe=TF,
        detector_version="double-top-detector-v1",
        parameter_version="params-v1",
        first_evaluation=evaluation_in(states[0]),
    )
    for step, state in enumerate(states[1:], start=1):
        built = built.advance(evaluation_in(state, step))
    return built


# -- the catalogue against the contract document ------------------------------------------------

_DOC = REPO / "docs" / "domain" / "figuras-chartistas.md"
_SECTION_GROUPS = {
    "### 4.1": PatternGroup.REVERSAL,
    "### 4.2": PatternGroup.CONTINUATION_CONSOLIDATION,
    "### 4.3": PatternGroup.COMPRESSION_EXPANSION_CONTEXTUAL,
}


def parse_contract() -> dict[str, tuple[PatternGroup, frozenset[str], str, int]]:
    """identifier -> (group, roles, bias, minimum anchors), read from the contract tables."""
    parsed: dict[str, tuple[PatternGroup, frozenset[str], str, int]] = {}
    group: PatternGroup | None = None
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        for heading, value in _SECTION_GROUPS.items():
            if line.startswith(heading):
                group = value
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if group is None or len(cells) != 6 or not re.fullmatch(r"`[A-Z_]+`", cells[0]):
            continue
        roles = frozenset(re.findall(r"`([A-Z_]+)`", cells[2]))
        bias = re.findall(r"`([A-Z_]+)`", cells[3])[0]
        anchors = int(re.match(r"(\d+)", cells[5]).group(1))  # type: ignore[union-attr]
        parsed[cells[0].strip("`")] = (group, roles, bias, anchors)
    return parsed


def test_the_document_lists_the_twenty_approved_patterns() -> None:
    assert len(parse_contract()) == 20


def test_the_catalogue_is_exactly_what_the_contract_says() -> None:
    contract = parse_contract()
    assert set(contract) == {t.value for t in PatternType} == {t.value for t in PATTERN_CATALOGUE}
    for pattern_type, definition in PATTERN_CATALOGUE.items():
        group, roles, bias, anchors = contract[pattern_type.value]
        assert definition.pattern_type is pattern_type
        assert definition.group is group, pattern_type
        assert {role.value for role in definition.traditional_roles} == roles, pattern_type
        assert definition.traditional_bias.value == bias, pattern_type
        assert definition.min_anchor_pivots == anchors, pattern_type


def test_eight_eight_and_four_by_group() -> None:
    counts = dict.fromkeys(PatternGroup, 0)
    for definition in PATTERN_CATALOGUE.values():
        counts[definition.group] += 1
    assert counts == {
        PatternGroup.REVERSAL: 8,
        PatternGroup.CONTINUATION_CONSOLIDATION: 8,
        PatternGroup.COMPRESSION_EXPANSION_CONTEXTUAL: 4,
    }


def test_triangles_wedges_and_rectangles_are_not_forced_into_one_family() -> None:
    for name in ("ASCENDING_TRIANGLE", "DESCENDING_TRIANGLE", "SYMMETRICAL_TRIANGLE"):
        assert {PatternRole.CONTINUATION, PatternRole.REVERSAL} <= (
            PATTERN_CATALOGUE[PatternType(name)].traditional_roles
        )
    assert len(PATTERN_CATALOGUE[PatternType.RECTANGLE].traditional_roles) == 3
    for name in ("RISING_WEDGE", "FALLING_WEDGE"):
        assert {PatternRole.REVERSAL, PatternRole.CONTINUATION} <= (
            PATTERN_CATALOGUE[PatternType(name)].traditional_roles
        )
    for name in ("SYMMETRICAL_TRIANGLE", "RECTANGLE"):
        bias = PATTERN_CATALOGUE[PatternType(name)].traditional_bias
        assert bias is PatternBias.BREAKOUT_DEPENDENT


def test_a_definition_is_immutable_and_the_catalogue_read_only() -> None:
    definition = PATTERN_CATALOGUE[PatternType.DOUBLE_TOP]
    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.min_anchor_pivots = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        PATTERN_CATALOGUE[PatternType.DOUBLE_TOP] = definition  # type: ignore[index]
    assert isinstance(definition.traditional_roles, frozenset)


# -- the parts ----------------------------------------------------------------------------------


def test_an_anchor_is_a_confirmed_pivot_at_an_exact_price() -> None:
    good = anchor(0, HIGH, "110.25")
    assert good.price == Decimal("110.25")
    with pytest.raises(InvalidPatternError, match="exact Decimal"):
        AnchorPivot(HIGH, T0, 110.25, T0 + STEP, "POINT")  # type: ignore[arg-type]
    with pytest.raises(InvalidPatternError, match="exact Decimal"):
        anchor(0, HIGH, "0")
    with pytest.raises(InvalidPatternError, match="UTC"):
        AnchorPivot(HIGH, datetime(2026, 1, 5), Decimal(1), T0 + STEP, "POINT")
    with pytest.raises(InvalidPatternError, match="before its candle has closed"):
        AnchorPivot(HIGH, T0, Decimal(1), T0, "POINT")
    with pytest.raises(InvalidPatternError, match="UPPER_SNAKE_CASE"):
        anchor(0, HIGH, "1", "head")


def test_only_a_confirmed_pivot_can_anchor_a_figure() -> None:
    provisional = Pivot(HIGH, PivotStatus.PROVISIONAL, T0, Decimal("110"), None)
    with pytest.raises(InvalidPatternError, match="provisional"):
        AnchorPivot.from_pivot(provisional, "HEAD")
    confirmed = Pivot(HIGH, PivotStatus.CONFIRMED, T0, Decimal("110"), T0 + STEP * 3)
    built = AnchorPivot.from_pivot(confirmed, "HEAD")
    assert (built.kind, built.price, built.confirmed_at) == (HIGH, Decimal("110"), T0 + STEP * 3)


def test_a_pivot_that_says_provisional_is_never_an_anchor_whatever_else_it_says() -> None:
    """Provisional but carrying a confirmation time: inconsistent, and still refused."""
    odd = Pivot(HIGH, PivotStatus.PROVISIONAL, T0, Decimal("110"), T0 + STEP * 3)
    with pytest.raises(InvalidPatternError, match="provisional"):
        AnchorPivot.from_pivot(odd, "HEAD")


def test_a_boundary_needs_its_points_in_order_and_its_contacts_once() -> None:
    point = BoundaryPoint(T0, Decimal("100"))
    later = BoundaryPoint(T0 + STEP, Decimal("101"))
    Boundary(BoundaryRole.UPPER, (point, later), (T0,))
    with pytest.raises(InvalidPatternError, match="needs 2 points"):
        Boundary(BoundaryRole.UPPER, (point,), ())
    with pytest.raises(InvalidPatternError, match="needs 3 points"):
        Boundary(BoundaryRole.ARC, (point, later), ())
    Boundary(BoundaryRole.ARC, (point, later, BoundaryPoint(T0 + STEP * 2, Decimal("99"))), ())
    with pytest.raises(InvalidPatternError, match="chronological"):
        Boundary(BoundaryRole.LOWER, (later, point), ())
    with pytest.raises(InvalidPatternError, match="once"):
        Boundary(BoundaryRole.LOWER, (point, later), (T0, T0))
    with pytest.raises(InvalidPatternError, match="exact Decimal"):
        BoundaryPoint(T0, 100.0)  # type: ignore[arg-type]


def test_a_breakout_is_a_closed_candle_at_an_exact_price() -> None:
    Breakout(BreakoutDirection.UP, BoundaryRole.UPPER, T0, T0 + STEP, Decimal("1"), True)
    with pytest.raises(InvalidPatternError, match="closes after it opens"):
        Breakout(BreakoutDirection.UP, BoundaryRole.UPPER, T0, T0, Decimal("1"), True)
    with pytest.raises(InvalidPatternError, match="exact Decimal"):
        Breakout(BreakoutDirection.UP, BoundaryRole.UPPER, T0, T0 + STEP, 1.5, True)  # type: ignore[arg-type]


def test_evidence_is_extensible_without_new_fields() -> None:
    # Known kinds of the contract, and one no code has ever heard of: same shape, no new field.
    for code in (
        "FLAGPOLE",
        "HEAD_AND_SHOULDERS",
        "ROUNDING_ARC",
        "EXPANSION_RANGE",
        "DIAMOND_PHASES",
    ):
        assert evidence(code, "what was seen").code == code
    future = evidence(
        "CUP_AND_HANDLE_RIM", "a figure not in the catalogue yet", rim_ratio=Decimal("0.8")
    )
    assert future.facts == (("rim_ratio", Decimal("0.8")),)
    mixed = evidence("FLAGPOLE", "d", bars=7, sharp=True, price=Decimal("10.5"), note="text")
    assert [name for name, _ in mixed.facts] == ["bars", "note", "price", "sharp"]  # sorted


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: evidence("flagpole", "d"), "UPPER_SNAKE_CASE"),
        (lambda: evidence("FLAGPOLE", "  "), "human-readable"),
        (lambda: evidence("FLAGPOLE", "d", ratio=0.5), "text, int, bool or Decimal"),  # type: ignore[arg-type]
        (lambda: evidence("FLAGPOLE", "d", Ratio=1), "lower_snake_case"),
        (lambda: evidence("FLAGPOLE", "d", ratio=Decimal("NaN")), "finite"),
        (lambda: chart_pattern.PatternEvidence("FLAGPOLE", "d", (("b", 1), ("a", 2))), "sorted"),
    ],
)
def test_evidence_that_is_not_exact_and_named_is_refused(build: Any, message: str) -> None:
    with pytest.raises(InvalidPatternError, match=message):
        build()


# -- what an evaluation may say -----------------------------------------------------------------


def test_every_state_has_a_coherent_evaluation() -> None:
    for state in PatternState:
        assert evaluation_in(state).state is state


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"evaluated_at": datetime(2026, 1, 5, 12, 0)}, "evaluated_at"),
        ({"as_of": datetime(2030, 1, 1, tzinfo=UTC)}, "closes after the evaluation"),
        ({"candle_count": -1}, "non-negative"),
        ({"candle_count": True}, "non-negative"),
        ({"anchors": ()}, "at least one anchor"),
        ({"anchors": tuple(reversed(double_top_anchors()))}, "chronological"),
    ],
)
def test_an_evaluation_that_is_not_a_well_formed_moment_is_refused(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(InvalidPatternError, match=message):
        evaluation_in(S.GEOMETRICALLY_VALID, **overrides)


def test_an_anchor_that_was_not_yet_confirmed_can_not_be_used() -> None:
    """Look-ahead: the evaluation is made before the last anchor was confirmed."""
    anchors = double_top_anchors()
    with pytest.raises(InvalidPatternError, match="not yet confirmed"):
        before = anchors[-1].confirmed_at - STEP
        evaluation_in(S.FORMING, anchors=anchors, evaluated_at=before, as_of=before)


def test_a_boundary_may_not_reach_beyond_the_evaluation_nor_touch_a_stranger() -> None:
    anchors = double_top_anchors()
    late = Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(anchors[0].open_time, Decimal(100)),
            BoundaryPoint(T0 + timedelta(days=9), Decimal(100)),
        ),
        (),
    )
    with pytest.raises(InvalidPatternError, match="lies after the evaluation"):
        evaluation_in(S.GEOMETRICALLY_VALID, boundaries=(late,))
    stranger = Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(anchors[0].open_time, Decimal(100)),
            BoundaryPoint(anchors[1].open_time, Decimal(100)),
        ),
        (T0 + timedelta(hours=1, minutes=3),),
    )
    with pytest.raises(InvalidPatternError, match="not one of the anchors"):
        evaluation_in(S.GEOMETRICALLY_VALID, boundaries=(stranger,))


def test_a_breakout_candle_that_had_not_closed_can_not_be_used() -> None:
    base = evaluation_in(S.BREAKOUT_PENDING_CONFIRMATION)
    open_candle = Breakout(
        BreakoutDirection.DOWN,
        BoundaryRole.NECKLINE,
        base.evaluated_at - STEP,
        base.evaluated_at + STEP,
        Decimal("99"),
        False,
    )
    with pytest.raises(InvalidPatternError, match="had not closed"):
        evaluation_in(S.BREAKOUT_PENDING_CONFIRMATION, breakout=open_candle)


@pytest.mark.parametrize(
    ("state", "overrides", "message"),
    [
        (S.FORMING, {"breakout": "any"}, "cannot carry a breakout"),
        (S.GEOMETRICALLY_VALID, {"breakout": "any"}, "cannot carry a breakout"),
        (S.INVALIDATED, {"invalidation_reasons": ()}, "exactly when INVALIDATED"),
        (
            S.FORMING,
            {"invalidation_reasons": (InvalidationReason.TOO_LONG,)},
            "exactly when INVALIDATED",
        ),
        (
            S.INVALIDATED,
            {"invalidation_reasons": (InvalidationReason.TOO_LONG,) * 2},
            "listed once",
        ),
        (S.INSUFFICIENT_DATA, {"insufficient_data_reasons": ()}, "exactly when"),
        (S.FORMING, {"insufficient_data_reasons": (MissingDataReason.NO_DATA,)}, "exactly when"),
        (S.INSUFFICIENT_DATA, {"breakout": "any"}, "nothing is claimed about a breakout"),
        (S.BREAKOUT_PENDING_CONFIRMATION, {"breakout": None}, "defined by a breakout"),
        (S.CONFIRMED_UP, {"breakout": None}, "defined by a breakout"),
        (S.CONFIRMED_DOWN, {"breakout": None}, "defined by a breakout"),
        (S.FAILED_BREAKOUT, {"breakout": None}, "defined by a breakout"),
        (S.GEOMETRICALLY_VALID, {"boundaries": ()}, "needs the boundaries"),
        (S.CONFIRMED_DOWN, {"boundaries": ()}, "needs the boundaries"),
    ],
)
def test_the_content_must_agree_with_the_state(
    state: PatternState, overrides: dict[str, Any], message: str
) -> None:
    if overrides.get("breakout") == "any":
        overrides["breakout"] = evaluation_in(S.CONFIRMED_DOWN).breakout
    with pytest.raises(InvalidPatternError, match=message):
        evaluation_in(state, **overrides)


def test_a_breakout_must_match_the_state_that_names_it() -> None:
    down = evaluation_in(S.CONFIRMED_DOWN).breakout
    up = evaluation_in(S.CONFIRMED_UP).breakout
    pending = evaluation_in(S.BREAKOUT_PENDING_CONFIRMATION).breakout
    assert down is not None and up is not None and pending is not None
    with pytest.raises(InvalidPatternError, match="needs its breakout confirmed"):
        evaluation_in(S.CONFIRMED_UP, breakout=down)
    with pytest.raises(InvalidPatternError, match="needs its breakout confirmed"):
        evaluation_in(S.CONFIRMED_DOWN, breakout=up)
    with pytest.raises(InvalidPatternError, match="needs its breakout confirmed"):
        evaluation_in(S.CONFIRMED_DOWN, breakout=dataclasses.replace(down, confirmed=False))
    with pytest.raises(InvalidPatternError, match="not yet confirmed"):
        evaluation_in(
            S.BREAKOUT_PENDING_CONFIRMATION, breakout=dataclasses.replace(pending, confirmed=True)
        )


def test_a_breakout_must_go_through_a_boundary_the_figure_has() -> None:
    down = evaluation_in(S.CONFIRMED_DOWN).breakout
    assert down is not None
    with pytest.raises(InvalidPatternError, match="boundary the figure lacks"):
        evaluation_in(
            S.CONFIRMED_DOWN, breakout=dataclasses.replace(down, boundary=BoundaryRole.UPPER)
        )


# -- the instance -------------------------------------------------------------------------------


def test_an_instance_carries_what_the_task_requires() -> None:
    built = instance_from(S.FORMING, S.GEOMETRICALLY_VALID)

    assert built.pattern_type is PatternType.DOUBLE_TOP
    assert built.traditional_roles == {PatternRole.REVERSAL}
    assert built.traditional_bias is PatternBias.BEARISH
    assert (built.instrument_id, built.data_source, built.timeframe) == (
        "instrument-1",
        "BINANCE",
        TF,
    )
    assert built.started_at == double_top_anchors()[0].open_time
    assert built.observed_at == built.evaluations[0].evaluated_at
    assert built.last_evaluated_at == built.evaluations[-1].evaluated_at > built.observed_at
    assert built.latest.anchors == double_top_anchors()
    assert built.latest.candle_count == 21
    assert (built.detector_version, built.parameter_version) == (
        "double-top-detector-v1",
        "params-v1",
    )
    assert built.state is S.GEOMETRICALLY_VALID and not built.is_terminal
    assert built.model_version == PATTERN_MODEL_VERSION == "pattern-instance-v1"


def test_a_pattern_needs_the_anchors_its_geometry_needs_before_it_is_valid() -> None:
    forming = instance_from(S.FORMING)
    assert forming.state is S.FORMING  # a figure still forming may have fewer
    two_anchors = double_top_anchors(2)
    born = start_pattern_instance(
        pattern_type=PatternType.DOUBLE_TOP,
        instrument_id="i",
        data_source="s",
        timeframe=TF,
        detector_version="d",
        parameter_version="p",
        first_evaluation=evaluation_in(S.FORMING, anchors=two_anchors),
    )
    with pytest.raises(InvalidPatternError, match="needs 3 anchors"):
        born.advance(evaluation_in(S.GEOMETRICALLY_VALID, 1, anchors=two_anchors))
    with pytest.raises(InvalidPatternError, match="needs 5 anchors"):
        start_pattern_instance(
            pattern_type=PatternType.HEAD_AND_SHOULDERS_TOP,
            instrument_id="i",
            data_source="s",
            timeframe=TF,
            detector_version="d",
            parameter_version="p",
            first_evaluation=evaluation_in(S.GEOMETRICALLY_VALID),
        )


def test_every_field_that_names_a_figure_must_be_declared() -> None:
    first = evaluation_in(S.FORMING)
    for field in ("instrument_id", "data_source", "detector_version", "parameter_version"):
        values: dict[str, Any] = {
            "pattern_type": PatternType.DOUBLE_TOP,
            "instrument_id": "i",
            "data_source": "s",
            "timeframe": TF,
            "detector_version": "d",
            "parameter_version": "p",
            "first_evaluation": first,
        }
        values[field] = "  "
        with pytest.raises(InvalidPatternError, match=field):
            start_pattern_instance(**values)
    with pytest.raises(InvalidPatternError, match="one of the catalogue"):
        PatternInstance("DOUBLE_TOP", "i", "s", TF, "d", "p", (first,))  # type: ignore[arg-type]
    with pytest.raises(InvalidPatternError, match="born from an evaluation"):
        PatternInstance(PatternType.DOUBLE_TOP, "i", "s", TF, "d", "p", ())


# -- identity and versions ----------------------------------------------------------------------


def identity(**changes: Any) -> Any:
    values: dict[str, Any] = {
        "pattern_type": PatternType.DOUBLE_TOP,
        "instrument_id": "instrument-1",
        "data_source": "BINANCE",
        "timeframe": TF,
        "started_at": T0,
        "first_anchor_kind": HIGH,
        "detector_version": "d1",
        "parameter_version": "p1",
    }
    values.update(changes)
    return derive_pattern_instance_id(**values)


def test_the_same_figure_found_again_is_the_same_instance() -> None:
    assert identity() == identity()
    assert (
        instance_from(S.FORMING).pattern_instance_id == instance_from(S.FORMING).pattern_instance_id
    )
    # ... and advancing it does not change who it is.
    assert (
        instance_from(S.FORMING).pattern_instance_id
        == instance_from(
            S.FORMING, S.GEOMETRICALLY_VALID, S.BREAKOUT_PENDING_CONFIRMATION
        ).pattern_instance_id
    )


@pytest.mark.parametrize(
    "change",
    [
        {"pattern_type": PatternType.TRIPLE_TOP},
        {"instrument_id": "instrument-2"},
        {"data_source": "KRAKEN"},
        {"timeframe": Timeframe.H1},
        {"started_at": T0 + STEP},
        {"first_anchor_kind": LOW},
        {"detector_version": "d2"},
        {"parameter_version": "p2"},
        {"model_version": "pattern-instance-v2"},
    ],
    ids=lambda change: next(iter(change)),
)
def test_anything_that_makes_it_another_figure_makes_another_identity(
    change: dict[str, Any],
) -> None:
    assert identity(**change) != identity()


# -- lifecycle ----------------------------------------------------------------------------------

# From each state, the states an evaluation may go to. Written out on its own, from the task:
# a figure forms, becomes valid, is broken out of, and the breakout is confirmed or fails; at
# any point it may be invalidated; FAILED_BREAKOUT and INVALIDATED are final.
ALLOWED: dict[PatternState, set[PatternState]] = {
    S.FORMING: {S.FORMING, S.GEOMETRICALLY_VALID, S.INVALIDATED},
    S.GEOMETRICALLY_VALID: {S.GEOMETRICALLY_VALID, S.BREAKOUT_PENDING_CONFIRMATION, S.INVALIDATED},
    S.BREAKOUT_PENDING_CONFIRMATION: {
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.CONFIRMED_UP,
        S.CONFIRMED_DOWN,
        S.FAILED_BREAKOUT,
        S.INVALIDATED,
    },
    S.CONFIRMED_UP: {S.CONFIRMED_UP, S.FAILED_BREAKOUT, S.INVALIDATED},
    S.CONFIRMED_DOWN: {S.CONFIRMED_DOWN, S.FAILED_BREAKOUT, S.INVALIDATED},
    S.FAILED_BREAKOUT: set(),
    S.INVALIDATED: set(),
}
PATH_TO = {
    S.FORMING: (S.FORMING,),
    S.GEOMETRICALLY_VALID: (S.FORMING, S.GEOMETRICALLY_VALID),
    S.BREAKOUT_PENDING_CONFIRMATION: (
        S.FORMING,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
    ),
    S.CONFIRMED_UP: (
        S.FORMING,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.CONFIRMED_UP,
    ),
    S.CONFIRMED_DOWN: (
        S.FORMING,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.CONFIRMED_DOWN,
    ),
    S.FAILED_BREAKOUT: (
        S.FORMING,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.FAILED_BREAKOUT,
    ),
    S.INVALIDATED: (S.FORMING, S.INVALIDATED),
}


@pytest.mark.parametrize(
    ("origin", "target"),
    [(o, t) for o, t in product(ALLOWED, PatternState) if t is not S.INSUFFICIENT_DATA],
    ids=lambda state: state.value,
)
def test_every_pair_of_states_is_allowed_or_refused_as_the_table_says(
    origin: PatternState, target: PatternState
) -> None:
    built = instance_from(*PATH_TO[origin])
    step = len(PATH_TO[origin])
    if target in ALLOWED[origin]:
        assert built.advance(evaluation_in(target, step)).state is target
    else:
        with pytest.raises(InvalidPatternError):
            built.advance(evaluation_in(target, step))


def test_a_figure_can_be_unjudgeable_at_any_moment_and_then_carry_on() -> None:
    for origin, path in PATH_TO.items():
        if origin in ALLOWED and not ALLOWED[origin]:
            continue  # final states take no more evaluations, not even this one
        built = instance_from(*path)
        step = len(path)
        paused = built.advance(evaluation_in(S.INSUFFICIENT_DATA, step))
        assert paused.state is S.INSUFFICIENT_DATA
        # It carries on from the state it had, or from anything that state could go to.
        for target in ALLOWED[origin]:
            assert paused.advance(evaluation_in(target, step + 1)).state is target


def test_an_interruption_does_not_let_a_figure_skip_or_go_back() -> None:
    valid = instance_from(S.FORMING, S.GEOMETRICALLY_VALID).advance(
        evaluation_in(S.INSUFFICIENT_DATA, 2)
    )
    with pytest.raises(InvalidPatternError, match="GEOMETRICALLY_VALID cannot go to FORMING"):
        valid.advance(evaluation_in(S.FORMING, 3))
    with pytest.raises(InvalidPatternError, match="cannot go to CONFIRMED_UP"):
        valid.advance(evaluation_in(S.CONFIRMED_UP, 3))


def test_a_figure_that_was_born_without_enough_data_can_still_start_forming() -> None:
    born = start_pattern_instance(
        pattern_type=PatternType.DOUBLE_TOP,
        instrument_id="i",
        data_source="s",
        timeframe=TF,
        detector_version="d",
        parameter_version="p",
        first_evaluation=evaluation_in(S.INSUFFICIENT_DATA),
    )
    assert born.advance(evaluation_in(S.FORMING, 1)).state is S.FORMING
    assert born.advance(evaluation_in(S.GEOMETRICALLY_VALID, 1)).state is S.GEOMETRICALLY_VALID
    with pytest.raises(InvalidPatternError):
        born.advance(evaluation_in(S.CONFIRMED_UP, 1))


@pytest.mark.parametrize("final", [S.INVALIDATED, S.FAILED_BREAKOUT])
def test_nothing_follows_a_final_state_not_even_a_pause(final: PatternState) -> None:
    ended = instance_from(*PATH_TO[final])
    assert ended.is_terminal
    for state in PatternState:
        with pytest.raises(InvalidPatternError, match="is final"):
            ended.advance(evaluation_in(state, 9))


def test_evaluations_only_move_forward_and_never_read_less() -> None:
    built = instance_from(S.FORMING, S.GEOMETRICALLY_VALID)
    latest = built.latest
    assert latest.as_of is not None
    with pytest.raises(InvalidPatternError, match="strictly forward"):
        built.advance(dataclasses.replace(latest))  # the same instant again
    earlier = evaluation_in(S.GEOMETRICALLY_VALID, 0)
    with pytest.raises(InvalidPatternError, match="strictly forward"):
        built.advance(earlier)
    with pytest.raises(InvalidPatternError, match="fewer candles"):
        built.advance(evaluation_in(S.GEOMETRICALLY_VALID, 2, as_of=latest.as_of - STEP))
    with pytest.raises(InvalidPatternError, match="fewer candles"):
        built.advance(evaluation_in(S.GEOMETRICALLY_VALID, 2, as_of=None))
    with pytest.raises(InvalidPatternError, match="cannot go down"):
        built.advance(evaluation_in(S.GEOMETRICALLY_VALID, 2, candle_count=5))


# -- append-only: a substantial change is another instance --------------------------------------


def test_anchors_can_only_be_added_never_changed_or_removed() -> None:
    forming = instance_from(S.FORMING)
    more = double_top_anchors()
    longer = forming.advance(evaluation_in(S.FORMING, 1, anchors=more))
    assert len(longer.latest.anchors) == 3
    assert len(forming.latest.anchors) == 3  # the earlier one is untouched


def test_replacing_a_removing_or_relabelling_an_anchor_is_another_figure() -> None:
    base = double_top_anchors()
    built = instance_from(S.FORMING)

    moved = (*base[:2], anchor(2, HIGH, "111.0", "SECOND_PEAK"))
    with pytest.raises(InvalidPatternError, match="another instance"):
        built.advance(evaluation_in(S.FORMING, 1, anchors=moved))
    relabelled = (*base[:2], anchor(2, HIGH, "110.2", "OTHER_LABEL"))
    with pytest.raises(InvalidPatternError, match="another instance"):
        built.advance(evaluation_in(S.FORMING, 1, anchors=relabelled))
    with pytest.raises(InvalidPatternError, match="another instance"):
        built.advance(evaluation_in(S.FORMING, 1, anchors=base[1:]))  # another starting point
    with pytest.raises(InvalidPatternError, match="another instance"):
        later = built.latest.evaluated_at + STEP * 3
        built.advance(
            evaluation_in(S.FORMING, 1, anchors=base[:2], evaluated_at=later, as_of=later)
        )  # one fewer


def test_the_past_is_never_rewritten() -> None:
    built = instance_from(S.FORMING, S.GEOMETRICALLY_VALID)
    before = built.document()
    later = built.advance(evaluation_in(S.BREAKOUT_PENDING_CONFIRMATION, 2))

    assert built.document() == before
    assert later.evaluations[:2] == built.evaluations
    assert later.pattern_instance_id == built.pattern_instance_id
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.evaluations = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.latest.state = S.INVALIDATED  # type: ignore[misc]
    assert isinstance(built.evaluations, tuple) and isinstance(built.latest.anchors, tuple)


def test_several_figures_coexist_over_the_same_candles() -> None:
    double_top = instance_from(S.FORMING, S.GEOMETRICALLY_VALID)
    other_start = tuple(
        AnchorPivot(a.kind, a.open_time + STEP, a.price, a.confirmed_at + STEP, a.label)
        for a in double_top_anchors()
    )
    triple = start_pattern_instance(
        pattern_type=PatternType.TRIPLE_TOP,
        instrument_id="instrument-1",
        data_source="BINANCE",
        timeframe=TF,
        detector_version="triple-top-detector-v1",
        parameter_version="params-v1",
        first_evaluation=evaluation_in(S.FORMING, anchors=other_start),
    )
    same_type_other_start = start_pattern_instance(
        pattern_type=PatternType.DOUBLE_TOP,
        instrument_id="instrument-1",
        data_source="BINANCE",
        timeframe=TF,
        detector_version="double-top-detector-v1",
        parameter_version="params-v1",
        first_evaluation=evaluation_in(S.FORMING, anchors=other_start),
    )
    ids = {
        double_top.pattern_instance_id,
        triple.pattern_instance_id,
        same_type_other_start.pattern_instance_id,
    }
    assert len(ids) == 3  # none of them replaced, hid or merged with another


def test_a_confirmed_breakout_is_compared_with_tradition_without_being_forced_to_agree() -> None:
    with_tradition = instance_from(*PATH_TO[S.CONFIRMED_DOWN])  # a double top, bearish
    against = instance_from(*PATH_TO[S.CONFIRMED_UP])
    assert with_tradition.resolved_with_tradition is True
    assert against.resolved_with_tradition is False  # tradition is not evidence: it can fail
    assert instance_from(S.FORMING).resolved_with_tradition is None
    four = (
        anchor(0, HIGH, "110.0", "UPPER_ONE"),
        anchor(1, LOW, "100.0", "LOWER_ONE"),
        anchor(2, HIGH, "108.0", "UPPER_TWO"),
        anchor(3, LOW, "102.0", "LOWER_TWO"),
    )
    triangle = start_pattern_instance(
        pattern_type=PatternType.SYMMETRICAL_TRIANGLE,
        instrument_id="i",
        data_source="s",
        timeframe=TF,
        detector_version="d",
        parameter_version="p",
        first_evaluation=evaluation_in(S.FORMING, anchors=four),
    )
    for step, state in enumerate(PATH_TO[S.CONFIRMED_UP][1:], start=1):
        triangle = triangle.advance(evaluation_in(state, step, anchors=four))
    assert triangle.state is S.CONFIRMED_UP
    assert triangle.resolved_with_tradition is None  # tradition does not say before the breakout


def test_a_bullish_pattern_is_read_against_tradition_the_other_way_round() -> None:
    bottom_up = instance_from(*PATH_TO[S.CONFIRMED_UP], pattern_type=PatternType.DOUBLE_BOTTOM)
    bottom_down = instance_from(*PATH_TO[S.CONFIRMED_DOWN], pattern_type=PatternType.DOUBLE_BOTTOM)
    assert PATTERN_CATALOGUE[PatternType.DOUBLE_BOTTOM].traditional_bias is PatternBias.BULLISH
    assert bottom_up.resolved_with_tradition is True
    assert bottom_down.resolved_with_tradition is False


# -- the document -------------------------------------------------------------------------------


def rich_instance() -> PatternInstance:
    base = evaluation_in(S.GEOMETRICALLY_VALID, 1)
    decorated = dataclasses.replace(
        base,
        evidence=(
            evidence(
                "HEAD_AND_SHOULDERS",
                "the two peaks are level within tolerance",
                peak_gap=Decimal("0.2"),
                touches=3,
                symmetrical=True,
                note="ok",
            ),
        ),
    )
    return instance_from(S.FORMING).advance(decorated)


def test_it_is_written_and_read_back_exactly_as_it_was() -> None:
    for built in (
        instance_from(S.FORMING),
        rich_instance(),
        instance_from(*PATH_TO[S.CONFIRMED_DOWN]),
        instance_from(*PATH_TO[S.INVALIDATED]),
        instance_from(S.FORMING, S.GEOMETRICALLY_VALID).advance(
            evaluation_in(S.INSUFFICIENT_DATA, 2)
        ),
    ):
        as_json = json.loads(json.dumps(built.document()))  # what a database or an API keeps
        assert pattern_instance_from_document(as_json) == built
        assert pattern_instance_from_document(built.document()) == built


def test_the_document_says_what_the_task_lists() -> None:
    document = rich_instance().document()
    for name in (
        "pattern_instance_id",
        "pattern_type",
        "traditional_roles",
        "traditional_bias",
        "instrument_id",
        "timeframe",
        "observed_at",
        "started_at",
        "last_evaluated_at",
        "state",
        "detector_version",
        "parameter_version",
    ):
        assert name in document
    latest = document["evaluations"][-1]
    for name in ("anchors", "boundaries", "breakout", "candle_count", "invalidation_reasons"):
        assert name in latest
    assert (
        document["traditional_roles"] == ["REVERSAL"] and document["state"] == "GEOMETRICALLY_VALID"
    )


def test_the_document_holds_no_float_and_prices_are_exact_text() -> None:
    def walk(value: object) -> None:
        assert not isinstance(value, float | Decimal)
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    document = rich_instance().document()
    walk(document)
    assert document["evaluations"][-1]["anchors"][0]["price"] == "110.0"
    fact = document["evaluations"][-1]["evidence"][0]["facts"]["peak_gap"]
    assert fact == {"type": "decimal", "value": "0.2"}  # the type travels with the value


def _tamper(mutate: Any) -> dict[str, Any]:
    document = instance_from(S.FORMING, S.GEOMETRICALLY_VALID).document()
    mutate(document)
    return document


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("evaluations"),
        lambda d: d.pop("pattern_instance_id"),
        lambda d: d.update(pattern_type="DOUBLE_TOP_PLUS"),
        lambda d: d.update(
            pattern_type="TRIPLE_TOP"
        ),  # a different figure: the identity betrays it
        lambda d: d.update(pattern_instance_id="00000000-0000-0000-0000-000000000000"),
        lambda d: d.update(instrument_id="instrument-2"),
        lambda d: d.update(model_version="pattern-instance-v0"),
        lambda d: d["evaluations"][0].update(state="SIDEWAYS"),
        lambda d: d["evaluations"][0]["anchors"][0].update(price="not a price"),
        lambda d: d["evaluations"][0]["anchors"][0].update(price="-1"),
        lambda d: d["evaluations"][0]["anchors"][0].update(open_time="2026-01-05T10:00:00"),
        lambda d: d["evaluations"][0]["anchors"][0].update(open_time="2026-01-05T10:00:00+02:00"),
        lambda d: d["evaluations"].append(  # valid, then forming again: a step backwards
            {
                **d["evaluations"][0],
                "evaluated_at": "2026-01-06T00:00:00Z",
                "as_of": "2026-01-06T00:00:00Z",
            }
        ),
        lambda d: d["evaluations"][1].update(evaluated_at=d["evaluations"][0]["evaluated_at"]),
    ],
    ids=[
        "no-evaluations",
        "no-identity",
        "unknown-type",
        "other-type",
        "forged-identity",
        "other-instrument",
        "other-model-version",
        "unknown-state",
        "bad-price",
        "negative-price",
        "naive-instant",
        "offset-instant",
        "state-goes-back",
        "time-does-not-advance",
    ],
)
def test_a_document_that_is_not_a_pattern_instance_is_refused_never_repaired(mutate: Any) -> None:
    with pytest.raises(InvalidPatternError):
        pattern_instance_from_document(_tamper(mutate))


def test_a_document_of_another_model_version_is_not_read() -> None:
    """Even when its identity is consistent with what it says: it is another format."""
    other = dataclasses.replace(instance_from(S.FORMING), model_version="pattern-instance-v0")
    with pytest.raises(InvalidPatternError, match="unsupported model version"):
        pattern_instance_from_document(other.document())


# -- anchored on real pivots --------------------------------------------------------------------


def test_a_figure_can_be_anchored_on_the_real_confirmed_pivots_of_real_candles() -> None:
    """Two equal peaks with a trough between them, on candles built leg by leg: the anchors are
    the confirmed swing points the structure module really finds, not hand-made ones."""
    candles = zigzag([100, 110, 100, 110, 101], tail=4)
    observed_at = observed_after(candles)
    result = detect_pivots(candles, timeframe=TF, observed_at=observed_at)
    swings = swing_points(result.confirmed)
    peaks_and_trough = list(swings)[:3]
    assert [s.kind for s in peaks_and_trough] == [HIGH, LOW, HIGH]

    labels = ("FIRST_PEAK", "TROUGH", "SECOND_PEAK")
    anchors = tuple(
        AnchorPivot.from_pivot(p, label) for p, label in zip(peaks_and_trough, labels, strict=True)
    )
    trough = anchors[1]
    line = Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(anchors[0].open_time, trough.price),
            BoundaryPoint(anchors[2].open_time, trough.price),
        ),
        (trough.open_time,),
    )
    figure = start_pattern_instance(
        pattern_type=PatternType.DOUBLE_TOP,
        instrument_id="instrument-1",
        data_source="BINANCE",
        timeframe=TF,
        detector_version="double-top-detector-v1",
        parameter_version="params-v1",
        first_evaluation=PatternEvaluation(
            evaluated_at=observed_at,
            as_of=candles[-1].close_time,
            candle_count=len(candles),
            state=S.GEOMETRICALLY_VALID,
            anchors=anchors,
            boundaries=(line,),
            evidence=(
                evidence(
                    "DOUBLE_TOP_PEAKS",
                    "the peaks are level",
                    gap=anchors[2].price - anchors[0].price,
                ),
            ),
        ),
    )
    assert figure.state is S.GEOMETRICALLY_VALID
    assert figure.started_at == anchors[0].open_time
    assert pattern_instance_from_document(figure.document()) == figure


# -- what the model must never become -----------------------------------------------------------


_FORBIDDEN = {
    "side",
    "action",
    "position",
    "entry",
    "order",
    "short",
    "long",
    "signal",
    "confidence",
    "score",
    "probability",
    "recommendation",
    "target",
    "stop_loss",
    "take_profit",
}


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= _keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= _keys(item)
    return found


def test_an_instance_holds_no_signal_no_decision_and_no_probability() -> None:
    built = rich_instance()
    fields = {f.name for f in dataclasses.fields(PatternInstance)}
    fields |= {f.name for f in dataclasses.fields(PatternEvaluation)}
    assert fields.isdisjoint(_FORBIDDEN)
    assert _keys(built.document()).isdisjoint(_FORBIDDEN)
    assert not hasattr(built, "signal") and not hasattr(built, "probability")


def test_the_module_only_depends_on_the_domain_layer() -> None:
    tree = ast.parse(Path(chart_pattern.__file__).read_text(encoding="utf-8"))
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
    stdlib = {"enum", "re", "uuid", "collections.abc", "dataclasses", "datetime", "decimal"}
    stdlib |= {"itertools", "types", "typing"}
    foreign = {
        m for m in imported if m not in stdlib and not m.startswith("freyja_backend.domain.")
    }
    assert foreign == set()
