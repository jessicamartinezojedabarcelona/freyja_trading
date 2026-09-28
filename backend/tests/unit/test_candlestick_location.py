"""POINT4-CONTEXT-001: candle pattern location.

The two scenarios the contract (`docs/domain/localizacion-de-patron-de-vela.md`, section 8)
requires before anything else: a pivot that confirms after the pattern's own instant, and a chart
figure initially held back by an overlap policy (`published_at` later than `known_at`). Both must
add a *new* evaluation, dated when the fact actually became knowable, without touching the
earlier one.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from freyja_backend.domain.candlestick_location import (
    DEFAULT_LOCATION_PARAMS,
    LOCATION_PARAMETER_VERSION,
    LocationContext,
    LocationEvaluation,
    LocationParams,
    LocationState,
    PatternLocation,
    evaluate_location,
)
from freyja_backend.domain.candlestick_pattern import (
    CandleAnchor,
    CandlePatternEvaluation,
    CandlePatternInstance,
    CandlePatternState,
    CandlePatternType,
    start_candle_pattern_instance,
)
from freyja_backend.domain.chart_pattern import (
    AnchorPivot,
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    PatternEvaluation,
    PatternInstance,
    PatternState,
    PatternType,
    evidence,
    start_pattern_instance,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle, InstrumentRef, Timeframe
from freyja_backend.domain.market_structure import PivotKind
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError

S = LocationState
TF = Timeframe.M5
STEP = TF.duration
SOURCE = "BINANCE"
AUTHORIZED = frozenset({SOURCE})
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")
T0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
SMALL_HISTORY = LocationParams(min_history=10)


# -- building fixtures ------------------------------------------------------------------------


def candle_at(open_time: datetime, o: str, h: str, low: str, c: str) -> Candle:
    return Candle(
        open_time, open_time + STEP, Decimal(o), Decimal(h), Decimal(low), Decimal(c), Decimal("1")
    )


def flat_candles(start: datetime, count: int, base: str = "50") -> list[Candle]:
    """Ordinary, boring candles: no confirmed pivot ever forms inside a monotonic-ish run like
    this, so they never interfere with a test's own, deliberately placed structure."""
    out = []
    price = Decimal(base)
    for i in range(count):
        price += Decimal("1")
        out.append(
            candle_at(start + STEP * i, str(price), str(price + 1), str(price - 1), str(price))
        )
    return out


def context_for(
    *,
    observed_at: datetime,
    params: LocationParams = SMALL_HISTORY,
    authorized_sources: frozenset[str] = AUTHORIZED,
) -> LocationContext:
    return LocationContext(
        instrument_id="instrument-1",
        instrument=BTC,
        schedule=MarketSchedule.CONTINUOUS_24_7,
        data_source=SOURCE,
        authorized_sources=authorized_sources,
        timeframe=TF,
        observed_at=observed_at,
        params=params,
    )


def doji_pattern(evaluated_at: datetime, price: str = "110") -> CandlePatternInstance:
    p = Decimal(price)
    anchor = CandleAnchor(
        evaluated_at - STEP, evaluated_at, p, p + Decimal("1"), p - Decimal("1"), p, "FIRST"
    )
    context_ev = evidence("CONTEXT", "no context required", required="NONE", compatible=True)
    ev = CandlePatternEvaluation(
        evaluated_at, evaluated_at, CandlePatternState.CONFIRMED, (anchor,), evidence=(context_ev,)
    )
    return start_candle_pattern_instance(
        pattern_type=CandlePatternType.DOJI,
        instrument_id="instrument-1",
        data_source=SOURCE,
        timeframe=TF,
        detector_version="test-fixture-v1",
        parameter_version="test-fixture-v1",
        first_evaluation=ev,
    )


def figure_anchor(
    index: int, kind: PivotKind, price: str, label: str, base: datetime
) -> AnchorPivot:
    opened = base + STEP * 10 * index
    return AnchorPivot(kind, opened, Decimal(price), opened + STEP * 4, label)


def make_figure(
    *,
    base: datetime,
    known_at: datetime,
    published_at: datetime | None = None,
    provenance: str | None = None,
    boundary_price: str = "110",
) -> PatternInstance:
    """A minimal DOUBLE_TOP with hand-set timing facts. `published_at`/`provenance` are, in real
    detection, only ever produced by the diamond (contract, section 4) -- setting them by hand
    here tests this module's own consumption of them, independent of reproducing the diamond's
    own overlap machinery (already covered in `test_pattern_diamond.py`)."""
    anchors = (
        figure_anchor(0, PivotKind.HIGH, boundary_price, "FIRST_PEAK", base),
        figure_anchor(1, PivotKind.LOW, "100", "TROUGH", base),
        figure_anchor(2, PivotKind.HIGH, "110.2", "SECOND_PEAK", base),
    )
    neckline = Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(anchors[1].open_time, Decimal(boundary_price)),
            BoundaryPoint(anchors[-1].open_time, Decimal(boundary_price)),
        ),
        (anchors[1].open_time,),
    )
    facts: dict[str, object] = {
        "market_formed_at": known_at.isoformat(),
        "receipts_available": True,
        "known_at": known_at.isoformat(),
    }
    if published_at is not None:
        facts["published_at"] = published_at.isoformat()
    if provenance is not None:
        facts["provenance"] = provenance
    timing = evidence("BREAKOUT_TIMING", "test fixture timing", **facts)  # type: ignore[arg-type]
    evaluated_at = anchors[-1].confirmed_at
    figure_evaluation = PatternEvaluation(
        evaluated_at,
        evaluated_at,
        20,
        PatternState.GEOMETRICALLY_VALID,
        anchors,
        (neckline,),
        evidence=(timing,),
    )
    return start_pattern_instance(
        pattern_type=PatternType.DOUBLE_TOP,
        instrument_id="instrument-1",
        data_source=SOURCE,
        timeframe=TF,
        detector_version="test-fixture-v1",
        parameter_version="test-fixture-v1",
        first_evaluation=figure_evaluation,
    )


# -- required scenario 1: a pivot that confirms after the pattern's own instant -----------------


def test_a_pivot_confirmed_later_is_added_as_a_new_evaluation_not_backdated() -> None:
    padding = flat_candles(T0, 15)  # a mild rise: no confirmed pivot forms inside it
    peak = candle_at(padding[-1].close_time, "105", "110", "104", "106")
    after1 = candle_at(peak.close_time, "106", "108", "105", "107")
    after2 = candle_at(after1.close_time, "107", "107", "104", "105")
    after3 = candle_at(after2.close_time, "105", "106", "103", "104")  # k=3rd: confirms the peak
    candles = [*padding, peak, after1, after2, after3]
    peak_confirmed_at = after3.close_time

    pattern = doji_pattern(after1.close_time, price="110")  # before the peak confirms
    assert pattern.latest.evaluated_at < peak_confirmed_at

    first_context = context_for(observed_at=after2.close_time + timedelta(seconds=1))
    location = evaluate_location(first_context, candles[:-1], pattern, ())
    assert len(location.evaluations) == 1
    first_eval = location.evaluations[0]
    assert first_eval.state is S.NOT_NEAR_LEVEL  # the peak is not confirmed yet: not "known"
    assert first_eval.evaluated_at == pattern.latest.evaluated_at

    second_context = context_for(observed_at=candles[-1].close_time + timedelta(seconds=1))
    location = evaluate_location(second_context, candles, pattern, (), previous=location)
    assert len(location.evaluations) == 2
    assert location.evaluations[0] == first_eval  # untouched
    second_eval = location.evaluations[1]
    assert second_eval.state is S.NEAR_LEVEL
    assert second_eval.evaluated_at == peak_confirmed_at  # dated when it became knowable
    assert second_eval.evaluated_at != pattern.latest.evaluated_at
    levels = {item.code for item in second_eval.evidence}
    assert "LEVEL" in levels


# -- required scenario 2: a figure initially covered (held) by another --------------------------


def test_a_figure_held_by_an_overlap_policy_is_added_only_once_published() -> None:
    pattern = doji_pattern(T0, price="110")
    held_until = T0 + STEP * 50
    figure = make_figure(
        base=T0 - STEP * 200,
        known_at=T0 - STEP * 5,  # geometry was known before the pattern
        published_at=held_until,  # but not offered until well after it
        boundary_price="110",
    )
    candles = flat_candles(T0 - STEP * 300, 400)

    first_context = context_for(observed_at=T0 + timedelta(seconds=1))
    location = evaluate_location(first_context, candles, pattern, (figure,))
    first_eval = location.evaluations[0]
    assert first_eval.state is S.NOT_NEAR_LEVEL  # held back: not usable yet
    assert first_eval.evaluated_at == pattern.latest.evaluated_at
    assert "LEVEL" not in {item.code for item in first_eval.evidence}

    second_context = context_for(observed_at=held_until + timedelta(seconds=1))
    location = evaluate_location(second_context, candles, pattern, (figure,), previous=location)
    assert len(location.evaluations) == 2
    assert location.evaluations[0] == first_eval  # untouched
    second_eval = location.evaluations[1]
    assert second_eval.state is S.NEAR_LEVEL
    assert second_eval.evaluated_at == held_until  # dated at publication, not at known_at or T0
    level = next(item for item in second_eval.evidence if item.code == "LEVEL")
    facts = dict(level.facts)
    assert facts["source_published_at"] == held_until.isoformat()


def test_provenance_is_copied_from_the_figure_never_recomputed() -> None:
    pattern = doji_pattern(T0, price="110")
    figure = make_figure(
        base=T0 - STEP * 200,
        known_at=T0 - STEP * 5,
        provenance="RETROSPECTIVE",
        boundary_price="110",
    )
    candles = flat_candles(T0 - STEP * 300, 400)
    location = evaluate_location(
        context_for(observed_at=T0 + timedelta(seconds=1)), candles, pattern, (figure,)
    )
    level = next(item for item in location.latest.evidence if item.code == "LEVEL")
    assert dict(level.facts)["source_provenance"] == "RETROSPECTIVE"


# -- NOT_NEAR_LEVEL vs INSUFFICIENT_DATA never confused ------------------------------------------


def test_not_near_level_is_not_insufficient_data() -> None:
    pattern = doji_pattern(T0, price="110")
    candles = flat_candles(T0 - STEP * 50, 60)
    location = evaluate_location(
        context_for(observed_at=T0 + timedelta(seconds=1)), candles, pattern, ()
    )
    assert location.latest.state is S.NOT_NEAR_LEVEL
    assert location.latest.insufficient_data_reasons == ()


def test_too_little_history_is_insufficient_data_not_not_near_level() -> None:
    pattern = doji_pattern(T0, price="110")
    candles = flat_candles(T0 - STEP * 3, 4)  # far below min_history=10
    location = evaluate_location(
        context_for(observed_at=T0 + timedelta(seconds=1)), candles, pattern, ()
    )
    assert location.latest.state is S.INSUFFICIENT_DATA
    assert location.latest.insufficient_data_reasons != ()


def test_an_unauthorized_source_is_insufficient_data() -> None:
    pattern = doji_pattern(T0, price="110")
    candles = flat_candles(T0 - STEP * 50, 60)
    context = context_for(
        observed_at=T0 + timedelta(seconds=1), authorized_sources=frozenset({"SOMEONE_ELSE"})
    )
    location = evaluate_location(context, candles, pattern, ())
    assert location.latest.state is S.INSUFFICIENT_DATA
    assert MissingDataReason.SOURCE_NOT_AUTHORIZED in location.latest.insufficient_data_reasons


# -- replay stability -------------------------------------------------------------------------


def test_replay_is_stable_evaluating_once_at_the_end_matches_step_by_step() -> None:
    """Replay significa rehacer la MISMA secuencia de llamadas (primera restringida a
    `pattern_at`, después encadenando `previous`), no una única llamada con `previous=None`:
    la sección 3 del contrato exige que la primera evaluación se restrinja siempre al instante
    propio del patrón, sin importar cuántas velas u `observed_at` se le pasen. Por eso un replay
    "de una sentada" sigue siendo dos llamadas — igual que en vivo — y se compara contra el
    resultado paso a paso obtenido con `observed_at` intermedios reales.
    """
    padding = flat_candles(T0, 15)
    peak = candle_at(padding[-1].close_time, "105", "110", "104", "106")
    after1 = candle_at(peak.close_time, "106", "108", "105", "107")
    after2 = candle_at(after1.close_time, "107", "107", "104", "105")
    after3 = candle_at(after2.close_time, "105", "106", "103", "104")
    candles = [*padding, peak, after1, after2, after3]
    pattern = doji_pattern(after1.close_time, price="110")

    stepwise = evaluate_location(
        context_for(observed_at=after2.close_time + timedelta(seconds=1)), candles[:-1], pattern, ()
    )
    stepwise = evaluate_location(
        context_for(observed_at=candles[-1].close_time + timedelta(seconds=1)),
        candles,
        pattern,
        (),
        previous=stepwise,
    )

    replayed = evaluate_location(
        context_for(observed_at=candles[-1].close_time + timedelta(seconds=1)), candles, pattern, ()
    )
    replayed = evaluate_location(
        context_for(observed_at=candles[-1].close_time + timedelta(seconds=1)),
        candles,
        pattern,
        (),
        previous=replayed,
    )
    assert replayed.evaluations == stepwise.evaluations


# -- model and parameter validation --------------------------------------------------------------


def test_default_params_carry_their_version() -> None:
    assert DEFAULT_LOCATION_PARAMS.version == LOCATION_PARAMETER_VERSION


def test_a_ratio_outside_zero_one_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        LocationParams(max_distance_fraction=Decimal("0"))


def test_an_unversioned_params_set_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="version"):
        LocationParams(version="  ")


def test_evaluations_must_move_strictly_forward() -> None:
    pattern = doji_pattern(T0, price="110")
    early = LocationEvaluation(
        T0,
        T0,
        S.NOT_NEAR_LEVEL,
        evidence=(evidence("LEVELS_CHECKED", "0 checked", levels_checked=0),),
    )
    location = PatternLocation(pattern.candle_pattern_instance_id, (early,))
    same_instant = LocationEvaluation(
        T0,
        T0,
        S.NOT_NEAR_LEVEL,
        evidence=(evidence("LEVELS_CHECKED", "0 checked", levels_checked=0),),
    )
    with pytest.raises(InvalidDetectionRequestError, match="forward"):
        location.advance(same_instant)


def test_near_level_requires_a_level_evidence_item() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="LEVEL"):
        LocationEvaluation(T0, T0, S.NEAR_LEVEL)


def test_not_near_level_requires_a_levels_checked_evidence_item() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="LEVELS_CHECKED"):
        LocationEvaluation(T0, T0, S.NOT_NEAR_LEVEL)
