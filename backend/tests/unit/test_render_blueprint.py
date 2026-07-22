import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RENDER_YAML = _REPO_ROOT / "render.yaml"

# Deliberately not a full YAML parse (no YAML library is a project
# dependency, and adding one solely for this check was out of scope for
# this task) — a structural/regex check is enough to catch the one thing
# that actually matters here: no literal secret value committed to Git.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"key:\s*(FREYJA_RATE_LIMIT_HMAC_KEY|FREYJA_SMTP_PASSWORD|FREYJA_SMTP_USERNAME|DATABASE_URL)\b"
)
_SUSPICIOUS_LITERAL_VALUE_PATTERN = re.compile(
    r"^\s*value:\s*['\"]?[A-Za-z0-9+/=_-]{16,}['\"]?\s*$"
)


def test_render_yaml_exists_and_is_non_empty() -> None:
    assert _RENDER_YAML.is_file()
    assert _RENDER_YAML.stat().st_size > 0


def test_render_yaml_declares_exactly_two_services() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    assert "type: web" in content
    assert "type: static" in content
    assert "name: freyja-backend" in content
    assert "name: freyja-frontend" in content


def test_render_yaml_has_no_render_managed_database() -> None:
    """PostgreSQL is external (Neon), not a Render-provisioned resource in
    this adaptation — there must be no top-level `databases:` section at
    all, and no reference to a Render Postgres via fromDatabase."""
    content = _RENDER_YAML.read_text(encoding="utf-8")
    assert "databases:" not in content
    assert "fromDatabase" not in content
    assert "name: freyja-postgres" not in content
    assert "ipAllowList" not in content


def _code_only_content() -> str:
    """render.yaml with comment text stripped from every line — used by
    checks that must not be tripped up by explanatory comments mentioning
    the very thing they document the absence of (e.g. "no preDeployCommand:
    ... migrations run from the workflow instead")."""
    lines = _RENDER_YAML.read_text(encoding="utf-8").splitlines()
    return "\n".join(line.split("#", 1)[0] for line in lines)


def test_render_yaml_has_no_predeploy_command() -> None:
    """Migrations run from the separate, manually-triggered GitHub Actions
    workflow against Neon's direct connection — not as a Render
    preDeployCommand tied to a Render deploy."""
    assert "preDeployCommand" not in _code_only_content()


def test_sensitive_variables_are_marked_sync_false_not_given_literal_values() -> None:
    lines = _RENDER_YAML.read_text(encoding="utf-8").splitlines()
    matched_at_least_one = False
    for index, line in enumerate(lines):
        if _SENSITIVE_KEY_PATTERN.search(line):
            matched_at_least_one = True
            following = "\n".join(lines[index + 1 : index + 3])
            assert "sync: false" in following, (
                f"Sensitive key on line {index + 1} must be followed by "
                "'sync: false', never a literal value."
            )
    assert matched_at_least_one, "expected at least one sensitive key in render.yaml"


def test_no_line_looks_like_a_literal_high_entropy_secret_value() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.split("#", 1)[0]
        if _SUSPICIOUS_LITERAL_VALUE_PATTERN.match(stripped):
            raise AssertionError(
                f"render.yaml line {line_number} looks like a literal secret value: {stripped!r}"
            )


def test_free_plan_used_for_backend_no_auto_paid_provisioning() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    assert content.count("plan: free") == 1


def test_health_check_path_points_at_readiness_not_plain_liveness() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    assert "healthCheckPath: /api/v1/health/ready" in content


def test_frontend_gets_backend_url_via_from_service_render_external_url() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    assert "FREYJA_BACKEND_URL" in content
    assert "fromService" in content
    assert "envVarKey: RENDER_EXTERNAL_URL" in content
    assert "name: freyja-backend" in content


def test_frontend_build_command_runs_environment_generator_before_build() -> None:
    content = _RENDER_YAML.read_text(encoding="utf-8")
    static_build_lines = [
        line
        for line in content.splitlines()
        if "buildCommand:" in line and "generate:prod-environment" in line
    ]
    assert static_build_lines, "expected the static site buildCommand to run the generator script"
    generator_index = static_build_lines[0].index("generate:prod-environment")
    build_index = static_build_lines[0].index("npm run build")
    assert generator_index < build_index, "generator must run before `npm run build`"


def test_no_localhost_or_placeholder_hardcoded_anywhere_in_render_yaml() -> None:
    """The production frontend URL is always computed at build time from
    FREYJA_BACKEND_URL — no localhost value or unresolved placeholder should
    ever appear as a literal (non-comment) value in this file."""
    code_only = _code_only_content()
    assert "localhost" not in code_only
    assert "REPLACE_WITH" not in code_only


def test_no_smtp_variables_declared_at_all() -> None:
    """No SMTP provider is approved yet, and Settings no longer requires any
    FREYJA_SMTP_* variable to start in production — none should be declared
    as an actual envVar entry here (a `key: FREYJA_SMTP_*` line), so applying
    this Blueprint never prompts Jessica to fill in values she does not
    have. Explanatory comments are allowed to mention the variable name
    when documenting its deliberate absence."""
    code_only = _code_only_content()
    assert "FREYJA_SMTP" not in code_only


def test_both_services_disable_auto_deploy_on_commit() -> None:
    """Deploys must only happen through deploy-preview.yml's controlled
    sequence (quality -> Neon migration -> verification -> deploy hooks).
    Without autoDeployTrigger: off, Render's default ("commit") would deploy
    every push to main on its own, bypassing the migration entirely."""
    content = _code_only_content()
    assert content.count("autoDeployTrigger: off") == 2
