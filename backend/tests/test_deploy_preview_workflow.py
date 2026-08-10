"""Structural checks on .github/workflows/deploy-preview.yml.

These are plain text/order assertions (no PyYAML dependency, none of which
this repo currently has) that encode the two properties DEPLOY-VERIFY-001
must not regress: migrations still run before any Render deploy is
attempted, and a Render deploy step is verified (not just triggered) for
both services exactly once.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-preview.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")


def _first_index(needle: str) -> int:
    index = WORKFLOW_TEXT.find(needle)
    assert index != -1, f"expected to find {needle!r} in {WORKFLOW_PATH}"
    return index


def test_neon_migration_step_exists_and_runs_before_either_render_deploy() -> None:
    migration_index = _first_index("Neon — apply Alembic migrations")
    verify_heads_index = _first_index("Neon — verify current revision matches heads")
    backend_deploy_index = _first_index("Deploy backend on Render")
    frontend_deploy_index = _first_index("Deploy frontend on Render")

    assert migration_index < verify_heads_index < backend_deploy_index < frontend_deploy_index


def test_render_deploy_script_is_invoked_exactly_once_per_service() -> None:
    assert WORKFLOW_TEXT.count("python scripts/render_deploy.py") == 2
    assert WORKFLOW_TEXT.count("--service-name backend") == 1
    assert WORKFLOW_TEXT.count("--service-name frontend") == 1


def test_each_deploy_step_pins_the_exact_triggering_commit() -> None:
    assert WORKFLOW_TEXT.count('--sha "${GITHUB_SHA}"') == 2


def test_deploy_steps_use_the_three_documented_render_secrets_and_no_others() -> None:
    assert "secrets.RENDER_API_KEY" in WORKFLOW_TEXT
    assert "secrets.RENDER_BACKEND_SERVICE_ID" in WORKFLOW_TEXT
    assert "secrets.RENDER_FRONTEND_SERVICE_ID" in WORKFLOW_TEXT
    assert "secrets.RENDER_BACKEND_DEPLOY_HOOK" in WORKFLOW_TEXT
    assert "secrets.RENDER_FRONTEND_DEPLOY_HOOK" in WORKFLOW_TEXT


def test_workflow_still_runs_only_on_manual_dispatch() -> None:
    assert "workflow_dispatch: {}" in WORKFLOW_TEXT
    assert "\non:\n  push" not in WORKFLOW_TEXT
    assert "\non:\n  pull_request" not in WORKFLOW_TEXT


def test_concurrency_still_queues_instead_of_silently_cancelling_a_run() -> None:
    assert "group: deploy-preview" in WORKFLOW_TEXT
    assert "cancel-in-progress: false" in WORKFLOW_TEXT


def test_no_curl_deploy_hook_call_treats_acceptance_as_completion() -> None:
    # The old implementation's bug: curl only proved Render *accepted* the
    # hook, never that the deploy finished (let alone finished on the right
    # commit). Guard against silently reintroducing that shape.
    assert "curl" not in WORKFLOW_TEXT
