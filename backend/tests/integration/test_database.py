import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from freyja_backend.core.database import (
    PostgresSettings,
    create_database_engine,
    get_postgres_settings,
)

REQUIRED_ENV_VARS = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


@pytest.mark.parametrize("missing_var", REQUIRED_ENV_VARS)
def test_missing_required_variable_fails_closed(
    missing_var: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {"POSTGRES_DB": "x", "POSTGRES_USER": "y", "POSTGRES_PASSWORD": "z"}
    del values[missing_var]

    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(ValidationError):
        PostgresSettings(_env_file=None)


def test_url_uses_psycopg_dialect() -> None:
    settings = get_postgres_settings()
    assert settings.url.drivername == "postgresql+psycopg"


def test_safe_url_hides_password() -> None:
    settings = get_postgres_settings()
    assert settings.postgres_password is not None
    assert settings.postgres_password not in settings.safe_url
    assert "***" in settings.safe_url


def test_engine_executes_select_1() -> None:
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        engine.dispose()


_FORBIDDEN_TABLE_NAME_SUBSTRINGS = ("order", "fill", "balance", "position")


def test_no_order_fill_balance_or_position_tables_exist(auth_test_engine: Engine) -> None:
    """POINT1-TEST-001: Point 1 is domain/catalog/capability/execution-
    context only — no productive order, fill, balance, or position data may
    exist anywhere in the schema. auth_* tables are exempt (a table named
    e.g. auth_password_reset_tokens legitimately contains "position"-free,
    unrelated text — checked explicitly below, not by substring)."""
    inspector = inspect(auth_test_engine)
    offenders = [
        table
        for table in inspector.get_table_names()
        if not table.startswith("auth_")
        and any(forbidden in table.lower() for forbidden in _FORBIDDEN_TABLE_NAME_SUBSTRINGS)
    ]
    assert offenders == [], (
        f"no productive order/fill/balance/position table may exist: {offenders}"
    )
