import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from freyja_backend.db.models import AuthUser, UserOrigin
from freyja_backend.scripts import create_owner

IDENTIFIER = "owner@example.test"
PASSWORD = "correct-horse-battery-staple"
SECOND_IDENTIFIER = "second-account@example.test"
SECOND_PASSWORD = "a-different-long-password"


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


def _provision(monkeypatch: pytest.MonkeyPatch, identifier: str, password: str) -> int:
    monkeypatch.setenv("FREYJA_OWNER_IDENTIFIER", identifier)
    monkeypatch.setenv("FREYJA_OWNER_PASSWORD", password)
    return create_owner.main()


def _stored_hash(engine: Engine, identifier: str) -> str:
    with engine.connect() as connection:
        return connection.execute(
            select(AuthUser.password_hash).where(AuthUser.identifier == identifier)
        ).scalar_one()


# AUTH-PRIVATE-ACCESS-001: the local script provisions any number of accounts,
# one per run, each with its own identifier and credentials.


def test_provisions_two_distinct_accounts(
    monkeypatch: pytest.MonkeyPatch, auth_test_engine: Engine
) -> None:
    assert _provision(monkeypatch, IDENTIFIER, PASSWORD) == 0
    assert _provision(monkeypatch, SECOND_IDENTIFIER, SECOND_PASSWORD) == 0

    with auth_test_engine.connect() as connection:
        rows = connection.execute(
            select(AuthUser.identifier, AuthUser.created_via, AuthUser.is_active).order_by(
                AuthUser.identifier
            )
        ).all()
    assert [row.identifier for row in rows] == [IDENTIFIER, SECOND_IDENTIFIER]
    assert {row.created_via for row in rows} == {UserOrigin.ADMIN_BOOTSTRAP}
    assert all(row.is_active for row in rows)
    assert _stored_hash(auth_test_engine, IDENTIFIER) != _stored_hash(
        auth_test_engine, SECOND_IDENTIFIER
    )


def test_duplicate_is_rejected_without_overwriting_the_existing_password(
    monkeypatch: pytest.MonkeyPatch,
    auth_test_engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _provision(monkeypatch, IDENTIFIER, PASSWORD) == 0
    original_hash = _stored_hash(auth_test_engine, IDENTIFIER)
    capsys.readouterr()

    assert _provision(monkeypatch, IDENTIFIER, SECOND_PASSWORD) == 1
    # Same identifier once normalized (case and surrounding whitespace).
    assert _provision(monkeypatch, f"  {IDENTIFIER.upper()} ", SECOND_PASSWORD) == 1

    assert _stored_hash(auth_test_engine, IDENTIFIER) == original_hash
    captured = capsys.readouterr()
    assert "Ya existe una cuenta con ese identificador" in captured.err
    assert SECOND_PASSWORD not in captured.out
    assert SECOND_PASSWORD not in captured.err
    with auth_test_engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(AuthUser)).scalar_one()
    assert count == 1
