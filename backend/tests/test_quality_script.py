import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import quality  # type: ignore[import-not-found]  # noqa: E402

SCRIPT_SOURCE = (REPO_ROOT / "scripts" / "quality.py").read_text(encoding="utf-8")
_REAL_RESOLVE_EXECUTABLE = quality._resolve_executable

_REAL_ALEMBIC_INFO_LINES = (
    "INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.\n"
    "INFO  [alembic.runtime.migration] Will assume transactional DDL.\n"
)


@pytest.fixture(autouse=True)
def _stub_resolve_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality, "_resolve_executable", lambda name: name)


# --- dispatch -----------------------------------------------------------


def test_no_args_runs_backend_and_frontend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(quality, "run_backend_checks", lambda: calls.append("backend"))
    monkeypatch.setattr(quality, "run_frontend_checks", lambda: calls.append("frontend"))

    exit_code = quality.main([])

    assert calls == ["backend", "frontend"]
    assert exit_code == 0


def test_all_flag_equivalent_to_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(quality, "run_backend_checks", lambda: calls.append("backend"))
    monkeypatch.setattr(quality, "run_frontend_checks", lambda: calls.append("frontend"))

    quality.main(["--all"])

    assert calls == ["backend", "frontend"]


def test_backend_flag_runs_only_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(quality, "run_backend_checks", lambda: calls.append("backend"))
    monkeypatch.setattr(quality, "run_frontend_checks", lambda: calls.append("frontend"))

    quality.main(["--backend"])

    assert calls == ["backend"]


def test_frontend_flag_runs_only_frontend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(quality, "run_backend_checks", lambda: calls.append("backend"))
    monkeypatch.setattr(quality, "run_frontend_checks", lambda: calls.append("frontend"))

    quality.main(["--frontend"])

    assert calls == ["frontend"]


def test_backend_and_frontend_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        quality.parse_args(["--backend", "--frontend"])


def test_all_and_backend_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        quality.parse_args(["--all", "--backend"])


# --- source-level safety checks -----------------------------------------


def test_no_shell_true_in_source() -> None:
    assert "shell=True" not in SCRIPT_SOURCE
    assert "shell = True" not in SCRIPT_SOURCE


def test_script_never_references_dotenv_or_environ() -> None:
    assert ".env" not in SCRIPT_SOURCE
    assert "os.environ" not in SCRIPT_SOURCE
    assert "getenv" not in SCRIPT_SOURCE


def test_log_prefixes_constant_removed() -> None:
    assert "_LOG_PREFIXES" not in SCRIPT_SOURCE


# --- run_command / run_command_capture -----------------------------------


def test_run_command_uses_list_and_explicit_cwd_no_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded: dict[str, object] = {}

    def fake_run(command: list[str], cwd: str, check: bool) -> subprocess.CompletedProcess[str]:
        recorded["command"] = command
        recorded["cwd"] = cwd
        recorded["check"] = check
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    returncode = quality.run_command(["echo", "hi"], tmp_path)

    assert returncode == 0
    assert isinstance(recorded["command"], list)
    assert recorded["command"] == ["echo", "hi"]
    assert recorded["cwd"] == str(tmp_path)
    assert recorded["check"] is False


def test_backend_checks_use_expected_cwd_and_canonical_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[list[str], Path]] = []

    def fake_run_command(command: list[str], cwd: Path) -> int:
        recorded.append((list(command), Path(cwd)))
        return 0

    def fake_run_command_capture(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        recorded.append((list(command), Path(cwd)))
        if command[:3] == ["docker", "compose", "ps"]:
            payload = json.dumps({"Service": "postgres", "Health": "healthy"})
            return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")
        if command[-1] in ("heads", "current"):
            return subprocess.CompletedProcess(
                command, 0, stdout="0007_seed_catalog_v1 (head)\n", stderr=""
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    quality.run_backend_checks()

    for command, cwd in recorded:
        if command[:2] == ["docker", "compose"]:
            assert cwd == quality.REPO_ROOT
        else:
            assert cwd == quality.BACKEND_DIR
        assert isinstance(command, list)

    joined = [" ".join(cmd) for cmd, _ in recorded]
    assert "uv sync --locked" in joined
    assert "uv run ruff format --check ." in joined
    assert "uv run ruff check ." in joined
    assert "uv run mypy src tests" in joined
    assert "uv run pytest" in joined
    assert "uv run alembic heads" in joined
    assert "uv run alembic current" in joined

    build_calls = [cmd for cmd, _ in recorded if cmd[:2] == ["uv", "build"]]
    assert len(build_calls) == 1
    out_dir = Path(build_calls[0][build_calls[0].index("--out-dir") + 1])
    assert not out_dir.is_relative_to(quality.REPO_ROOT)


def test_frontend_checks_use_expected_cwd_and_canonical_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[list[str], Path]] = []

    def fake_run_command(command: list[str], cwd: Path) -> int:
        recorded.append((list(command), Path(cwd)))
        return 0

    monkeypatch.setattr(quality, "run_command", fake_run_command)

    quality.run_frontend_checks()

    for command, cwd in recorded:
        assert cwd == quality.FRONTEND_DIR
        assert isinstance(command, list)

    joined = [" ".join(cmd) for cmd, _ in recorded]
    assert "npm ci" in joined
    assert "npm run format:check" in joined
    assert "npm run lint" in joined
    assert "npm run typecheck" in joined
    assert "npm run test:ci" in joined
    assert "npm run build" in joined


def test_resolve_executable_fails_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality.shutil, "which", lambda _name: None)

    with pytest.raises(quality.QualityCheckFailureError):
        _REAL_RESOLVE_EXECUTABLE("does-not-exist")


def test_resolve_executable_returns_resolved_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality.shutil, "which", lambda name: f"/resolved/{name}")

    assert _REAL_RESOLVE_EXECUTABLE("npm") == "/resolved/npm"


def test_stops_immediately_on_first_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def fake_run_command(command: list[str], _cwd: Path) -> int:
        recorded.append(list(command))
        if "check" in command and "ruff" in command:
            return 1
        return 0

    monkeypatch.setattr(quality, "run_command", fake_run_command)

    with pytest.raises(quality.QualityCheckFailureError) as excinfo:
        quality.run_backend_checks()

    assert excinfo.value.returncode == 1
    joined = [" ".join(cmd) for cmd in recorded]
    assert any("ruff check" in cmd for cmd in joined)
    assert not any("mypy" in cmd for cmd in joined)
    assert not any("pytest" in cmd for cmd in joined)


def test_main_stops_before_frontend_when_backend_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    frontend_called: list[bool] = []

    def fake_backend() -> None:
        raise quality.QualityCheckFailureError(5, "backend fallo")

    monkeypatch.setattr(quality, "run_backend_checks", fake_backend)
    monkeypatch.setattr(quality, "run_frontend_checks", lambda: frontend_called.append(True))

    exit_code = quality.main([])

    assert exit_code == 5
    assert frontend_called == []


# --- check_postgres_available: cardinality and health --------------------


def test_check_postgres_available_fails_closed_when_not_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"Service": "postgres", "Health": "starting"})

    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    with pytest.raises(quality.QualityCheckFailureError):
        quality.check_postgres_available()


def test_check_postgres_available_fails_closed_when_service_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    with pytest.raises(quality.QualityCheckFailureError):
        quality.check_postgres_available()


def test_check_postgres_available_fails_closed_when_two_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = "\n".join(
        [
            json.dumps({"Service": "postgres", "Health": "healthy"}),
            json.dumps({"Service": "postgres", "Health": "healthy"}),
        ]
    )

    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    with pytest.raises(quality.QualityCheckFailureError):
        quality.check_postgres_available()


def test_check_postgres_available_fails_closed_when_health_not_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"Service": "postgres", "Health": True})

    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    with pytest.raises(quality.QualityCheckFailureError):
        quality.check_postgres_available()


def test_check_postgres_available_passes_when_single_healthy_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"Service": "postgres", "Health": "healthy"})

    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    quality.check_postgres_available()


def test_check_postgres_available_fails_closed_on_nonempty_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"Service": "postgres", "Health": "healthy"})
    leaked = "some-unexpected-stderr-content"

    def fake_run_command(_command: list[str], _cwd: Path) -> int:
        return 0

    def fake_run_command_capture(
        command: list[str], _cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=payload, stderr=leaked)

    monkeypatch.setattr(quality, "run_command", fake_run_command)
    monkeypatch.setattr(quality, "run_command_capture", fake_run_command_capture)

    with pytest.raises(quality.QualityCheckFailureError) as excinfo:
        quality.check_postgres_available()

    assert leaked not in str(excinfo.value)


# --- validate_compose_ps_stderr -------------------------------------------


def test_validate_compose_ps_stderr_accepts_empty() -> None:
    quality.validate_compose_ps_stderr("")


def test_validate_compose_ps_stderr_accepts_whitespace_only() -> None:
    quality.validate_compose_ps_stderr("   \n  \n")


def test_validate_compose_ps_stderr_rejects_nonempty_and_hides_content() -> None:
    leaked = "top-secret-connection-detail"
    with pytest.raises(quality.QualityCheckFailureError) as excinfo:
        quality.validate_compose_ps_stderr(leaked)
    assert leaked not in str(excinfo.value)


# --- validate_alembic_stderr ------------------------------------------------


def test_validate_alembic_stderr_accepts_real_info_lines() -> None:
    quality.validate_alembic_stderr(_REAL_ALEMBIC_INFO_LINES)


def test_validate_alembic_stderr_accepts_empty() -> None:
    quality.validate_alembic_stderr("")


@pytest.mark.parametrize(
    "bad_stderr",
    [
        "WARNING  [alembic.runtime.migration] something happened\n",
        "ERROR  [alembic.runtime.migration] something broke\n",
        "some completely unrecognized stderr text\n",
    ],
)
def test_validate_alembic_stderr_rejects_unexpected_content(bad_stderr: str) -> None:
    with pytest.raises(quality.QualityCheckFailureError) as excinfo:
        quality.validate_alembic_stderr(bad_stderr)
    assert bad_stderr.strip() not in str(excinfo.value)


# --- validate_alembic_heads / validate_alembic_current ----------------------


def test_validate_alembic_heads_accepts_expected_single_head() -> None:
    quality.validate_alembic_heads("0007_seed_catalog_v1 (head)\n")


def test_validate_alembic_heads_accepts_with_real_info_noise() -> None:
    quality.validate_alembic_heads(_REAL_ALEMBIC_INFO_LINES + "0007_seed_catalog_v1 (head)\n")


def test_validate_alembic_heads_rejects_zero_heads() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_heads("\n")


def test_validate_alembic_heads_rejects_multiple_heads() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_heads("0001_initial (head)\n0002_other (head)\n")


def test_validate_alembic_heads_rejects_unexpected_revision() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_heads("9999_unexpected (head)\n")


def test_validate_alembic_heads_rejects_warning_plus_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_heads(
            "WARNING  [alembic.runtime.migration] uh oh\n0001_initial (head)\n"
        )


def test_validate_alembic_current_accepts_expected_single_head() -> None:
    quality.validate_alembic_current("0007_seed_catalog_v1 (head)\n")


def test_validate_alembic_current_accepts_with_real_info_noise() -> None:
    quality.validate_alembic_current(_REAL_ALEMBIC_INFO_LINES + "0007_seed_catalog_v1 (head)\n")


def test_validate_alembic_current_rejects_ambiguous_output() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current("")


def test_validate_alembic_current_rejects_wrong_revision() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current("0002_other (head)\n")


def test_validate_alembic_current_rejects_extra_line_before_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current("something unexpected\n0001_initial (head)\n")


def test_validate_alembic_current_rejects_extra_line_after_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current("0001_initial (head)\nsomething unexpected\n")


def test_validate_alembic_current_rejects_warning_plus_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current(
            "WARNING  [alembic.runtime.migration] uh oh\n0001_initial (head)\n"
        )


def test_validate_alembic_current_rejects_error_plus_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_current(
            "ERROR  [alembic.runtime.migration] broken\n0001_initial (head)\n"
        )


def test_validate_alembic_heads_rejects_error_plus_head() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality.validate_alembic_heads(
            "ERROR  [alembic.runtime.migration] broken\n0001_initial (head)\n"
        )


# --- _parse_compose_ps_json: fail-closed JSON typing ------------------------


def test_parse_compose_ps_json_accepts_single_object() -> None:
    payload = json.dumps({"Service": "postgres", "Health": "healthy"})
    result = quality._parse_compose_ps_json(payload)
    assert result == [{"Service": "postgres", "Health": "healthy"}]


def test_parse_compose_ps_json_accepts_list_of_objects() -> None:
    payload = json.dumps(
        [
            {"Service": "postgres", "Health": "healthy"},
            {"Service": "other", "Health": "healthy"},
        ]
    )
    result = quality._parse_compose_ps_json(payload)
    assert len(result) == 2


def test_parse_compose_ps_json_accepts_ndjson() -> None:
    payload = "\n".join(
        [
            json.dumps({"Service": "postgres", "Health": "healthy"}),
            json.dumps({"Service": "other", "Health": "healthy"}),
        ]
    )
    result = quality._parse_compose_ps_json(payload)
    assert len(result) == 2


def test_parse_compose_ps_json_accepts_empty_stdout() -> None:
    assert quality._parse_compose_ps_json("") == []
    assert quality._parse_compose_ps_json("   \n  ") == []


def test_parse_compose_ps_json_rejects_invalid_json_without_raw_traceback() -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality._parse_compose_ps_json("{not valid json, definitely not::")


@pytest.mark.parametrize(
    "scalar_payload",
    [
        json.dumps("just a string"),
        json.dumps(42),
        json.dumps(True),
        json.dumps(None),
    ],
)
def test_parse_compose_ps_json_rejects_top_level_scalars(scalar_payload: str) -> None:
    with pytest.raises(quality.QualityCheckFailureError):
        quality._parse_compose_ps_json(scalar_payload)


def test_parse_compose_ps_json_rejects_list_with_scalar_element() -> None:
    payload = json.dumps([{"Service": "postgres", "Health": "healthy"}, "oops"])
    with pytest.raises(quality.QualityCheckFailureError):
        quality._parse_compose_ps_json(payload)


def test_parse_compose_ps_json_rejects_ndjson_with_scalar_line() -> None:
    payload = "\n".join([json.dumps({"Service": "postgres", "Health": "healthy"}), "42"])
    with pytest.raises(quality.QualityCheckFailureError):
        quality._parse_compose_ps_json(payload)
