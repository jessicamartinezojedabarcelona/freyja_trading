"""Makes the application's own log events visible (PLATFORM-LOGGING-001).

Uvicorn only configures its own loggers, so without this the root logger stays at WARNING
and every INFO event of the application (for example `candle_scan_finished`) is dropped
before it reaches Render's log stream. Only the `freyja_backend` logger tree is configured:
the root logger and third-party libraries keep their defaults, so their output does not
flood the logs.

What is logged is decided at each call site, never here. Events carry fixed names and small
structured fields (see the guard test in `tests/unit/test_architecture_guards.py`); nothing
that can hold a secret, a cookie, a token or an email address goes into `extra`.
"""

import logging
import sys
import time
from typing import IO

from freyja_backend.core.config import Settings

APP_LOGGER_NAME = "freyja_backend"

_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Attributes every LogRecord has by itself; anything else on a record came from `extra=`.
_RECORD_ATTRIBUTES = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class _StructuredFormatter(logging.Formatter):
    """`<UTC time> <LEVEL> <logger> <event> key=value ...`, with the traceback below."""

    @staticmethod
    def converter(seconds: float | None = None) -> time.struct_time:
        # Explicit UTC, never the host's local zone: the trailing "Z" in the date format is true.
        return time.gmtime(seconds)

    def __init__(self) -> None:
        super().__init__(_LINE_FORMAT, datefmt=_DATE_FORMAT)

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802 (stdlib name)
        line = super().formatMessage(record)
        fields = {
            key: value for key, value in record.__dict__.items() if key not in _RECORD_ATTRIBUTES
        }
        if not fields:
            return line
        # repr() escapes newlines, so a value can never forge a second log line.
        rendered = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
        return f"{line} {rendered}"


class _StdoutHandler(logging.StreamHandler[IO[str]]):
    """Writes to whatever `sys.stdout` is at emit time, not at construction time.

    A stream captured once at import would be a stale (or closed) file as soon as a test
    runner or a process manager swaps `sys.stdout`.
    """

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        self.setFormatter(_StructuredFormatter())

    @property
    def stream(self) -> IO[str]:  # type: ignore[override]
        return sys.stdout


def configure_logging(settings: Settings) -> None:
    """Send the application's log events to standard output at `settings.log_level`.

    Safe to call more than once (`create_app` runs it every time it builds an app): the
    handler is installed a single time and only the level follows the settings.
    """
    logger = logging.getLogger(APP_LOGGER_NAME)
    if not any(isinstance(handler, _StdoutHandler) for handler in logger.handlers):
        logger.addHandler(_StdoutHandler())
    logger.setLevel(settings.log_level)
