"""PLATFORM-LOGGING-001: the application's own log events reach standard output.

Uvicorn configures only its own loggers, so before this the root logger sat at WARNING and
every INFO event of the application was dropped: the candle scanner ran in production and
its logs showed nothing. These tests use the real `logging` machinery and the real scanner
loop, and read what would actually be printed.
"""

import asyncio
import logging
import re
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from freyja_backend import main as main_module
from freyja_backend.application import candle_scanner_service
from freyja_backend.application.candle_scanner import ScanOutcome, ScanReport, ScanTarget
from freyja_backend.application.candle_scanner_service import CandleScannerService
from freyja_backend.core.config import Settings
from freyja_backend.core.logging_setup import APP_LOGGER_NAME, configure_logging
from freyja_backend.domain.market_data import InstrumentRef, Timeframe

TARGET = ScanTarget("SRC", InstrumentRef("CRYPTO", "SPOT", "BTC/USDT"), Timeframe.M1)
LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z (DEBUG|INFO|WARNING|ERROR) freyja_backend\.\S+ \S+"
)


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, environment="test", **values)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _isolated_app_logger() -> Iterator[None]:
    """The `freyja_backend` logger, put back exactly as found (other tests build apps too)."""
    logger = logging.getLogger(APP_LOGGER_NAME)
    saved_handlers, saved_level = list(logger.handlers), logger.level
    logger.handlers.clear()
    try:
        yield
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)


def printed(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.splitlines()


# -- the setting ---------------------------------------------------------------------------


def test_the_level_defaults_to_info_and_is_case_insensitive() -> None:
    assert settings().log_level == "INFO"
    assert settings(log_level="debug").log_level == "DEBUG"
    assert settings(log_level=" Warning ").log_level == "WARNING"


@pytest.mark.parametrize("value", ["", "verbose", "CRITICAL", "0"])
def test_an_unknown_level_is_rejected_at_startup(value: str) -> None:
    with pytest.raises(ValidationError):
        settings(log_level=value)


# -- configuring the logger ----------------------------------------------------------------


def test_configuring_twice_installs_one_handler_and_follows_the_latest_level() -> None:
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    configure_logging(settings(log_level="INFO"))
    configure_logging(settings(log_level="WARNING"))

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.WARNING


def test_only_the_application_loggers_are_configured() -> None:
    root_level = logging.getLogger().level
    configure_logging(settings())

    assert logging.getLogger().level == root_level
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_info_events_of_the_application_are_printed_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(settings(log_level="INFO"))

    logging.getLogger("freyja_backend.anything").info("something_happened")

    (line,) = printed(capsys)
    assert LINE.match(line), line
    assert line.endswith(" INFO freyja_backend.anything something_happened")


def test_events_below_the_configured_level_are_not_printed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(settings(log_level="WARNING"))
    log = logging.getLogger("freyja_backend.anything")

    log.info("too_quiet")
    log.debug("too_quiet_as_well")
    log.warning("loud_enough")

    (line,) = printed(capsys)
    assert line.endswith("loud_enough")


def test_the_handler_follows_a_replaced_stdout_instead_of_holding_the_first_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(settings())
    log = logging.getLogger("freyja_backend.anything")

    log.info("first")
    assert printed(capsys) != []
    log.info("second")  # capsys swapped sys.stdout in between; nothing may be lost or fail
    assert len(printed(capsys)) == 1


# -- what a line contains ------------------------------------------------------------------


def test_structured_fields_are_printed_as_sorted_key_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(settings())

    logging.getLogger("freyja_backend.anything").info(
        "candle_scan_finished", extra={"outcomes": {"SYNCED": 2}, "inserted": 7}
    )

    (line,) = printed(capsys)
    assert line.endswith("candle_scan_finished inserted=7 outcomes={'SYNCED': 2}")


def test_a_value_can_never_forge_a_second_log_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings())

    logging.getLogger("freyja_backend.anything").info(
        "event", extra={"series": "BTC\n2099-01-01T00:00:00Z ERROR forged line"}
    )

    (line,) = printed(capsys)  # exactly one line, the newline escaped
    assert "\\n" in line


def test_an_exception_prints_its_traceback_below_the_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(settings())

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("freyja_backend.anything").exception("candle_scan_crashed")

    lines = printed(capsys)
    assert lines[0].endswith("ERROR freyja_backend.anything candle_scan_crashed")
    assert lines[1] == "Traceback (most recent call last):"
    assert lines[-1] == "RuntimeError: boom"


def test_timestamps_are_utc(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings())

    logging.getLogger("freyja_backend.anything").info("event")

    (line,) = printed(capsys)
    assert line.split(" ", 1)[0].endswith("Z")


# -- the events that motivated it ----------------------------------------------------------


class SyncedOnce:
    """A scanner whose first pass brings in candles, as it does every minute in production."""

    def __init__(self) -> None:
        self.calls = 0

    def scan_once(self) -> tuple[ScanReport, ...]:
        self.calls += 1
        return (ScanReport(TARGET, ScanOutcome.SYNCED, inserted=3, requests=1),)


def test_a_scan_that_brings_candles_is_visible_in_the_logs(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact event whose absence left production unverifiable."""
    # The real minimum (30 s) is a product safeguard, not something a test should wait for.
    monkeypatch.setattr(candle_scanner_service, "MIN_INTERVAL_SECONDS", 0.01)
    configure_logging(settings())
    scanner = SyncedOnce()
    service = CandleScannerService(scanner, interval_seconds=0.01, on_close=[])

    async def scenario() -> None:
        service.start()
        for _ in range(400):
            if scanner.calls:
                break
            await asyncio.sleep(0.005)
        await service.stop()

    asyncio.run(scenario())

    finished = [line for line in printed(capsys) if "candle_scan_finished" in line]
    assert finished, "the scanner ran but nothing reached the log stream"
    assert " INFO freyja_backend.application.candle_scanner_service " in finished[0]
    assert finished[0].endswith("inserted=3 outcomes={'SYNCED': 1}")


def test_the_lifespan_reports_what_the_service_is_doing(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings())

    async def scenario() -> None:
        from fastapi import FastAPI

        async with main_module._lifespan(settings())(FastAPI()):
            pass

    asyncio.run(scenario())

    lines = printed(capsys)
    assert any("app_started environment='test' log_level='INFO'" in line for line in lines)
    assert any(line.endswith("candle_scanner_disabled") for line in lines)


def test_create_app_configures_logging() -> None:
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    assert app_logger.handlers == []

    main_module.create_app()

    assert len(app_logger.handlers) == 1
