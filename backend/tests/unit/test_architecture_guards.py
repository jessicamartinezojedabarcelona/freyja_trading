"""POINT1-TEST-001: static architecture/security guards.

These scan the actual source tree rather than asserting behavior of a
specific module — they exist to catch a future regression (a mock leaking
into production code, a real broker client appearing, a test reading the
real .env) as soon as it lands, not to test business logic.
"""

import re
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "freyja_backend"
TESTS_DIR = Path(__file__).resolve().parents[1]

_THIS_FILE = Path(__file__).resolve()


def _source_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.resolve() != _THIS_FILE
    ]


def test_no_production_code_imports_test_only_tooling() -> None:
    """Production code (backend/src) must never import pytest, unittest.mock,
    or reference Mock/MagicMock/monkeypatch — those belong exclusively to
    the test suite."""
    forbidden_import_re = re.compile(
        r"^\s*(import|from)\s+(pytest|unittest\.mock|mock)\b", re.MULTILINE
    )
    forbidden_token_re = re.compile(r"\b(MagicMock|monkeypatch)\b")

    offenders = []
    for path in _source_files(SRC_DIR):
        text = path.read_text(encoding="utf-8")
        if forbidden_import_re.search(text) or forbidden_token_re.search(text):
            offenders.append(str(path))

    assert offenders == [], f"production code must never import test-only tooling: {offenders}"


def test_no_legacy_module_import_anywhere_in_source() -> None:
    """Freyja 2.0 vendors nothing from the legacy knowledge-audit repository
    (LEGACY-SRC-01, a separate private repo used only as a read-only design
    reference, never checked into freyja_trading) — no import statement in
    backend/src may reference a module path containing "legacy"."""
    legacy_import_re = re.compile(
        r"^\s*(import|from)\s+[\w.]*legacy[\w.]*", re.MULTILINE | re.IGNORECASE
    )

    offenders = [
        str(path)
        for path in _source_files(SRC_DIR)
        if legacy_import_re.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"no source file may import a legacy-named module: {offenders}"


def test_no_test_file_reads_the_real_env_file() -> None:
    """Isolation from the real .env is already proven behaviorally by
    test_config.py/test_database_settings.py (_env_file=None). This is the
    complementary static guard: no test file may literally open/read the
    repo's real .env (as opposed to .env.example, which carries no
    secrets)."""
    real_env_read_re = re.compile(r"""(open|read_text|read_bytes)\([^)]*['"]\.env['"]""")

    offenders = []
    for path in _source_files(TESTS_DIR):
        text = path.read_text(encoding="utf-8")
        if real_env_read_re.search(text):
            offenders.append(str(path))

    assert offenders == [], f"no test may directly read the real .env file: {offenders}"


_LOG_CALL_RE = re.compile(r"_?\w*logger\w*\.(debug|info|warning|error|critical|exception)\(")
_EXTRA_KWARG_RE = re.compile(r"extra\s*=\s*\{([^}]*)\}")
_FORBIDDEN_LOG_SUBSTRINGS = (
    "password",
    "session_hash",
    "cookie",
    "secret",
    "credential",
    "api_key",
    "apikey",
)


def test_logging_calls_never_log_raw_secrets_cookies_or_full_hashes() -> None:
    """Every logger.*(...) call's extra={...} payload (the actual structured
    data attached to the log line) is scanned for forbidden substrings —
    catching accidental logging of a raw password, session hash, cookie, or
    other credential-shaped value. The static event-name string itself (the
    call's first argument, e.g. "password_reset_completed") is intentionally
    NOT scanned — it is a fixed, searchable identifier, not logged data, and
    legitimately contains words like "password" as part of its slug."""
    offenders: list[str] = []
    for path in _source_files(SRC_DIR):
        text = path.read_text(encoding="utf-8")
        for log_match in _LOG_CALL_RE.finditer(text):
            snippet = text[log_match.start() : log_match.start() + 300]
            call_end = snippet.find(")\n")
            call_text = snippet[: call_end if call_end != -1 else len(snippet)]
            extra_match = _EXTRA_KWARG_RE.search(call_text)
            if extra_match is None:
                continue
            extra_text = extra_match.group(1).lower()
            offenders.extend(
                f"{path}: extra={{{extra_match.group(1).strip()}}} (matches {forbidden!r})"
                for forbidden in _FORBIDDEN_LOG_SUBSTRINGS
                if forbidden in extra_text
            )

    assert offenders == [], (
        f"logging call's extra payload looks like it logs a raw secret: {offenders}"
    )


_BROKER_DOMAIN_RE = re.compile(
    r"(binance\.com|coinbase\.com|kraken\.com|interactivebrokers\.com|oanda\.com|"
    r"alpaca\.markets|ig\.com|etoro\.com)",
    re.IGNORECASE,
)


def test_no_real_broker_or_exchange_client_code_exists() -> None:
    """REAL execution remains suspended (CLAUDE.md POINT1 rules) — no source
    file may reference a real broker/exchange domain or hostname, and the
    infrastructure package (reserved for future provider adapters) must
    remain empty."""
    offenders = [
        str(path)
        for path in _source_files(SRC_DIR)
        if _BROKER_DOMAIN_RE.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"no source file may reference a real broker/exchange domain: {offenders}"
    )

    infrastructure_dir = SRC_DIR / "infrastructure"
    non_init_files = [
        path for path in infrastructure_dir.rglob("*.py") if path.name != "__init__.py"
    ]
    assert non_init_files == [], (
        "infrastructure/ must stay empty until a real broker/exchange adapter is "
        f"explicitly authorized — found: {non_init_files}"
    )
