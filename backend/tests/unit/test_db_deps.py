import pytest

from freyja_backend.db import deps as db_deps


def test_is_database_ready_returns_false_when_engine_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolving the engine (Settings construction) can fail before any
    connection is even attempted — a missing/malformed DATABASE_URL raises
    from pydantic, not from SQLAlchemy. is_database_ready() must still return
    False, never let that exception escape (see its docstring: "never
    raises")."""

    def _broken_default_engine() -> None:
        raise ValueError("simulated Settings construction failure")

    # The session-scoped `auth_test_engine` fixture (see conftest.py) sets a
    # real engine override for the whole test session — it must be cleared
    # here so is_database_ready() actually falls through to _default_engine()
    # instead of using that unrelated, healthy override. monkeypatch restores
    # the previous value automatically once this test ends.
    monkeypatch.setattr(db_deps, "_engine_override", None)
    monkeypatch.setattr(db_deps, "_default_engine", _broken_default_engine)

    assert db_deps.is_database_ready() is False
