import pytest
from pydantic import ValidationError

from freyja_backend.core.config import Settings

_PROD_REQUIRED_ENV = {
    "FREYJA_ENVIRONMENT": "production",
    "FREYJA_SMTP_HOST": "smtp.example.test",
    "FREYJA_SMTP_FROM_ADDRESS": "no-reply@example.test",
    "FREYJA_RATE_LIMIT_HMAC_KEY": "a-real-secret-key-value",
    "FREYJA_FRONTEND_ORIGIN": "https://freyja-frontend.example.test",
    "FREYJA_ALLOWED_HOSTS": "freyja-backend.example.test",
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


def test_production_succeeds_with_all_required_variables_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    settings = _settings()
    assert settings.environment == "production"
    assert settings.cookie_secure is True


@pytest.mark.parametrize(
    "missing_key",
    [
        "FREYJA_SMTP_HOST",
        "FREYJA_SMTP_FROM_ADDRESS",
        "FREYJA_RATE_LIMIT_HMAC_KEY",
    ],
)
def test_production_fails_closed_without_required_variable(
    monkeypatch: pytest.MonkeyPatch, missing_key: str
) -> None:
    for key, value in _PROD_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_frontend_origin_left_at_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, {"FREYJA_FRONTEND_ORIGIN": "http://localhost:4200"})
    with pytest.raises(ValidationError):
        _settings()


def test_production_fails_closed_if_allowed_hosts_left_at_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, {"FREYJA_ALLOWED_HOSTS": "localhost,127.0.0.1"})
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
    FREYJA_* variable from the process environment below would still let
    Settings() succeed by silently falling back to those real .env values
    for the "missing" fields this test intentionally leaves unset — instead
    it must fail exactly the way test_production_fails_closed_without_
    required_variable expects. This test does not assert what .env
    contains, only that it is never consulted."""
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "production")
    for key in (
        "FREYJA_SMTP_HOST",
        "FREYJA_SMTP_FROM_ADDRESS",
        "FREYJA_RATE_LIMIT_HMAC_KEY",
        "FREYJA_FRONTEND_ORIGIN",
        "FREYJA_ALLOWED_HOSTS",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError, match="Configuración de producción incompleta"):
        _settings()
