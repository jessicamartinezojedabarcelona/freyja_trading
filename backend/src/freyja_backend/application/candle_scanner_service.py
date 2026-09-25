"""Runs the candle scanner in the background of a long-lived process.

The scanner itself is synchronous (SQLAlchemy sessions and blocking HTTP), so each pass
runs in a worker thread and the event loop stays free to serve requests. The service is
started and stopped by the application's lifespan, and never takes the application down:
a pass that fails is logged and retried after a growing pause.

It only makes progress while its process is running. On a host that puts the process to
sleep (Render Free), the next pass after waking catches up from what is stored.
"""

import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Protocol

from freyja_backend.application.candle_scanner import ScanOutcome, ScanReport

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 30
MAX_INTERVAL_SECONDS = 3600
_MAX_BACKOFF_SECONDS = 600.0
_QUIET_OUTCOMES = frozenset({ScanOutcome.UP_TO_DATE})
_FAILURE_OUTCOMES = frozenset(
    {
        ScanOutcome.PROVIDER_UNAVAILABLE,
        ScanOutcome.NOT_CONFIGURED,
        ScanOutcome.REJECTED,
        ScanOutcome.DATABASE_ERROR,
        ScanOutcome.COOLING_DOWN,
    }
)


class Scanner(Protocol):
    def scan_once(self) -> Sequence[ScanReport]: ...


class CandleScannerService:
    def __init__(
        self,
        scanner: Scanner,
        *,
        interval_seconds: float,
        on_close: Sequence[Callable[[], None]] = (),
    ) -> None:
        if not MIN_INTERVAL_SECONDS <= interval_seconds <= MAX_INTERVAL_SECONDS:
            raise ValueError(
                f"interval_seconds must be between {MIN_INTERVAL_SECONDS} and "
                f"{MAX_INTERVAL_SECONDS}"
            )
        self._scanner = scanner
        self._interval = interval_seconds
        self._on_close = tuple(on_close)
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin scanning in the background. Call from inside the running event loop."""
        if self._task is not None:
            raise RuntimeError("the scanner service was already started")
        self._task = asyncio.get_running_loop().create_task(self._run(), name="candle-scanner")

    async def stop(self, timeout: float = 20.0) -> None:
        """Ask the loop to end, wait for the pass in progress, then release resources."""
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout)
            except TimeoutError:
                logger.warning("candle_scanner_stop_timeout")
                self._task.cancel()
        for close in self._on_close:
            close()

    async def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                reports = await asyncio.to_thread(self._scanner.scan_once)
            except Exception:
                # `scan_once` reports every expected problem as an outcome, so anything
                # landing here is a bug. It is logged with its traceback and the loop
                # keeps going, because the alternative is a scanner that stops for good.
                failures += 1
                logger.exception("candle_scan_crashed")
                await self._pause(min(self._interval * 2**failures, _MAX_BACKOFF_SECONDS))
                continue
            failures = 0
            _log_summary(reports)
            await self._pause(self._interval)

    async def _pause(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            return


def _log_summary(reports: Sequence[ScanReport]) -> None:
    counts = Counter(report.outcome for report in reports)
    inserted = sum(report.inserted for report in reports)
    failed = [report for report in reports if report.outcome in _FAILURE_OUTCOMES]
    summary = {outcome.value: count for outcome, count in sorted(counts.items())}
    if failed:
        logger.warning(
            "candle_scan_finished",
            extra={"outcomes": summary, "inserted": inserted, "failed": len(failed)},
        )
    elif set(counts) - _QUIET_OUTCOMES:
        logger.info("candle_scan_finished", extra={"outcomes": summary, "inserted": inserted})
    else:
        logger.debug("candle_scan_finished", extra={"outcomes": summary})
