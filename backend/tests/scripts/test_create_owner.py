import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from freyja_backend.db.models import AuthUser
from freyja_backend.scripts import create_owner

IDENTIFIER = "owner@example.test"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch: pytest.MonkeyPatch, auth_test_engine: Engine) -> None:
    monkeypatch.setattr(create_owner, "create_database_engine", lambda: auth_test_engine)
    # Prevent the script from disposing the shared session-scoped test engine.
    monkeypatch.setattr(auth_test_engine, "dispose", lambda: None)


def test_creates_owner_from_env_vars(
    monkeypatch: pytest.MonkeyPatch, auth_test_engine: Engine
) -> None:
    monkeypatch.setenv("FREYJA_OWNER_IDENTIFIER", IDENTIFIER)
    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", PASSWORD)

    exit_code = create_owner.main()

    assert exit_code == 0
    with auth_test_engine.connect() as connection:
        user = connection.execute(
            select(AuthUser.identifier).where(AuthUser.identifier == IDENTIFIER)
        ).scalar_one()
        assert user == IDENTIFIER


def test_second_run_fails_without_overwriting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREYJA_OWNER_IDENTIFIER", IDENTIFIER)
    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", PASSWORD)
    assert create_owner.main() == 0

    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", "a-completely-different-password")
    exit_code = create_owner.main()

    assert exit_code == 1


def test_rejects_short_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREYJA_OWNER_IDENTIFIER", IDENTIFIER)
    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", "too-short")

    exit_code = create_owner.main()

    assert exit_code == 1


def test_never_prints_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FREYJA_OWNER_IDENTIFIER", IDENTIFIER)
    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", PASSWORD)

    create_owner.main()

    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
