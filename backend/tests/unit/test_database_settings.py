import pytest
from pydantic import ValidationError

from freyja_backend.core.database import PostgresSettings

_POSTGRES_ENV_KEYS = (
    "DATABASE_URL",
    "DATABASE_DIRECT_URL",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_SSLMODE",
)


def _settings(**init_kwargs: object) -> PostgresSettings:
    # _env_file=None is the real isolation mechanism: it disables pydantic-
    # settings' dotenv source for this instantiation entirely, so this
    # repo's actual local .env file (which defines real POSTGRES_DB/USER/
    # PASSWORD for local development) is never consulted, regardless of
    # what each individual test does or doesn't set in the process
    # environment. Overriding with empty strings is NOT equivalent — it
    # only masks the keys a test happens to touch, not the ones it doesn't.
    return PostgresSettings(_env_file=None, **init_kwargs)  # type: ignore[arg-type]


def _clear_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _POSTGRES_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_requires_either_database_url_or_component_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    with pytest.raises(ValidationError):
        _settings()


def test_component_variables_build_a_psycopg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_DB", "freyja")
    monkeypatch.setenv("POSTGRES_USER", "freyja_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-local-password")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    settings = _settings()

    assert settings.url.drivername == "postgresql+psycopg"
    assert settings.url.database == "freyja"
    assert settings.url.host == "127.0.0.1"
    # The rendered safe form never includes the password.
    assert "a-local-password" not in settings.safe_url


def test_database_url_takes_precedence_over_component_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://render_user:render_pass@internal-host/render_db?sslmode=require",
    )
    monkeypatch.setenv("POSTGRES_DB", "should_be_ignored")
    monkeypatch.setenv("POSTGRES_USER", "should_be_ignored")
    monkeypatch.setenv("POSTGRES_PASSWORD", "should_be_ignored")

    settings = _settings()

    assert settings.url.database == "render_db"
    assert settings.url.host == "internal-host"
    assert settings.url.username == "render_user"


def test_database_url_is_normalized_to_the_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/db?sslmode=require")

    settings = _settings()

    # A bare "postgres://" (a common alias some providers use) must not be
    # handed to SQLAlchemy as-is: its default driver for that scheme is
    # psycopg2, which this project does not have installed (only psycopg v3).
    assert settings.url.drivername == "postgresql+psycopg"


def test_database_url_password_never_appears_in_safe_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://render_user:a-real-secret@internal-host/render_db?sslmode=require",
    )

    settings = _settings()

    assert "a-real-secret" not in settings.safe_url


def test_no_sqlite_fallback_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no code path in PostgresSettings.url that can produce a
    sqlite:// URL under any environment variable combination — the only two
    branches are DATABASE_URL (normalized to postgresql+psycopg) or the
    component fields (hardcoded postgresql+psycopg)."""
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_DB", "freyja")
    monkeypatch.setenv("POSTGRES_USER", "freyja_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-local-password")

    settings = _settings()

    assert "sqlite" not in settings.url.drivername


def test_postgres_settings_construction_does_not_rely_on_the_local_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural proof of isolation from the real .env file (never read or
    modified by this test — its content is unknown to this test on
    purpose). This repo's local .env defines real POSTGRES_DB/USER/PASSWORD
    values so `docker compose`/the app can run locally. If _env_file=None
    did not actually disable the dotenv source, clearing every one of
    these variables from the process environment below would still let
    PostgresSettings() succeed by silently falling back to those real .env
    values — instead it must fail exactly like
    test_requires_either_database_url_or_component_variables expects. This
    test does not assert what .env contains, only that it is never
    consulted."""
    _clear_postgres_env(monkeypatch)

    with pytest.raises(ValidationError, match="Configuración de base de datos incompleta"):
        _settings()


# --- TLS is mandatory for any external (Neon-style) connection string -----


@pytest.mark.parametrize("env_key", ["DATABASE_URL", "DATABASE_DIRECT_URL"])
def test_external_url_without_sslmode_is_rejected(
    monkeypatch: pytest.MonkeyPatch, env_key: str
) -> None:
    _clear_postgres_env(monkeypatch)
    # DATABASE_URL is always required for the app's own runtime queries;
    # DATABASE_DIRECT_URL (Alembic-only) is meaningless on its own. Both
    # variables are set here (one valid, one missing sslmode) so the test
    # isolates which variable's TLS check actually fires.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://neon_user:neon_pass@ep-pooled.neon.tech/freyja?sslmode=require",
    )
    monkeypatch.setenv(env_key, "postgresql://neon_user:neon_pass@ep-example.neon.tech/freyja")

    with pytest.raises(ValidationError, match="sslmode"):
        _settings()


@pytest.mark.parametrize("insufficient_sslmode", ["disable", "allow", "prefer"])
def test_external_url_with_insufficient_sslmode_is_rejected(
    monkeypatch: pytest.MonkeyPatch, insufficient_sslmode: str
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://neon_user:neon_pass@ep-example.neon.tech/freyja?sslmode={insufficient_sslmode}",
    )

    with pytest.raises(ValidationError, match="sslmode"):
        _settings()


@pytest.mark.parametrize("sufficient_sslmode", ["require", "verify-ca", "verify-full"])
def test_external_url_with_sufficient_sslmode_is_accepted(
    monkeypatch: pytest.MonkeyPatch, sufficient_sslmode: str
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://neon_user:neon_pass@ep-example.neon.tech/freyja?sslmode={sufficient_sslmode}",
    )

    settings = _settings()

    assert settings.url.query.get("sslmode") == sufficient_sslmode


def test_component_based_local_development_is_unaffected_by_tls_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TLS requirement only applies to DATABASE_URL/DATABASE_DIRECT_URL —
    local development's component-based POSTGRES_* fields carry no such
    requirement (Docker Compose Postgres has no TLS configured locally)."""
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_DB", "freyja")
    monkeypatch.setenv("POSTGRES_USER", "freyja_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-local-password")

    settings = _settings()  # must not raise

    assert settings.url.query.get("sslmode") is None


# --- DATABASE_DIRECT_URL: Alembic-only, falls back to DATABASE_URL ---------


def test_migration_url_uses_direct_url_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://neon_user:neon_pass@ep-pooled.neon.tech/freyja?sslmode=require",
    )
    monkeypatch.setenv(
        "DATABASE_DIRECT_URL",
        "postgresql://neon_user:neon_pass@ep-direct.neon.tech/freyja?sslmode=require",
    )

    settings = _settings()

    assert settings.migration_url.host == "ep-direct.neon.tech"
    assert settings.url.host == "ep-pooled.neon.tech"


def test_migration_url_falls_back_to_database_url_when_direct_url_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://neon_user:neon_pass@ep-only-one.neon.tech/freyja?sslmode=require",
    )

    settings = _settings()

    assert settings.migration_url.host == settings.url.host == "ep-only-one.neon.tech"


def test_migration_url_falls_back_to_components_in_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_DB", "freyja")
    monkeypatch.setenv("POSTGRES_USER", "freyja_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-local-password")

    settings = _settings()

    assert settings.migration_url.drivername == "postgresql+psycopg"
    assert settings.migration_url.database == "freyja"


def test_direct_url_password_never_appears_in_safe_migration_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_postgres_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_DIRECT_URL",
        "postgresql://neon_user:a-direct-secret@ep-direct.neon.tech/freyja?sslmode=require",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://neon_user:neon_pass@ep-pooled.neon.tech/freyja?sslmode=require",
    )

    settings = _settings()

    assert "a-direct-secret" not in settings.safe_migration_url
