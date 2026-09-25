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


# The one exchange hostname each authorized adapter may contain: its own public
# market-data host, and nothing else (`www.kraken.com`, another exchange, ... still trip
# the guard above).
_OWN_PUBLIC_HOST = {
    "market_data/kraken_spot_rest.py": "api.kraken.com",
}


def _text_without_own_public_host(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    host = (
        _OWN_PUBLIC_HOST.get(path.relative_to(SRC_DIR / "infrastructure").as_posix())
        if (SRC_DIR / "infrastructure" in path.parents)
        else None
    )
    return text.replace(host, "") if host else text


# Adapters explicitly authorized so far. Adding a file here is a deliberate,
# reviewed act: each new provider adapter needs its own task and ADR.
_AUTHORIZED_INFRASTRUCTURE_FILES = frozenset(
    {
        "market_data/__init__.py",
        "market_data/binance_spot_rest.py",  # MARKET-DATA-BINANCE-REST-001
        "market_data/kraken_spot_rest.py",  # MARKET-DATA-KRAKEN-REST-001
    }
)


def test_no_real_broker_or_exchange_client_code_exists() -> None:
    """REAL execution remains suspended (CLAUDE.md POINT1 rules) — no source
    file may reference a real broker/exchange domain or hostname, and the
    infrastructure package (reserved for provider adapters) may only hold the
    adapters that a task has explicitly authorized."""
    offenders = [
        str(path)
        for path in _source_files(SRC_DIR)
        if _BROKER_DOMAIN_RE.search(_text_without_own_public_host(path))
    ]
    assert offenders == [], (
        f"no source file may reference a real broker/exchange domain: {offenders}"
    )

    infrastructure_dir = SRC_DIR / "infrastructure"
    found = {
        path.relative_to(infrastructure_dir).as_posix()
        for path in infrastructure_dir.rglob("*.py")
        if path.name != "__init__.py" or path.parent != infrastructure_dir
    }
    assert found == _AUTHORIZED_INFRASTRUCTURE_FILES, (
        "infrastructure/ may only contain explicitly authorized adapters — "
        f"unexpected: {sorted(found - _AUTHORIZED_INFRASTRUCTURE_FILES)}, "
        f"missing: {sorted(_AUTHORIZED_INFRASTRUCTURE_FILES - found)}"
    )


_BINANCE_ADAPTER = SRC_DIR / "infrastructure" / "market_data" / "binance_spot_rest.py"
_FORBIDDEN_ADAPTER_TOKENS = (
    "x-mbx-apikey",
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "signature",
    "hmac",
    "listenkey",
    "/api/v3/order",
    "/api/v3/account",
    "/sapi/",
    "/fapi/",
    "/dapi/",
    "wss://",
    "testnet",
)


def test_binance_adapter_is_public_read_only_and_credential_free() -> None:
    """The Binance adapter must stay a public market-data reader: no key
    material, signing, account/order/margin/futures endpoints, WebSocket or
    Testnet — those need their own authorized tasks (and REAL stays suspended)."""
    text = _BINANCE_ADAPTER.read_text(encoding="utf-8").lower()
    found = [token for token in _FORBIDDEN_ADAPTER_TOKENS if token in text]
    assert found == [], f"Binance adapter must not touch credentials or trading: {found}"


_KRAKEN_ADAPTER = SRC_DIR / "infrastructure" / "market_data" / "kraken_spot_rest.py"
_FORBIDDEN_KRAKEN_TOKENS = (
    "api-key",
    "api-sign",
    "api_key",
    "apikey",
    "secret",
    "signature",
    "hmac",
    "nonce",
    "/0/private",
    "addorder",
    "withdraw",
    "wss://",
    "ws.kraken",
    "futures.kraken",
)


def test_kraken_adapter_is_public_read_only_and_credential_free() -> None:
    """Same boundary as Binance's: public market data only. No key material, signing,
    private (account/order/funding) endpoints, WebSocket or futures — those need their own
    authorized tasks, and REAL stays suspended."""
    text = _KRAKEN_ADAPTER.read_text(encoding="utf-8").lower()
    found = [token for token in _FORBIDDEN_KRAKEN_TOKENS if token in text]
    assert found == [], f"Kraken adapter must not touch credentials or trading: {found}"


def test_kraken_adapter_only_ever_names_its_own_public_host() -> None:
    hosts = set(re.findall(r"[a-z0-9.-]+\.kraken\.com", _KRAKEN_ADAPTER.read_text("utf-8")))
    assert hosts == {"api.kraken.com"}


def test_domain_and_application_contracts_never_mention_the_provider() -> None:
    """Internal contracts must not carry provider types or names: each provider is
    confined to its adapter."""
    offenders = [
        str(path)
        for area in ("domain", "application", "dto", "repositories", "db")
        for path in _source_files(SRC_DIR / area)
        if any(name in path.read_text(encoding="utf-8").lower() for name in ("binance", "kraken"))
    ]
    assert offenders == [], f"provider names leaked into internal layers: {offenders}"
