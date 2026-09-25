"""Provider-agnostic market-data contract: candle validity and series quality.

Pure and deterministic — every case fixes `now`, so nothing depends on the
wall clock.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from freyja_backend.domain.market_data import (
    Candle,
    CandleGap,
    DataQuality,
    InvalidMarketDataError,
    ProviderLimits,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    assess_candles,
    newest_expected_open,
    quality_from_issues,
)

# 12:07:30 UTC: the 12:05 five-minute candle is still open, 12:00 is closed.
NOW = datetime(2026, 9, 24, 12, 7, 30, tzinfo=UTC)
M5 = Timeframe.M5


def candle(open_time: datetime, timeframe: Timeframe = M5, price: str = "100") -> Candle:
    value = Decimal(price)
    return Candle(
        open_time=open_time,
        close_time=open_time + timeframe.duration,
        open=value,
        high=value + 1,
        low=value - 1,
        close=value,
        volume=Decimal("3"),
    )


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 24, hour, minute, tzinfo=UTC)


def codes(issues: tuple[QualityIssue, ...]) -> list[QualityIssueCode]:
    return [issue.code for issue in issues]


# -- Timeframe ---------------------------------------------------------------


def test_timeframe_durations_and_utc_grid() -> None:
    assert [tf.duration.total_seconds() for tf in Timeframe] == [60, 300, 900, 3600, 14400]
    assert Timeframe.M5.floor(NOW) == at(12, 5)
    assert Timeframe.H4.floor(NOW) == at(12, 0)
    assert Timeframe.H4.floor(at(15, 59)) == at(12, 0)


def test_timeframe_floor_rejects_naive_and_non_utc_moments() -> None:
    with pytest.raises(InvalidMarketDataError):
        Timeframe.M1.floor(datetime(2026, 9, 24, 12, 0))
    with pytest.raises(InvalidMarketDataError):
        Timeframe.M1.floor(datetime(2026, 9, 24, 12, 0, tzinfo=timezone(timedelta(hours=2))))


# -- Candle invariants -------------------------------------------------------


def test_candle_rejects_naive_timestamps() -> None:
    with pytest.raises(InvalidMarketDataError):
        Candle(
            datetime(2026, 9, 24, 12, 0),
            datetime(2026, 9, 24, 12, 5),
            Decimal(1),
            Decimal(1),
            Decimal(1),
            Decimal(1),
            Decimal(0),
        )


@pytest.mark.parametrize(
    ("open_", "high", "low", "close", "volume"),
    [
        ("100", "99", "98", "100", "1"),  # high below open
        ("100", "101", "102", "100", "1"),  # low above open
        ("0", "1", "0", "1", "1"),  # zero price
        ("-5", "1", "-5", "1", "1"),  # negative price
        ("NaN", "1", "1", "1", "1"),  # not finite
        ("100", "101", "99", "100", "-1"),  # negative volume
        ("100", "Infinity", "99", "100", "1"),
    ],
)
def test_candle_rejects_inconsistent_values(
    open_: str, high: str, low: str, close: str, volume: str
) -> None:
    with pytest.raises(InvalidMarketDataError):
        Candle(
            at(12, 0),
            at(12, 5),
            Decimal(open_),
            Decimal(high),
            Decimal(low),
            Decimal(close),
            Decimal(volume),
        )


def test_candle_rejects_close_not_after_open() -> None:
    with pytest.raises(InvalidMarketDataError):
        Candle(at(12, 5), at(12, 5), Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(0))


# -- Quality levels ----------------------------------------------------------


def test_quality_levels_come_from_issues() -> None:
    open_note = QualityIssue(QualityIssueCode.OPEN_CANDLE_EXCLUDED, "x")
    gap = QualityIssue(QualityIssueCode.GAP, "x")
    timeout = QualityIssue(QualityIssueCode.TIMEOUT, "x")
    assert quality_from_issues(()) is DataQuality.OK
    assert quality_from_issues((open_note,)) is DataQuality.OK
    assert quality_from_issues((open_note, gap)) is DataQuality.DEGRADED
    assert quality_from_issues((gap, timeout)) is DataQuality.UNAVAILABLE


# -- Closed vs open candles --------------------------------------------------


def test_clean_recent_series_has_no_issues() -> None:
    series = [candle(at(11, 55)), candle(at(12, 0))]
    result = assess_candles(series, timeframe=M5, now=NOW)
    assert result.candles == tuple(series)
    assert result.issues == ()


def test_candle_still_in_progress_is_never_returned_as_closed() -> None:
    series = [candle(at(11, 55)), candle(at(12, 0)), candle(at(12, 5))]  # 12:05 ends 12:10
    result = assess_candles(series, timeframe=M5, now=NOW)
    assert [c.open_time for c in result.candles] == [at(11, 55), at(12, 0)]
    assert codes(result.issues) == [QualityIssueCode.OPEN_CANDLE_EXCLUDED]
    assert quality_from_issues(result.issues) is DataQuality.OK  # informational only


def test_candle_is_closed_exactly_at_its_close_time() -> None:
    result = assess_candles([candle(at(12, 0))], timeframe=M5, now=at(12, 5))
    assert len(result.candles) == 1
    result = assess_candles([candle(at(12, 0))], timeframe=M5, now=at(12, 5) - timedelta(seconds=1))
    assert result.candles == ()


# -- Order, duplicates, gaps -------------------------------------------------


def test_out_of_order_candles_are_sorted_and_flagged() -> None:
    result = assess_candles(
        [candle(at(12, 0)), candle(at(11, 55)), candle(at(11, 50))], timeframe=M5, now=NOW
    )
    assert [c.open_time for c in result.candles] == [at(11, 50), at(11, 55), at(12, 0)]
    assert codes(result.issues) == [QualityIssueCode.OUT_OF_ORDER]


def test_identical_duplicates_are_dropped_and_flagged() -> None:
    result = assess_candles(
        [candle(at(11, 55)), candle(at(11, 55)), candle(at(12, 0))], timeframe=M5, now=NOW
    )
    assert [c.open_time for c in result.candles] == [at(11, 55), at(12, 0)]
    assert codes(result.issues) == [QualityIssueCode.DUPLICATE_DROPPED]


def test_conflicting_duplicates_are_invalid_not_repaired() -> None:
    with pytest.raises(InvalidMarketDataError, match="conflicting duplicates"):
        assess_candles(
            [candle(at(11, 55), price="100"), candle(at(11, 55), price="101")],
            timeframe=M5,
            now=NOW,
        )


def test_gap_between_candles_is_reported_with_its_size() -> None:
    result = assess_candles([candle(at(11, 45)), candle(at(12, 0))], timeframe=M5, now=NOW)
    assert codes(result.issues) == [QualityIssueCode.GAP]
    assert "2 candle(s) missing after 2026-09-24T11:45:00+00:00" in result.issues[0].detail
    assert len(result.candles) == 2  # real candles are kept, only flagged


# -- Grid and span validation ------------------------------------------------


def test_candle_off_the_timeframe_grid_is_invalid() -> None:
    off_grid = candle(at(12, 1))
    with pytest.raises(InvalidMarketDataError, match="off the 5m UTC grid"):
        assess_candles([off_grid], timeframe=M5, now=NOW)


def test_candle_with_the_wrong_span_is_invalid() -> None:
    one_minute_candle = candle(at(12, 0), Timeframe.M1)
    with pytest.raises(InvalidMarketDataError, match="does not span one 5m"):
        assess_candles([one_minute_candle], timeframe=M5, now=NOW)


# -- Freshness (recent mode) -------------------------------------------------


def test_old_data_is_never_presented_as_current() -> None:
    result = assess_candles([candle(at(10, 0))], timeframe=M5, now=NOW)
    assert codes(result.issues) == [QualityIssueCode.STALE]
    assert quality_from_issues(result.issues) is DataQuality.DEGRADED


def test_empty_recent_series_is_stale() -> None:
    result = assess_candles([], timeframe=M5, now=NOW)
    assert codes(result.issues) == [QualityIssueCode.STALE]
    assert "newest closed candle is none" in result.issues[0].detail


def test_candle_that_closed_within_the_publication_grace_may_be_missing() -> None:
    just_after_close = at(12, 5) + timedelta(seconds=3)  # 12:00 candle closed 3s ago
    result = assess_candles([candle(at(11, 55))], timeframe=M5, now=just_after_close)
    assert result.issues == ()
    later = at(12, 5) + timedelta(seconds=11)  # grace is over: 12:00 is now owed
    result = assess_candles([candle(at(11, 55))], timeframe=M5, now=later)
    assert codes(result.issues) == [QualityIssueCode.STALE]


# -- Historical windows ------------------------------------------------------


def test_complete_historical_window_is_clean_and_never_stale() -> None:
    series = [candle(at(9, 0)), candle(at(9, 5)), candle(at(9, 10))]
    result = assess_candles(series, timeframe=M5, now=NOW, start=at(9, 0), end=at(9, 15))
    assert result.issues == ()


def test_truncated_window_is_incomplete() -> None:
    series = [candle(at(9, 0)), candle(at(9, 5))]  # window owes up to 9:10
    result = assess_candles(series, timeframe=M5, now=NOW, start=at(9, 0), end=at(9, 15))
    assert codes(result.issues) == [QualityIssueCode.INCOMPLETE_RANGE]
    assert "expected candles 2026-09-24T09:00:00+00:00..2026-09-24T09:10:00+00:00" in (
        result.issues[0].detail
    )


def test_window_missing_its_head_is_incomplete() -> None:
    series = [candle(at(9, 5)), candle(at(9, 10))]
    result = assess_candles(series, timeframe=M5, now=NOW, start=at(9, 0), end=at(9, 15))
    assert codes(result.issues) == [QualityIssueCode.INCOMPLETE_RANGE]


def test_empty_window_that_owes_candles_is_incomplete() -> None:
    result = assess_candles([], timeframe=M5, now=NOW, start=at(9, 0), end=at(9, 15))
    assert codes(result.issues) == [QualityIssueCode.INCOMPLETE_RANGE]


def test_window_that_has_not_closed_yet_owes_nothing() -> None:
    result = assess_candles([], timeframe=M5, now=NOW, start=at(13, 0), end=at(14, 0))
    assert result.issues == ()


def test_unaligned_window_start_rounds_up_to_the_first_full_candle() -> None:
    series = [candle(at(9, 5)), candle(at(9, 10))]
    result = assess_candles(series, timeframe=M5, now=NOW, start=at(9, 1), end=at(9, 15))
    assert result.issues == ()


def test_start_without_end_is_judged_up_to_now() -> None:
    complete = [candle(at(11, 55)), candle(at(12, 0))]
    assert assess_candles(complete, timeframe=M5, now=NOW, start=at(11, 55)).issues == ()
    stale = assess_candles([candle(at(11, 55))], timeframe=M5, now=NOW, start=at(11, 55))
    assert codes(stale.issues) == [QualityIssueCode.INCOMPLETE_RANGE]


# -- Structured gaps, expected head, revisions ---------------------------------


def test_gaps_are_also_returned_as_structured_data() -> None:
    series = [candle(at(11, 30)), candle(at(11, 35)), candle(at(11, 50)), candle(at(12, 0))]
    result = assess_candles(series, timeframe=M5, now=NOW)
    assert result.gaps == (
        CandleGap(after=at(11, 35), missing=2),
        CandleGap(after=at(11, 50), missing=1),
    )
    assert codes(result.issues).count(QualityIssueCode.GAP) == 2


def test_a_series_without_gaps_has_none() -> None:
    result = assess_candles([candle(at(11, 55)), candle(at(12, 0))], timeframe=M5, now=NOW)
    assert result.gaps == ()


def test_newest_expected_open_is_the_last_bucket_closed_beyond_the_grace() -> None:
    assert newest_expected_open(M5, NOW) == at(12, 0)  # 12:05 is still open at 12:07:30
    assert newest_expected_open(M5, at(12, 5) + timedelta(seconds=3)) == at(11, 55)
    assert newest_expected_open(M5, at(12, 5) + timedelta(seconds=11)) == at(12, 0)
    assert newest_expected_open(Timeframe.H1, NOW) == at(11, 0)
    assert newest_expected_open(M5, at(12, 5), timedelta(0)) == at(12, 0)


def test_a_revised_candle_degrades_the_quality_without_failing_it() -> None:
    revised = QualityIssue(QualityIssueCode.REVISED_CANDLE, "x")
    assert quality_from_issues((revised,)) is DataQuality.DEGRADED


def test_no_data_is_unavailable_and_a_failing_provider_only_degrades() -> None:
    no_data = QualityIssue(QualityIssueCode.NO_DATA, "x")
    failing = QualityIssue(QualityIssueCode.PROVIDER_FAILING, "x")
    assert quality_from_issues((no_data,)) is DataQuality.UNAVAILABLE
    assert quality_from_issues((failing,)) is DataQuality.DEGRADED
    assert quality_from_issues((failing, no_data)) is DataQuality.UNAVAILABLE


# -- what a provider can serve (MARKET-DATA-KRAKEN-REST-001) --------------------------------


def test_provider_limits_default_to_no_history_limit() -> None:
    limits = ProviderLimits(max_candles_per_request=1000)
    assert (limits.max_candles_per_request, limits.history_candles) == (1000, None)


@pytest.mark.parametrize(("page", "history"), [(0, None), (-1, None), (10, 0), (10, -5)])
def test_provider_limits_reject_impossible_values(page: int, history: int | None) -> None:
    with pytest.raises(ValueError):
        ProviderLimits(max_candles_per_request=page, history_candles=history)
