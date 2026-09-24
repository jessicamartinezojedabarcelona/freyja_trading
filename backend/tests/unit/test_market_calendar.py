"""POINT2-CONTEXT-001: the Forex week, the sessions and daylight saving time.

Dates are real 2026 dates. Winter: New York is UTC-5 and London UTC+0. Summer:
UTC-4 and UTC+1. In between there are weeks where only one of them has changed.
"""

from datetime import UTC, datetime

import pytest

from freyja_backend.domain.market_calendar import (
    FOREX_CALENDAR_VERSION,
    MarketSchedule,
    MarketSession,
    forex_session_at,
    is_expected_open,
    is_forex_open,
    last_forex_close,
)
from freyja_backend.domain.market_data import InvalidMarketDataError


def utc(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


S = MarketSession


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        # Winter Wednesday (2026-01-14): London 08-17 UTC, New York 13-22 UTC.
        (utc(1, 14, 7, 59), S.ASIA),
        (utc(1, 14, 8, 0), S.LONDON),
        (utc(1, 14, 12, 59), S.LONDON),
        (utc(1, 14, 13, 0), S.OVERLAP_LONDON_NEW_YORK),
        (utc(1, 14, 16, 59), S.OVERLAP_LONDON_NEW_YORK),
        (utc(1, 14, 17, 0), S.NEW_YORK),
        (utc(1, 14, 21, 59), S.NEW_YORK),
        (utc(1, 14, 22, 0), S.ASIA),
        (utc(1, 14, 3, 0), S.ASIA),
        # Summer Wednesday (2026-07-15): London 07-16 UTC, New York 12-21 UTC.
        (utc(7, 15, 6, 59), S.ASIA),
        (utc(7, 15, 7, 0), S.LONDON),
        (utc(7, 15, 12, 0), S.OVERLAP_LONDON_NEW_YORK),
        (utc(7, 15, 16, 0), S.NEW_YORK),
        (utc(7, 15, 21, 0), S.ASIA),
        # 2026-03-18: the US is already on summer time, the UK is not yet, so the
        # overlap is five hours long (12-17 UTC) instead of four.
        (utc(3, 18, 11, 59), S.LONDON),
        (utc(3, 18, 12, 0), S.OVERLAP_LONDON_NEW_YORK),
        (utc(3, 18, 16, 59), S.OVERLAP_LONDON_NEW_YORK),
        (utc(3, 18, 17, 0), S.NEW_YORK),
    ],
)
def test_sessions_follow_the_local_clocks_of_london_and_new_york(
    instant: datetime, expected: MarketSession
) -> None:
    assert forex_session_at(instant) is expected


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        (utc(1, 16, 21, 59), True),  # Friday, winter: closes at 22:00 UTC
        (utc(1, 16, 22, 0), False),
        (utc(1, 17, 12, 0), False),  # Saturday
        (utc(1, 18, 21, 59), False),  # Sunday, before 22:00 UTC
        (utc(1, 18, 22, 0), True),  # Sunday, winter: opens at 22:00 UTC
        (utc(1, 19, 0, 0), True),  # Monday
        (utc(7, 17, 20, 59), True),  # Friday, summer: closes at 21:00 UTC
        (utc(7, 17, 21, 0), False),
        (utc(7, 19, 20, 59), False),  # Sunday, summer: opens at 21:00 UTC
        (utc(7, 19, 21, 0), True),
    ],
)
def test_the_week_runs_from_sunday_1700_to_friday_1700_new_york_time(
    instant: datetime, is_open: bool
) -> None:
    assert is_forex_open(instant) is is_open
    assert (forex_session_at(instant) is S.CLOSED) is (not is_open)


def test_the_weekly_open_moves_an_hour_when_the_us_changes_its_clocks() -> None:
    # The US springs forward on Sunday 2026-03-08 at 02:00 local time, so that very
    # evening the week opens at 21:00 UTC. The Friday before it closed at 22:00 UTC.
    assert is_forex_open(utc(3, 6, 21, 59)) is True
    assert is_forex_open(utc(3, 6, 22, 0)) is False
    assert is_forex_open(utc(3, 8, 20, 59)) is False
    assert is_forex_open(utc(3, 8, 21, 0)) is True


def test_every_open_instant_has_a_named_session_and_only_closed_ones_are_closed() -> None:
    step = 15
    for day in range(12, 20):  # a full week around 2026-01-14
        for minute_of_day in range(0, 24 * 60, step):
            instant = utc(1, day, minute_of_day // 60, minute_of_day % 60)
            session = forex_session_at(instant)
            assert (session is S.CLOSED) is (not is_forex_open(instant))


@pytest.mark.parametrize(
    ("instant", "close"),
    [
        (utc(1, 17, 12, 0), utc(1, 16, 22, 0)),  # Saturday -> the Friday just gone
        (utc(1, 18, 21, 0), utc(1, 16, 22, 0)),  # Sunday before the open
        (utc(1, 16, 22, 0), utc(1, 16, 22, 0)),  # exactly at the close
        (utc(1, 16, 21, 0), utc(1, 9, 22, 0)),  # still open: the close before that
        (utc(1, 14, 12, 0), utc(1, 9, 22, 0)),  # midweek
        (utc(7, 18, 8, 0), utc(7, 17, 21, 0)),  # summer close is an hour earlier
    ],
)
def test_last_forex_close(instant: datetime, close: datetime) -> None:
    assert last_forex_close(instant) == close


def test_crypto_is_always_open_and_a_broker_defined_schedule_is_unknown() -> None:
    assert is_expected_open(MarketSchedule.CONTINUOUS_24_7, utc(1, 17, 12, 0)) is True
    assert is_expected_open(MarketSchedule.FOREX_WEEKLY, utc(1, 17, 12, 0)) is False
    # Nothing is assumed about a broker's own hours (e.g. its OTC instruments).
    assert is_expected_open(MarketSchedule.BROKER_DEFINED, utc(1, 14, 12, 0)) is None


def test_instants_must_be_utc_aware() -> None:
    with pytest.raises(InvalidMarketDataError):
        is_forex_open(datetime(2026, 1, 14, 12, 0))
    with pytest.raises(InvalidMarketDataError):
        forex_session_at(datetime(2026, 1, 14, 12, 0))


def test_the_calendar_is_versioned() -> None:
    assert FOREX_CALENDAR_VERSION == "forex-sessions-v1"
