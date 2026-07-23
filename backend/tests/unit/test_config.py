import pytest
from pydantic import ValidationError

from freyja_backend.core.config import Settings

_PROD_REQUIRED_ENV = {
    "FREYJA_ENVIRONMENT": "production",
    "FREYJA_RATE_LIMIT_HMAC_KEY": "a-real-secret-key-value",
    "FREYJA_FRONTEND_ORIGIN": "https://freyja-frontend.example.test",
    "FREYJA_ALLOWED_HOSTS": "freyja-backend.example.test",
}

_VALID_SMTP_ENV = {
    "FREYJA_SMTP_HOST": "smtp.example.test",
    "FREYJA_SMTP_FROM_ADDRESS": "no-reply@example.test",
}


def _settings(**init_kwargs: object) -> Settings:
    # _env_file=None is the real isolation mechanism: it disables pydantic-
    # settings' dotenv source for this instantiation entirely, so this
    # repo's actual local .env file (which defines real POSTGRES_*/SMTP
    # values for Mailpit) is never consulted, regardless of what is or
    # isn't set in the process environment. Overriding with empty strings
    # is NOT equivalent — it still reads the real .env for every OTHER key
    # this test didn't happen to touch.
    return Settings(_env_file=None, **init_kwargs)  # type: ignore[arg-type]


def _set_env(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> None:
    env = {**_PROD_REQUIRED_ENV, **(overrides or {})}
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def _clear_smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "FREYJA_SMTP_HOST",
        "FREYJA_SMTP_FROM_ADDRESS",
        "FREYJA_SMTP_USERNAME",
        "FREYJA_SMTP_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)


def test_production_succeeds_with_all_required_variables_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    _clear_smtp_env(monkeypatch)
    settings = _settings()
    assert settings.environment == "production"
    assert settings.cookie_secure is True


def test_production_succeeds_with_no_smtp_variables_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Product decision: no SMTP provider is approved yet. Production must
    start (registration, login, sessions) with zero SMTP configuration —
    password recovery simply stays non-operational until a real provider
    is configured later, never by inventing placeholder SMTP values."""
    _set_env(monkeypatch)
    _clear_smtp_env(monkeypatch)
    settings = _settings()
    assert settings.smtp_host is None
    assert settings.smtp_from_address is None


@pytest.mark.parametrize("missing_key", ["FREYJA_RATE_LIMIT_HMAC_KEY"])
def test_production_fails_closed_without_required_variable(
    monkeypatch: pytest.MonkeyPatch, missing_key: str
) -> None:
    for key, value in _PROD_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    _clear_smtp_env(monkeypatch)
    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_frontend_origin_left_at_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, {"FREYJA_FRONTEND_ORIGIN": "http://localhost:4200"})
    _clear_smtp_env(monkeypatch)
    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_allowed_hosts_left_at_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, {"FREYJA_ALLOWED_HOSTS": "localhost,127.0.0.1"})
    _clear_smtp_env(monkeypatch)
    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_frontend_origin_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank is not equal to the dev-default sentinel by strict `==`, but is
    just as broken: it must still be caught, not silently accepted."""
    _set_env(monkeypatch, {"FREYJA_FRONTEND_ORIGIN": "   "})
    _clear_smtp_env(monkeypatch)
    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_allowed_hosts_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty/whitespace-only value parses to an empty allowed_hosts_list,
    which would make TrustedHostMiddleware reject every request (including
    Render's own health check) — must fail closed at startup instead."""
    _set_env(monkeypatch, {"FREYJA_ALLOWED_HOSTS": " , "})
    _clear_smtp_env(monkeypatch)
    with pytest.raises(ValidationError):
        _settings()


def test_wildcard_frontend_origin_rejected_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.setenv("FREYJA_FRONTEND_ORIGIN", "*")
    with pytest.raises(ValidationError):
        _settings()


def test_allowed_hosts_list_splits_and_strips_comma_separated_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.setenv("FREYJA_ALLOWED_HOSTS", "example.test, second.example.test ,,third.test")
    settings = _settings()
    assert settings.allowed_hosts_list == ["example.test", "second.example.test", "third.test"]


def test_development_does_not_require_production_only_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "development")
    settings = _settings()
    assert settings.cookie_secure is False


def test_settings_construction_does_not_rely_on_the_local_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural proof of isolation from the real .env file (never read or
    modified by this test — its content is unknown to this test on
    purpose). This repo's local .env defines real values for local
    development (e.g. Mailpit's FREYJA_SMTP_HOST=127.0.0.1). If _env_file=
    None did not actually disable the dotenv source, clearing every
    FREYJA_* variable this test cares about would still let Settings()
    succeed by silently falling back to those real .env values — instead
    it must fail exactly the way test_production_fails_closed_without_
    required_variable expects. This test does not assert what .env
    contains, only that it is never consulted."""
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "production")
    for key in (
        "FREYJA_RATE_LIMIT_HMAC_KEY",
        "FREYJA_FRONTEND_ORIGIN",
        "FREYJA_ALLOWED_HOSTS",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError, match="Configuración de producción incompleta"):
        _settings()


# --- SMTP: fully optional, but never partially configured ------------------


def test_smtp_host_without_from_address_fails_closed_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.setenv("FREYJA_SMTP_HOST", "smtp.example.test")
    monkeypatch.delenv("FREYJA_SMTP_FROM_ADDRESS", raising=False)

    with pytest.raises(ValidationError, match="FREYJA_SMTP_FROM_ADDRESS"):
        _settings()


def test_smtp_from_address_without_host_fails_closed_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.delenv("FREYJA_SMTP_HOST", raising=False)
    monkeypatch.setenv("FREYJA_SMTP_FROM_ADDRESS", "no-reply@example.test")

    with pytest.raises(ValidationError, match="FREYJA_SMTP_HOST"):
        _settings()


def test_smtp_username_without_password_fails_closed_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.setenv("FREYJA_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("FREYJA_SMTP_FROM_ADDRESS", "no-reply@example.test")
    monkeypatch.setenv("FREYJA_SMTP_USERNAME", "a-username")
    monkeypatch.delenv("FREYJA_SMTP_PASSWORD", raising=False)

    with pytest.raises(ValidationError, match="FREYJA_SMTP_PASSWORD"):
        _settings()


def test_smtp_fully_configured_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    for key, value in _VALID_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("FREYJA_SMTP_USERNAME", "a-username")
    monkeypatch.setenv("FREYJA_SMTP_PASSWORD", "a-password")

    settings = _settings()  # must not raise

    assert settings.smtp_host == "smtp.example.test"
    assert settings.smtp_username == "a-username"


def test_smtp_partial_config_error_never_echoes_the_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    monkeypatch.setenv("FREYJA_SMTP_USERNAME", "a-very-specific-username-value")
    monkeypatch.delenv("FREYJA_SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("FREYJA_SMTP_HOST", raising=False)
    monkeypatch.delenv("FREYJA_SMTP_FROM_ADDRESS", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        _settings()

    assert "a-very-specific-username-value" not in str(exc_info.value)
