from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import render_deploy  # type: ignore[import-not-found]  # noqa: E402

FAKE_HOOK_URL = "https://api.render.com/deploy/srv-fake?key=super-secret-hook-key"
FAKE_API_KEY = "rnd_super_secret_api_key_value"
FAKE_SERVICE_ID = "srv-fake0000000000000000"
EXPECTED_SHA = "a" * 40
OTHER_SHA = "b" * 40


class FakeClock:
    """Deterministic clock/sleep pair: sleep() advances the same clock time() reads."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += seconds


class FakePost:
    """Records every URL it is called with; never mutates real network state."""

    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body if isinstance(body, str) else json.dumps(body)
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        return self.status_code, self.body


class FakeGetSequence:
    """Returns each queued response in order, then keeps repeating the last one."""

    def __init__(self, responses: list[tuple[int, object]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def __call__(self, url: str, _api_key: str) -> tuple[int, str]:
        self.calls.append(url)
        status_code, body = (
            self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        )
        text = body if isinstance(body, str) else json.dumps(body)
        return status_code, text


# --- trigger_deploy: fires the hook exactly once, captures the deploy id ----


def test_trigger_deploy_posts_exactly_once_and_pins_the_ref() -> None:
    post = FakePost(200, {"deploy": {"id": "dep-abc123"}})

    deploy_id = render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)

    assert deploy_id == "dep-abc123"
    assert post.calls == [f"{FAKE_HOOK_URL}&ref={EXPECTED_SHA}"]


def test_trigger_deploy_accepts_the_flat_id_response_shape() -> None:
    post = FakePost(201, {"id": "dep-flat456"})

    deploy_id = render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)

    assert deploy_id == "dep-flat456"


def test_trigger_deploy_fails_when_response_has_no_verifiable_id() -> None:
    post = FakePost(202, {})

    with pytest.raises(render_deploy.RenderDeployError, match="ID de despliegue verificable"):
        render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)


def test_trigger_deploy_fails_on_non_2xx_status() -> None:
    post = FakePost(401, "")

    with pytest.raises(render_deploy.RenderDeployError, match="HTTP 401"):
        render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)


def test_trigger_deploy_fails_on_invalid_json() -> None:
    post = FakePost(200, "not json")

    with pytest.raises(render_deploy.RenderDeployError, match="JSON válido"):
        render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)


def test_trigger_deploy_requires_a_non_empty_sha() -> None:
    post = FakePost(200, {"id": "dep-x"})

    with pytest.raises(render_deploy.RenderDeployError, match="SHA de commit"):
        render_deploy.trigger_deploy(FAKE_HOOK_URL, "", http_post=post)

    assert post.calls == []


# --- fetch_deploy_status: read-only query against the official API ---------


def test_fetch_deploy_status_parses_status_and_commit_id() -> None:
    get = FakeGetSequence([(200, {"status": "live", "commit": {"id": EXPECTED_SHA}})])

    result = render_deploy.fetch_deploy_status(
        FAKE_SERVICE_ID, "dep-abc", FAKE_API_KEY, http_get=get
    )

    assert result == render_deploy.DeployStatus(
        deploy_id="dep-abc", status="live", commit_id=EXPECTED_SHA
    )


def test_fetch_deploy_status_fails_on_an_unexpected_non_200_status() -> None:
    get = FakeGetSequence([(500, "")])

    with pytest.raises(render_deploy.RenderDeployError, match="HTTP 500"):
        render_deploy.fetch_deploy_status(FAKE_SERVICE_ID, "dep-abc", FAKE_API_KEY, http_get=get)


@pytest.mark.parametrize("status_code", [401, 403])
def test_fetch_deploy_status_fails_immediately_on_401_or_403(status_code: int) -> None:
    get = FakeGetSequence([(status_code, "")])

    with pytest.raises(render_deploy.RenderDeployError, match=f"HTTP {status_code}"):
        render_deploy.fetch_deploy_status(FAKE_SERVICE_ID, "dep-abc", FAKE_API_KEY, http_get=get)


def test_fetch_deploy_status_raises_a_distinct_not_yet_visible_error_on_404() -> None:
    # 404 must never be silently treated as success, and must be
    # distinguishable from a definitive failure — only wait_for_live_deploy
    # is allowed to interpret it as "retry within the grace period".
    get = FakeGetSequence([(404, "")])

    with pytest.raises(render_deploy._DeployNotYetVisibleError):
        render_deploy.fetch_deploy_status(FAKE_SERVICE_ID, "dep-abc", FAKE_API_KEY, http_get=get)


# --- wait_for_live_deploy: success, SHA mismatch, failure statuses, timeout -


def test_wait_for_live_deploy_succeeds_when_live_and_sha_matches() -> None:
    get = FakeGetSequence([(200, {"status": "live", "commit": {"id": EXPECTED_SHA}})])
    clock = FakeClock()

    result = render_deploy.wait_for_live_deploy(
        FAKE_SERVICE_ID,
        "dep-abc",
        FAKE_API_KEY,
        EXPECTED_SHA,
        timeout_seconds=60,
        poll_interval_seconds=5,
        http_get=get,
        sleep=clock.sleep,
        now=clock.now,
    )

    assert result.status == "live"
    assert clock.sleep_calls == []


def test_wait_for_live_deploy_fails_when_live_on_an_unexpected_commit() -> None:
    get = FakeGetSequence([(200, {"status": "live", "commit": {"id": OTHER_SHA}})])
    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match="se esperaba"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=5,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )


@pytest.mark.parametrize(
    "failure_status",
    ["build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"],
)
def test_wait_for_live_deploy_fails_on_every_documented_terminal_failure_status(
    failure_status: str,
) -> None:
    get = FakeGetSequence([(200, {"status": failure_status, "commit": {"id": EXPECTED_SHA}})])
    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match="estado de fallo"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=5,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )


def test_wait_for_live_deploy_fails_on_an_unrecognized_status() -> None:
    get = FakeGetSequence([(200, {"status": "something_new_render_added", "commit": {}})])
    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match="no reconocido"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=5,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )


def test_wait_for_live_deploy_polls_at_the_given_interval_until_live() -> None:
    responses = [
        (200, {"status": "queued", "commit": {}}),
        (200, {"status": "build_in_progress", "commit": {}}),
        (200, {"status": "live", "commit": {"id": EXPECTED_SHA}}),
    ]
    remaining = list(responses)
    calls: list[str] = []

    def get(url: str, _api_key: str) -> tuple[int, str]:
        calls.append(url)
        status_code, body = remaining.pop(0)
        return status_code, json.dumps(body)

    clock = FakeClock()

    result = render_deploy.wait_for_live_deploy(
        FAKE_SERVICE_ID,
        "dep-abc",
        FAKE_API_KEY,
        EXPECTED_SHA,
        timeout_seconds=60,
        poll_interval_seconds=5,
        http_get=get,
        sleep=clock.sleep,
        now=clock.now,
    )

    assert result.status == "live"
    assert len(calls) == 3
    assert clock.sleep_calls == [5, 5]


def test_wait_for_live_deploy_times_out_without_ever_reaching_live() -> None:
    def get(_url: str, _api_key: str) -> tuple[int, str]:
        return 200, json.dumps({"status": "build_in_progress", "commit": {}})

    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match="Tiempo de espera agotado"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=20,
            poll_interval_seconds=5,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )


def test_wait_for_live_deploy_rejects_non_positive_timeout_or_interval() -> None:
    with pytest.raises(ValueError):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=0,
            poll_interval_seconds=5,
        )

    with pytest.raises(ValueError):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=0,
        )

    with pytest.raises(ValueError):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=5,
            visibility_timeout_seconds=0,
        )


# --- wait_for_live_deploy: transient 404s before Render indexes the deploy -


def test_wait_for_live_deploy_retries_through_a_transient_404_then_succeeds() -> None:
    get = FakeGetSequence(
        [
            (404, ""),
            (404, ""),
            (200, {"status": "live", "commit": {"id": EXPECTED_SHA}}),
        ]
    )
    clock = FakeClock()

    result = render_deploy.wait_for_live_deploy(
        FAKE_SERVICE_ID,
        "dep-abc",
        FAKE_API_KEY,
        EXPECTED_SHA,
        timeout_seconds=600,
        poll_interval_seconds=15,
        http_get=get,
        sleep=clock.sleep,
        now=clock.now,
    )

    assert result.status == "live"
    assert len(get.calls) == 3
    assert clock.sleep_calls == [15, 15]


def test_wait_for_live_deploy_fails_once_404_persists_beyond_the_visibility_grace_period() -> None:
    def get(_url: str, _api_key: str) -> tuple[int, str]:
        return 404, ""

    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match="HTTP 404"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=600,
            poll_interval_seconds=15,
            visibility_timeout_seconds=60,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )

    # never gave up before the full, documented 60s grace period elapsed —
    # and never anywhere near the unrelated 600s overall timeout either.
    assert clock.now() >= 60
    assert clock.now() < 600


def test_wait_for_live_deploy_never_lets_a_persistent_404_masquerade_as_success() -> None:
    def get(_url: str, _api_key: str) -> tuple[int, str]:
        return 404, ""

    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=600,
            poll_interval_seconds=15,
            visibility_timeout_seconds=60,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )


@pytest.mark.parametrize("status_code", [401, 403])
def test_wait_for_live_deploy_fails_immediately_on_401_or_403_without_retrying(
    status_code: int,
) -> None:
    get = FakeGetSequence([(status_code, "")])
    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError, match=f"HTTP {status_code}"):
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=600,
            poll_interval_seconds=15,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )

    assert len(get.calls) == 1
    assert clock.sleep_calls == []


# --- verify_deploy: end-to-end, exactly one trigger even across many polls -


def test_verify_deploy_triggers_exactly_once_even_across_multiple_polls() -> None:
    post = FakePost(200, {"deploy": {"id": "dep-once"}})

    responses = [
        (200, {"status": "queued", "commit": {}}),
        (200, {"status": "live", "commit": {"id": EXPECTED_SHA}}),
    ]
    remaining = list(responses)
    get_calls: list[str] = []

    def get(url: str, _api_key: str) -> tuple[int, str]:
        get_calls.append(url)
        status_code, body = remaining.pop(0)
        return status_code, json.dumps(body)

    clock = FakeClock()

    result = render_deploy.verify_deploy(
        hook_url=FAKE_HOOK_URL,
        service_id=FAKE_SERVICE_ID,
        api_key=FAKE_API_KEY,
        sha=EXPECTED_SHA,
        timeout_seconds=60,
        poll_interval_seconds=5,
        http_post=post,
        http_get=get,
        sleep=clock.sleep,
        now=clock.now,
    )

    assert result.deploy_id == "dep-once"
    assert len(post.calls) == 1
    assert len(get_calls) == 2


def test_verify_deploy_never_re_triggers_after_a_failure_status() -> None:
    post = FakePost(200, {"deploy": {"id": "dep-once"}})
    get = FakeGetSequence([(200, {"status": "build_failed", "commit": {}})])

    with pytest.raises(render_deploy.RenderDeployError):
        render_deploy.verify_deploy(
            hook_url=FAKE_HOOK_URL,
            service_id=FAKE_SERVICE_ID,
            api_key=FAKE_API_KEY,
            sha=EXPECTED_SHA,
            timeout_seconds=60,
            poll_interval_seconds=5,
            http_post=post,
            http_get=get,
        )

    assert len(post.calls) == 1


def test_verify_deploy_triggers_exactly_once_even_with_several_transient_404s() -> None:
    post = FakePost(200, {"deploy": {"id": "dep-once"}})
    get = FakeGetSequence(
        [
            (404, ""),
            (404, ""),
            (200, {"status": "live", "commit": {"id": EXPECTED_SHA}}),
        ]
    )
    clock = FakeClock()

    result = render_deploy.verify_deploy(
        hook_url=FAKE_HOOK_URL,
        service_id=FAKE_SERVICE_ID,
        api_key=FAKE_API_KEY,
        sha=EXPECTED_SHA,
        timeout_seconds=600,
        poll_interval_seconds=15,
        http_post=post,
        http_get=get,
        sleep=clock.sleep,
        now=clock.now,
    )

    assert result.deploy_id == "dep-once"
    assert len(post.calls) == 1
    assert len(get.calls) == 3


# --- secrets never leak into error messages or stdout/stderr ---------------


def test_error_messages_never_contain_the_hook_url_or_the_api_key() -> None:
    post = FakePost(401, "")

    with pytest.raises(render_deploy.RenderDeployError) as excinfo:
        render_deploy.trigger_deploy(FAKE_HOOK_URL, EXPECTED_SHA, http_post=post)

    assert FAKE_HOOK_URL not in str(excinfo.value)
    assert "super-secret-hook-key" not in str(excinfo.value)


def test_persistent_404_error_message_never_contains_the_api_key() -> None:
    def get(_url: str, _api_key: str) -> tuple[int, str]:
        return 404, ""

    clock = FakeClock()

    with pytest.raises(render_deploy.RenderDeployError) as excinfo:
        render_deploy.wait_for_live_deploy(
            FAKE_SERVICE_ID,
            "dep-abc",
            FAKE_API_KEY,
            EXPECTED_SHA,
            timeout_seconds=600,
            poll_interval_seconds=15,
            visibility_timeout_seconds=60,
            http_get=get,
            sleep=clock.sleep,
            now=clock.now,
        )

    assert FAKE_API_KEY not in str(excinfo.value)


def test_main_success_path_prints_no_secret_and_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FAKE_HOOK", FAKE_HOOK_URL)
    monkeypatch.setenv("FAKE_SERVICE_ID", FAKE_SERVICE_ID)
    monkeypatch.setenv("FAKE_API_KEY", FAKE_API_KEY)

    def fake_verify_deploy(**kwargs: object) -> render_deploy.DeployStatus:
        assert kwargs["hook_url"] == FAKE_HOOK_URL
        assert kwargs["api_key"] == FAKE_API_KEY
        return render_deploy.DeployStatus(deploy_id="dep-ok", status="live", commit_id=EXPECTED_SHA)

    monkeypatch.setattr(render_deploy, "verify_deploy", fake_verify_deploy)

    exit_code = render_deploy.main(
        [
            "--service-name",
            "backend",
            "--hook-url-env",
            "FAKE_HOOK",
            "--service-id-env",
            "FAKE_SERVICE_ID",
            "--api-key-env",
            "FAKE_API_KEY",
            "--sha",
            EXPECTED_SHA,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OK" in captured.out
    assert FAKE_HOOK_URL not in captured.out
    assert FAKE_API_KEY not in captured.out
    assert FAKE_HOOK_URL not in captured.err
    assert FAKE_API_KEY not in captured.err


def test_main_failure_path_prints_no_secret_and_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FAKE_HOOK", FAKE_HOOK_URL)
    monkeypatch.setenv("FAKE_SERVICE_ID", FAKE_SERVICE_ID)
    monkeypatch.setenv("FAKE_API_KEY", FAKE_API_KEY)

    def fake_verify_deploy(**_kwargs: object) -> render_deploy.DeployStatus:
        raise render_deploy.RenderDeployError("el despliegue dep-bad terminó en 'build_failed'")

    monkeypatch.setattr(render_deploy, "verify_deploy", fake_verify_deploy)

    exit_code = render_deploy.main(
        [
            "--service-name",
            "frontend",
            "--hook-url-env",
            "FAKE_HOOK",
            "--service-id-env",
            "FAKE_SERVICE_ID",
            "--api-key-env",
            "FAKE_API_KEY",
            "--sha",
            EXPECTED_SHA,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "FALLO" in captured.err
    assert FAKE_HOOK_URL not in captured.out
    assert FAKE_API_KEY not in captured.out
    assert FAKE_HOOK_URL not in captured.err
    assert FAKE_API_KEY not in captured.err


def test_main_fails_fast_when_required_env_vars_are_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MISSING_HOOK", raising=False)
    monkeypatch.delenv("MISSING_SERVICE_ID", raising=False)
    monkeypatch.delenv("MISSING_API_KEY", raising=False)

    exit_code = render_deploy.main(
        [
            "--service-name",
            "backend",
            "--hook-url-env",
            "MISSING_HOOK",
            "--service-id-env",
            "MISSING_SERVICE_ID",
            "--api-key-env",
            "MISSING_API_KEY",
            "--sha",
            EXPECTED_SHA,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "MISSING_HOOK" in captured.err
