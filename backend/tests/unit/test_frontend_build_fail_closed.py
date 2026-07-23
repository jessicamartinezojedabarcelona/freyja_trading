import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_JSON = _REPO_ROOT / "frontend" / "package.json"
_GENERATOR_SCRIPT = _REPO_ROOT / "frontend" / "scripts" / "generate-production-environment.mjs"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_DEPLOY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "deploy-preview.yml"


def test_npm_build_script_runs_the_generator_before_ng_build() -> None:
    """`npm run build` must not be able to succeed without the generator
    running first — this is what actually makes every build fail-closed,
    including a plain `ng build` a developer or CI step might otherwise
    invoke expecting production behavior."""
    package = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))
    build_script = package["scripts"]["build"]
    assert "generate:prod-environment" in build_script
    assert "ng build" in build_script
    assert build_script.index("generate:prod-environment") < build_script.index("ng build")
    assert "&&" in build_script, "the generator must gate ng build, not just run alongside it"


def test_ci_production_build_step_injects_a_reserved_invalid_domain() -> None:
    """CI must supply FREYJA_BACKEND_URL as an env var for its own build
    step (RFC 2606 reserved .invalid domain — never a real or realistic-
    looking URL), not rely on any fallback baked into application code."""
    content = _CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"FREYJA_BACKEND_URL:\s*(\S+)", content)
    assert match is not None, "expected ci.yml to set FREYJA_BACKEND_URL for the build step"
    value = match.group(1)
    assert value.startswith("https://")
    assert value.rstrip("\"'").endswith(".invalid")


def test_generator_script_has_no_hardcoded_invalid_domain_fallback() -> None:
    """The .invalid domain is an *external* env var supplied by CI — the
    generator script itself must never default to it (or to any other
    value) when FREYJA_BACKEND_URL is missing; it must keep failing."""
    content = _GENERATOR_SCRIPT.read_text(encoding="utf-8")
    assert ".invalid" not in content
    assert "ci-build-check" not in content


def test_deploy_preview_workflow_has_no_frontend_production_build_step() -> None:
    """deploy-preview.yml's frontend quality gate stops at test:ci and never
    calls `npm run build` itself — the real production bundle is built by
    Render's own pipeline (render.yaml), which supplies the real
    FREYJA_BACKEND_URL via fromService. If a build step is ever added here,
    it would need the same .invalid treatment as ci.yml."""
    content = _DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "npm run build" not in content
