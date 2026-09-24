"""Trading calendars and Forex sessions (POINT2-CONTEXT-001).

Pure and free of I/O. Every instant is a timezone-aware UTC ``datetime``; the local
clocks of New York and London are used only to place the Forex week and the session
windows, so daylight-saving changes are handled by the IANA database and never by
hand-written offsets.

The sessions are a *convention*, not an official schedule (nobody publishes one for
the spot Forex market). That is why the calendar carries a version: any change to a
window or to the week's opening and closing bumps ``FOREX_CALENDAR_VERSION``.
"""

import enum
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from freyja_backend.domain.market_data import InvalidMarketDataError, _require_utc

FOREX_CALENDAR_VERSION = "forex-sessions-v1"

_NEW_YORK = ZoneInfo("America/New_York")
_LONDON = ZoneInfo("Europe/London")

# The Forex week runs from Sunday 17:00 to Friday 17:00, New York time.
_WEEK_BOUNDARY = time(17, 0)
_FRIDAY = 4
_SUNDAY = 6

# Local trading hours of the two centres that define the named sessions.
_LONDON_OPEN, _LONDON_CLOSE = time(8, 0), time(17, 0)
_NEW_YORK_OPEN, _NEW_YORK_CLOSE = time(8, 0), time(17, 0)


class MarketSchedule(enum.StrEnum):
    """When a market can be expected to publish candles."""

    # Trades around the clock, every day (crypto).
    CONTINUOUS_24_7 = "CONTINUOUS_24_7"
    # Spot Forex: Sunday 17:00 to Friday 17:00 New York time, with named sessions.
    FOREX_WEEKLY = "FOREX_WEEKLY"
    # The hours belong to the broker that quotes the instrument (e.g. its synthetic
    # OTC instruments). Nothing is assumed: until an adapter supplies them, the
    # schedule is unknown and any context built on it is insufficient.
    BROKER_DEFINED = "BROKER_DEFINED"


class MarketSession(enum.StrEnum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP_LONDON_NEW_YORK = "OVERLAP_LONDON_NEW_YORK"
    CLOSED = "CLOSED"


def is_forex_open(instant: datetime) -> bool:
    """True from Sunday 17:00 to Friday 17:00 New York time (start included, end excluded)."""
    _require_utc(instant, "instant")
    local = instant.astimezone(_NEW_YORK)
    weekday, clock = local.weekday(), local.time()
    if weekday < _FRIDAY:
        return True
    if weekday == _FRIDAY:
        return clock < _WEEK_BOUNDARY
    if weekday == _SUNDAY:
        return clock >= _WEEK_BOUNDARY
    return False  # Saturday


def forex_session_at(instant: datetime) -> MarketSession:
    """The Forex session at `instant`.

    London and New York are 08:00-17:00 local time. Where both are open it is the
    overlap. While the market is open and neither is, it is ASIA: the hours between
    New York's close and London's open, when Asia-Pacific trading leads. Outside the
    Forex week it is CLOSED.
    """
    if not is_forex_open(instant):
        return MarketSession.CLOSED
    in_london = _LONDON_OPEN <= instant.astimezone(_LONDON).time() < _LONDON_CLOSE
    in_new_york = _NEW_YORK_OPEN <= instant.astimezone(_NEW_YORK).time() < _NEW_YORK_CLOSE
    if in_london and in_new_york:
        return MarketSession.OVERLAP_LONDON_NEW_YORK
    if in_london:
        return MarketSession.LONDON
    if in_new_york:
        return MarketSession.NEW_YORK
    return MarketSession.ASIA


def last_forex_close(instant: datetime) -> datetime:
    """The most recent weekly close (Friday 17:00 New York) at or before `instant`."""
    _require_utc(instant, "instant")
    local_date = instant.astimezone(_NEW_YORK).date()
    for back in range(9):
        day = local_date - timedelta(days=back)
        if day.weekday() != _FRIDAY:
            continue
        close = datetime.combine(day, _WEEK_BOUNDARY, tzinfo=_NEW_YORK).astimezone(UTC)
        if close <= instant:
            return close
    raise InvalidMarketDataError("no weekly close found")  # unreachable: one Friday per week


def is_expected_open(schedule: MarketSchedule, instant: datetime) -> bool | None:
    """Whether candles are expected at `instant`; None when the schedule is unknown."""
    if schedule is MarketSchedule.CONTINUOUS_24_7:
        _require_utc(instant, "instant")
        return True
    if schedule is MarketSchedule.FOREX_WEEKLY:
        return is_forex_open(instant)
    return None
