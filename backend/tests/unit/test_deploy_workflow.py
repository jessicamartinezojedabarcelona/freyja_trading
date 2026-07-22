import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "deploy-preview.yml"

_REQUIRED_SECRETS = (
    "NEON_DATABASE_URL",
    "NEON_DATABASE_DIRECT_URL",
    "RENDER_BACKEND_DEPLOY_HOOK",
    "RENDER_FRONTEND_DEPLOY_HOOK",
)

_SUSPICIOUS_LITERAL_VALUE_PATTERN = re.compile(
    r"^\s*value:\s*['\"]?[A-Za-z0-9+/=_-]{16,}['\"]?\s*$"
)


def _content() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _code_only_content() -> str:
    lines = _content().splitlines()
    return "\n".join(line.split("#", 1)[0] for line in lines)


def test_workflow_file_exists_and_is_non_empty() -> None:
    assert _WORKFLOW.is_file()
    assert _WORKFLOW.stat().st_size > 0


def test_trigger_is_workflow_dispatch_only() -> None:
    code_only = _code_only_content()
    assert "workflow_dispatch:" in code_only
    assert "pull_request:" not in code_only
    assert re.search(r"^\s*push:\s*$", code_only, re.MULTILINE) is None


def test_declares_a_concurrency_group_that_does_not_cancel_in_progress() -> None:
    code_only = _code_only_content()
    assert "concurrency:" in code_only
    assert "group: deploy-preview" in code_only
    assert "cancel-in-progress: false" in code_only


def test_permissions_are_read_only() -> None:
    code_only = _code_only_content()
    match = re.search(r"^permissions:\n(\s+\S.*\n)+", code_only, re.MULTILINE)
    assert match is not None, "expected a top-level permissions block"
    assert "contents: read" in match.group(0)
    assert "write" not in match.group(0)


def test_uses_preview_environment() -> None:
    assert "environment: preview" in _code_only_content()


def test_guards_against_running_on_a_ref_other_than_main() -> None:
    code_only = _code_only_content()
    assert "github.ref == 'refs/heads/main'" in code_only
    assert "refs/heads/main" in code_only


def test_references_all_four_required_secrets_by_exact_name() -> None:
    code_only = _code_only_content()
    for secret_name in _REQUIRED_SECRETS:
        assert f"secrets.{secret_name}" in code_only, f"expected secrets.{secret_name} to be used"


def test_migrates_neon_via_direct_url_before_triggering_deploy_hooks() -> None:
    code_only = _code_only_content()
    migrate_index = code_only.index("secrets.NEON_DATABASE_DIRECT_URL")
    backend_hook_index = code_only.index("secrets.RENDER_BACKEND_DEPLOY_HOOK")
    frontend_hook_index = code_only.index("secrets.RENDER_FRONTEND_DEPLOY_HOOK")
    assert migrate_index < backend_hook_index
    assert migrate_index < frontend_hook_index


def test_verifies_current_matches_heads_after_migration() -> None:
    code_only = _code_only_content()
    assert "alembic heads" in code_only
    assert "alembic current" in code_only
    assert "current_revision" in code_only
    assert "heads_revision" in code_only


def test_no_line_looks_like_a_literal_high_entropy_secret_value() -> None:
    for line_number, line in enumerate(_content().splitlines(), start=1):
        stripped = line.split("#", 1)[0]
        if _SUSPICIOUS_LITERAL_VALUE_PATTERN.match(stripped):
            raise AssertionError(
                f"deploy-preview.yml line {line_number} looks like a literal secret "
                f"value: {stripped!r}"
            )


def test_both_neon_migration_steps_set_pooled_and_direct_urls() -> None:
    """PostgresSettings requires DATABASE_URL (or the POSTGRES_* component
    fields) before migration_url is even accessible — DATABASE_DIRECT_URL
    alone cannot construct Settings. Both the 'apply' and 'verify' steps
    must therefore set both secrets, with migration_url still resolving to
    the direct connection because DATABASE_DIRECT_URL is present."""
    content = _content()
    # Split on step boundaries ("- name:") to inspect each Neon migration
    # step's own env block in isolation.
    steps = content.split("- name:")
    neon_migration_steps = [
        step
        for step in steps
        if "Neon" in step.splitlines()[0] and "alembic" in step and "reachable" not in step
    ]
    assert len(neon_migration_steps) == 2, "expected exactly the apply + verify Neon steps"
    for step in neon_migration_steps:
        assert "secrets.NEON_DATABASE_URL" in step
        assert "secrets.NEON_DATABASE_DIRECT_URL" in step


def test_deploy_hooks_pin_the_exact_validated_commit() -> None:
    """Deploy hooks must never deploy 'whatever is latest' — they deploy the
    exact commit this workflow run validated, via Render's documented `ref`
    query parameter appended to the hook URL, using GitHub's own
    GITHUB_SHA (no separate declaration needed — GitHub Actions provides it
    automatically to every step)."""
    code_only = _code_only_content()
    assert "&ref=${GITHUB_SHA}" in code_only or "&ref=$GITHUB_SHA" in code_only
    backend_hook_line = next(
        line for line in code_only.splitlines() if "RENDER_BACKEND_DEPLOY_HOOK}" in line
    )
    frontend_hook_line = next(
        line for line in code_only.splitlines() if "RENDER_FRONTEND_DEPLOY_HOOK}" in line
    )
    assert "ref=" in backend_hook_line
    assert "ref=" in frontend_hook_line


def test_readiness_check_step_declares_no_smtp_placeholders() -> None:
    """SMTP is no longer required for Settings to construct in production —
    no provider is approved yet, and this workflow's one-off connectivity
    check must not invent placeholder SMTP values it no longer needs."""
    content = _content()
    reachable_step = next(step for step in content.split("- name:") if "reachable" in step)
    assert "FREYJA_SMTP" not in reachable_step


def test_never_runs_pytest_or_migrations_against_neon_pooled_url_directly() -> None:
    """The quality-control phase (pytest, alembic upgrade for validation) runs
    only against the ephemeral CI Postgres service container — never against
    a Neon secret. Only the two Neon-specific steps below that phase should
    reference a NEON_* secret."""
    code_only = _code_only_content()
    ci_postgres_marker = "freyja_ci_ephemeral_5f3a9c2b"
    assert ci_postgres_marker in code_only
    first_neon_secret_index = min(
        code_only.index(f"secrets.{name}") for name in _REQUIRED_SECRETS if name.startswith("NEON")
    )
    last_ci_postgres_index = code_only.rindex(ci_postgres_marker)
    assert last_ci_postgres_index < first_neon_secret_index, (
        "expected all ephemeral-CI-Postgres steps to precede the first Neon-secret step"
    )
