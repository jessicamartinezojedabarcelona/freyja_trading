"""Static guards for the scheduled candle-sync workflow.

The workflow writes to production PostgreSQL on a timer, so what it may touch
is pinned here: which secret it reads, that it runs only from `main`, that runs
never overlap, and that every action is pinned to a commit SHA.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "sync-candles.yml"


def _code_only() -> str:
    lines = _WORKFLOW.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        line.split(" #", 1)[0] if not line.lstrip().startswith("#") else "" for line in lines
    )


def test_runs_on_a_schedule_and_can_be_dispatched_by_hand() -> None:
    code = _code_only()
    assert re.search(r"^\s*schedule:\s*$", code, re.MULTILINE)
    assert re.search(r'cron:\s*"\*/5 \* \* \* \*"', code)
    assert "workflow_dispatch:" in code
    assert "pull_request" not in code
    assert re.search(r"^\s*push:\s*$", code, re.MULTILINE) is None


def test_runs_only_from_main() -> None:
    assert "if: github.ref == 'refs/heads/main'" in _code_only()


def test_uses_exactly_one_secret_the_neon_pooled_connection_string() -> None:
    secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", _code_only()))
    assert secrets == {"NEON_DATABASE_URL"}


def test_never_receives_broker_or_render_credentials() -> None:
    code = _code_only()
    for forbidden in ("RENDER_", "API_KEY", "DEPLOY_HOOK", "DIRECT_URL"):
        assert forbidden not in code


def test_permissions_are_read_only() -> None:
    match = re.search(r"^permissions:\n(\s+\S.*\n)+", _code_only(), re.MULTILINE)
    assert match is not None
    assert "contents: read" in match.group(0)
    assert "write" not in match.group(0)


def test_runs_never_overlap_and_are_never_cancelled_midway() -> None:
    code = _code_only()
    assert "group: sync-candles" in code
    assert "cancel-in-progress: false" in code


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    uses = re.findall(r"uses:\s*(\S+)", _WORKFLOW.read_text(encoding="utf-8"))
    assert uses, "expected at least one action"
    for reference in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", reference), reference


def test_installs_without_dev_dependencies_and_from_the_lockfile() -> None:
    assert "uv sync --locked --no-dev" in _code_only()


def test_syncs_only_catalog_series_and_fails_the_run_if_any_series_fails() -> None:
    code = _code_only()
    assert "for symbol in BTC/USDT ETH/USDT SOL/USDT XRP/USDT" in code
    assert "for timeframe in 1m 5m 15m 1h 4h" in code
    assert 'test "$failures" -eq 0' in code
