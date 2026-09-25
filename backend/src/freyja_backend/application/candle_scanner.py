"""Candle scanner: keeps the stored candle series up to date (MARKET-DATA-SCANNER-001).

One `scan_once` looks at every configured series and brings each one up to date:

* already current                      -> no request is made at all;
* a few candles behind (or empty)      -> one request for the latest candles;
* far behind (the service was asleep)  -> a bounded, page-by-page catch-up forward
  from the newest stored candle, so a sleeping host leaves no hole in the history.

Nothing is fetched twice in a way that matters: inserts are idempotent and a stored
candle is never rewritten (ADR 0003). Each series is handled in its own transaction
guarded by a PostgreSQL *transaction-level* advisory lock, which (unlike a session
lock) works behind a pooled connection: two scanners on the same database then never
fetch the same series at the same time.

Failures never stop the pass. A provider that answers badly is recorded by the sync
service (so the API can show it as failing); a database error ends the pass early
instead of hammering a database that is down.

A provider that says "too many requests" is not asked again: insisting is what turns a
temporary limit into an IP ban. The first RATE_LIMITED answer of a source puts the whole
source in a cooldown (2 minutes, doubling to 30 while it keeps saying so), during which none
of its series makes any request; when it ends, one series probes it. Other sources carry on.
"""

import enum
import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from freyja_backend.application import market_data_service
from freyja_backend.application.market_data_service import (
    DEFAULT_PAGE_LIMIT,
    MarketDataConfigurationError,
    MarketDataIntegrityError,
    SyncResult,
)
from freyja_backend.db.session import session_scope
from freyja_backend.domain.market_data import (
    CandleProvider,
    Clock,
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    QualityIssueCode,
    Timeframe,
    newest_expected_open,
    utc_now,
)

logger = logging.getLogger(__name__)

DEFAULT_RECENT_LIMIT = 500
# Most candles one pass will fetch for a single series while catching up. The rest is
# fetched by the next pass, which resumes from what is already stored.
DEFAULT_MAX_CATCHUP_CANDLES = 5_000
# How long a source that answered "too many requests" is left alone, by consecutive rate-limited
# probes: 2, 4, 8, 16 minutes, then 30 minutes for as long as it keeps saying so.
RATE_LIMIT_COOLDOWN_SECONDS = (120, 240, 480, 960, 1800)


@dataclass(frozen=True, slots=True)
class ScanTarget:
    """One stored series: a source, an instrument and a candle period."""

    source_code: str
    instrument: InstrumentRef
    timeframe: Timeframe

    @property
    def label(self) -> str:
        return f"{self.source_code} {self.instrument.symbol} {self.timeframe.value}"


class ScanOutcome(enum.StrEnum):
    UP_TO_DATE = "UP_TO_DATE"
    SYNCED = "SYNCED"
    # Caught up as far as this pass's budget allows; the next pass continues.
    PARTIAL = "PARTIAL"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    LOCKED_BY_ANOTHER = "LOCKED_BY_ANOTHER"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    # The provider's answer did not match what the catalog says; nothing was stored.
    REJECTED = "REJECTED"
    DATABASE_ERROR = "DATABASE_ERROR"
    # The pass ended early (database error) before reaching this series.
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    # Skipped without a request: the source asked us to stop for a while (rate limit).
    COOLING_DOWN = "COOLING_DOWN"


@dataclass(frozen=True, slots=True)
class ScanReport:
    target: ScanTarget
    outcome: ScanOutcome
    inserted: int = 0
    requests: int = 0
    detail: str | None = None


@dataclass(slots=True)
class _Cooldown:
    """A source that said "too many requests": left alone until `until`. `streak` counts the
    rate-limited answers in a row and sets how long the next cooldown is."""

    until: datetime
    streak: int


def advisory_lock_key(target: ScanTarget) -> int:
    """A stable signed 64-bit key for the series (what `pg_try_advisory_xact_lock` takes)."""
    digest = hashlib.blake2b(target.label.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class CandleScanner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        providers: Mapping[str, CandleProvider],
        targets: Sequence[ScanTarget],
        *,
        clock: Clock = utc_now,
        recent_limit: int = DEFAULT_RECENT_LIMIT,
        max_catchup_candles: int = DEFAULT_MAX_CATCHUP_CANDLES,
    ) -> None:
        if not 1 <= recent_limit <= DEFAULT_PAGE_LIMIT:
            raise ValueError(f"recent_limit must be between 1 and {DEFAULT_PAGE_LIMIT}")
        if max_catchup_candles < 1:
            raise ValueError("max_catchup_candles must be at least 1")
        self._session_factory = session_factory
        self._providers = providers
        self._targets = tuple(targets)
        self._clock = clock
        self._recent_limit = recent_limit
        self._max_catchup = max_catchup_candles
        self._cooldowns: dict[str, _Cooldown] = {}

    @property
    def targets(self) -> tuple[ScanTarget, ...]:
        return self._targets

    def scan_once(self) -> tuple[ScanReport, ...]:
        """One pass over every target, in order. Never raises for a data or provider problem."""
        reports: list[ScanReport] = []
        for index, target in enumerate(self._targets):
            report = self._scan_or_skip(target)
            reports.append(report)
            if report.outcome is ScanOutcome.DATABASE_ERROR:
                reports.extend(
                    ScanReport(later, ScanOutcome.NOT_ATTEMPTED)
                    for later in self._targets[index + 1 :]
                )
                break
        return tuple(reports)

    # -- a source that asked us to stop -----------------------------------------

    def _scan_or_skip(self, target: ScanTarget) -> ScanReport:
        """The series, unless its source is cooling down after a rate limit: then nothing is
        requested at all and the series is reported as skipped (its recorded state, which
        already says the last attempt failed, is left as it is)."""
        now = self._clock()
        cooldown = self._cooldowns.get(target.source_code)
        if cooldown is not None and now < cooldown.until:
            return ScanReport(
                target,
                ScanOutcome.COOLING_DOWN,
                detail=f"rate limited; not asked again before {cooldown.until.isoformat()}",
            )
        report = self._scan_target(target)
        self._note(target.source_code, report, now)
        return report

    def _note(self, source: str, report: ScanReport, now: datetime) -> None:
        """Open a cooldown on a rate-limited answer; close it once a request goes through.
        A series that made no request says nothing about the source."""
        if (
            report.outcome is ScanOutcome.PROVIDER_UNAVAILABLE
            and report.detail == QualityIssueCode.RATE_LIMITED.value
        ):
            previous = self._cooldowns.get(source)
            streak = 1 if previous is None else previous.streak + 1
            seconds = RATE_LIMIT_COOLDOWN_SECONDS[min(streak, len(RATE_LIMIT_COOLDOWN_SECONDS)) - 1]
            self._cooldowns[source] = _Cooldown(now + timedelta(seconds=seconds), streak)
            logger.warning(
                "candle_source_rate_limited",
                extra={"source": source, "cooldown_seconds": seconds, "streak": streak},
            )
        elif (
            report.outcome in (ScanOutcome.SYNCED, ScanOutcome.PARTIAL)
            and report.requests > 0
            and source in self._cooldowns
        ):
            del self._cooldowns[source]
            logger.info("candle_source_recovered", extra={"source": source})

    # -- one series ------------------------------------------------------------

    def _scan_target(self, target: ScanTarget) -> ScanReport:
        provider = self._providers.get(target.source_code)
        if provider is None:
            return ScanReport(
                target, ScanOutcome.NOT_CONFIGURED, detail="no provider for this source"
            )
        try:
            return self._bring_up_to_date(target, provider)
        except MarketDataConfigurationError as exc:
            return ScanReport(target, ScanOutcome.NOT_CONFIGURED, detail=str(exc))
        except (MarketDataIntegrityError, MarketDataRequestError) as exc:
            logger.warning("candle_scan_rejected", extra={"series": target.label})
            return ScanReport(target, ScanOutcome.REJECTED, detail=str(exc))
        except SQLAlchemyError as exc:
            logger.warning(
                "candle_scan_database_error",
                extra={"series": target.label, "error": type(exc).__name__},
            )
            return ScanReport(target, ScanOutcome.DATABASE_ERROR, detail=type(exc).__name__)

    def _bring_up_to_date(self, target: ScanTarget, provider: CandleProvider) -> ScanReport:
        step = target.timeframe.duration
        expected = newest_expected_open(target.timeframe, self._clock())
        latest = self._latest_stored(target)
        if latest is not None and latest >= expected:
            return ScanReport(target, ScanOutcome.UP_TO_DATE)

        limits = provider.limits
        recent = min(self._recent_limit, limits.max_candles_per_request)
        if latest is None:
            return self._fetch_recent(target, provider, limit=recent)
        missing = int((expected - latest) / step)
        if missing < recent:
            return self._fetch_recent(target, provider, limit=recent)
        first = latest + step
        if limits.history_candles is not None:
            # This provider only serves its most recent candles. Whatever is older cannot
            # be fetched from it, so catching up starts at the oldest reachable candle and
            # the skipped range stays a visible gap: never invented, never filled from
            # another source.
            first = max(first, expected - step * (limits.history_candles - 1))
        return self._catch_up(target, provider, first=first, last=expected)

    def _latest_stored(self, target: ScanTarget) -> datetime | None:
        with session_scope(self._session_factory) as session:
            return market_data_service.latest_open_time(
                session,
                source_code=target.source_code,
                instrument=target.instrument,
                timeframe=target.timeframe,
            )

    def _fetch_recent(
        self, target: ScanTarget, provider: CandleProvider, *, limit: int
    ) -> ScanReport:
        result = self._sync_page(target, provider, limit=limit)
        if result is None:
            return ScanReport(target, ScanOutcome.LOCKED_BY_ANOTHER)
        if result.quality is DataQuality.UNAVAILABLE:
            return ScanReport(
                target, ScanOutcome.PROVIDER_UNAVAILABLE, requests=1, detail=_first_issue(result)
            )
        return ScanReport(target, ScanOutcome.SYNCED, inserted=result.inserted, requests=1)

    def _catch_up(
        self, target: ScanTarget, provider: CandleProvider, *, first: datetime, last: datetime
    ) -> ScanReport:
        duration = target.timeframe.duration
        page = provider.limits.max_candles_per_request
        cursor, end = first, last + duration  # `end` is exclusive: it includes `last`
        inserted = requests = 0
        budget = self._max_catchup
        while cursor < end:
            page_end = min(end, cursor + duration * page)
            result = self._sync_page(target, provider, limit=page, start=cursor, end=page_end)
            if result is None:
                return ScanReport(
                    target, ScanOutcome.LOCKED_BY_ANOTHER, inserted=inserted, requests=requests
                )
            requests += 1
            if result.quality is DataQuality.UNAVAILABLE:
                return ScanReport(
                    target,
                    ScanOutcome.PROVIDER_UNAVAILABLE,
                    inserted=inserted,
                    requests=requests,
                    detail=_first_issue(result),
                )
            inserted += result.inserted
            cursor = page_end
            budget -= page
            if cursor < end and budget <= 0:
                return ScanReport(target, ScanOutcome.PARTIAL, inserted=inserted, requests=requests)
        return ScanReport(target, ScanOutcome.SYNCED, inserted=inserted, requests=requests)

    def _sync_page(
        self,
        target: ScanTarget,
        provider: CandleProvider,
        *,
        limit: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> SyncResult | None:
        """One provider request stored in one transaction, or None if another scanner
        holds this series. The lock lives exactly as long as the transaction."""
        with session_scope(self._session_factory) as session:
            if not _try_lock(session, target):
                session.rollback()
                return None
            result = market_data_service.sync_candles(
                session,
                provider,
                source_code=target.source_code,
                instrument=target.instrument,
                timeframe=target.timeframe,
                limit=limit,
                start=start,
                end=end,
            )
            session.commit()
            return result


def _try_lock(session: Session, target: ScanTarget) -> bool:
    return bool(
        session.execute(select(func.pg_try_advisory_xact_lock(advisory_lock_key(target)))).scalar()
    )


def _first_issue(result: SyncResult) -> str | None:
    return result.issues[0].code.value if result.issues else None
