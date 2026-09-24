"""The background loop around the candle scanner, its settings and its lifespan wiring.

The loop is exercised with a scripted scanner (its own behaviour is covered against real
PostgreSQL in tests/integration/test_candle_scanner.py); here only the running, pausing,
crashing and stopping of the loop matter.
"""

import asyncio
import threading
from collections.abc import Callable, Sequence

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from freyja_backend import main as main_module
from freyja_backend.application import candle_scanner_service
from freyja_backend.application.candle_scanner import ScanOutcome, ScanReport, ScanTarget
from freyja_backend.application.candle_scanner_service import CandleScannerService
from freyja_backend.core.config import Settings
from freyja_backend.domain.market_data import InstrumentRef, Timeframe

TARGET = ScanTarget("SRC", InstrumentRef("CRYPTO", "SPOT", "BTC/USDT"), Timeframe.M1)
UP_TO_DATE = (ScanReport(TARGET, ScanOutcome.UP_TO_DATE),)


class ScriptedScanner:
    def __init__(self, *script: Sequence[ScanReport] | Exception) -> None:
        self._script = list(script)
        self.calls = 0
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def scan_once(self) -> Sequence[ScanReport]:
        self.calls += 1
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=5)
        outcome = self._script[min(self.calls, len(self._script)) - 1] if self._script else ()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _fast_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real minimum (30 s) is a product safeguard, not something a test should wait for.
    monkeypatch.setattr(candle_scanner_service, "MIN_INTERVAL_SECONDS", 0.01)


def run(coro: Callable[[], object]) -> None:
    asyncio.run(coro())  # type: ignore[arg-type]


async def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


# -- the loop ------------------------------------------------------------------------------


def test_it_scans_again_and_again_until_stopped() -> None:
    async def scenario() -> None:
        scanner = ScriptedScanner(UP_TO_DATE)
        service = CandleScannerService(scanner, interval_seconds=0.01)
        service.start()
        await wait_until(lambda: scanner.calls >= 3)
        assert service.running
        await service.stop()
        assert not service.running
        calls = scanner.calls
        await asyncio.sleep(0.05)
        assert scanner.calls == calls  # nothing runs after it was stopped

    run(scenario)


def test_stopping_during_the_pause_is_immediate() -> None:
    async def scenario() -> None:
        scanner = ScriptedScanner(UP_TO_DATE)
        service = CandleScannerService(scanner, interval_seconds=3600)  # a very long pause
        service.start()
        await wait_until(lambda: scanner.calls == 1)
        await asyncio.wait_for(service.stop(), timeout=2)  # does not sit out the hour

    run(scenario)


def test_stopping_waits_for_the_pass_in_progress_then_releases_resources() -> None:
    async def scenario() -> None:
        closed: list[str] = []
        scanner = ScriptedScanner(UP_TO_DATE)
        scanner.gate = threading.Event()
        service = CandleScannerService(
            scanner,
            interval_seconds=0.01,
            on_close=[lambda: closed.append("engine"), lambda: closed.append("client")],
        )
        service.start()
        await wait_until(scanner.started.is_set)

        stopping = asyncio.create_task(service.stop())
        await asyncio.sleep(0.05)
        assert not stopping.done()  # the pass is still running, so stop is still waiting
        assert closed == []  # and nothing was released under its feet

        scanner.gate.set()
        await asyncio.wait_for(stopping, timeout=3)
        assert closed == ["engine", "client"]

    run(scenario)


def test_a_crashing_pass_is_logged_and_the_loop_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        scanner = ScriptedScanner(RuntimeError("boom"), UP_TO_DATE)
        service = CandleScannerService(scanner, interval_seconds=0.01)
        service.start()
        await wait_until(lambda: scanner.calls >= 2)  # it came back after the crash
        assert service.running
        await service.stop()

    with caplog.at_level("ERROR"):
        run(scenario)

    crashed = [r for r in caplog.records if r.getMessage() == "candle_scan_crashed"]
    assert crashed
    assert crashed[0].exc_info is not None  # with its traceback


def test_a_pass_with_failures_is_reported_as_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    failed = (ScanReport(TARGET, ScanOutcome.PROVIDER_UNAVAILABLE),)

    async def scenario() -> None:
        scanner = ScriptedScanner(failed)
        service = CandleScannerService(scanner, interval_seconds=0.01)
        service.start()
        await wait_until(lambda: scanner.calls >= 1)
        await service.stop()

    with caplog.at_level("WARNING"):
        run(scenario)

    assert any(r.getMessage() == "candle_scan_finished" for r in caplog.records)


def test_it_cannot_be_started_twice() -> None:
    async def scenario() -> None:
        service = CandleScannerService(ScriptedScanner(UP_TO_DATE), interval_seconds=0.01)
        service.start()
        with pytest.raises(RuntimeError):
            service.start()
        await service.stop()

    run(scenario)


def test_the_interval_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candle_scanner_service, "MIN_INTERVAL_SECONDS", 30)
    with pytest.raises(ValueError, match="interval_seconds"):
        CandleScannerService(ScriptedScanner(), interval_seconds=29)
    with pytest.raises(ValueError, match="interval_seconds"):
        CandleScannerService(ScriptedScanner(), interval_seconds=3601)
    CandleScannerService(ScriptedScanner(), interval_seconds=30)


# -- settings ---------------------------------------------------------------------------------


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, environment="test", **values)  # type: ignore[arg-type]


def test_the_scanner_is_off_unless_explicitly_enabled() -> None:
    assert settings().candle_scanner_enabled is False


@pytest.mark.parametrize("seconds", [29, 3601, 0, -5])
def test_an_interval_outside_30_to_3600_seconds_is_rejected(seconds: int) -> None:
    with pytest.raises(ValidationError):
        settings(candle_scanner_interval_seconds=seconds)


def test_the_default_interval_is_a_minute() -> None:
    assert settings().candle_scanner_interval_seconds == 60


def test_sources_are_parsed_and_an_unknown_one_stops_a_scanner_that_is_enabled() -> None:
    assert settings(candle_scanner_sources=" binance , ").candle_scanner_sources_list == ["BINANCE"]
    with pytest.raises(ValidationError, match="fuente conocida"):
        settings(candle_scanner_enabled=True, candle_scanner_sources="BINANCE,NOWHERE")
    with pytest.raises(ValidationError, match="fuente conocida"):
        settings(candle_scanner_enabled=True, candle_scanner_sources="")
    # Disabled, the list is never used, so it is not policed.
    assert settings(candle_scanner_sources="NOWHERE").candle_scanner_enabled is False


# -- the application's lifespan ---------------------------------------------------------------


def test_the_lifespan_starts_nothing_when_the_scanner_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[Settings] = []
    monkeypatch.setattr(main_module, "build_candle_scanner_service", built.append)

    async def scenario() -> None:
        async with main_module._lifespan(settings())(FastAPI()):
            pass

    run(scenario)

    assert built == []


def test_the_lifespan_starts_the_scanner_with_the_app_and_stops_it_with_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    scanner = ScriptedScanner(UP_TO_DATE)
    service = CandleScannerService(
        scanner, interval_seconds=0.01, on_close=[lambda: events.append("closed")]
    )
    monkeypatch.setattr(main_module, "build_candle_scanner_service", lambda _s: service)

    async def scenario() -> None:
        async with main_module._lifespan(settings(candle_scanner_enabled=True))(FastAPI()):
            events.append("serving")
            await wait_until(lambda: scanner.calls >= 1)  # it is scanning while the app serves
            assert service.running
        events.append("stopped")

    run(scenario)

    assert events == ["serving", "closed", "stopped"]
    assert not service.running


def test_a_scanner_that_cannot_be_built_stops_the_startup_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_settings: Settings) -> CandleScannerService:
        raise ValueError("bad database url")

    monkeypatch.setattr(main_module, "build_candle_scanner_service", broken)

    async def scenario() -> None:
        async with main_module._lifespan(settings(candle_scanner_enabled=True))(FastAPI()):
            pytest.fail("the application must not start with a scanner that is enabled but broken")

    with pytest.raises(ValueError, match="bad database url"):
        run(scenario)
