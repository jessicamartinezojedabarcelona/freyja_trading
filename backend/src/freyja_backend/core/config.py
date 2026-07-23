from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# Development-only defaults. Also used to detect a production deployment that
# forgot to override them (see _require_production_configuration below).
_DEV_FRONTEND_ORIGIN = "http://localhost:4200"
_DEV_ALLOWED_HOSTS = "localhost,127.0.0.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FREYJA_",
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    app_name: str = "Freyja 2.0 Backend"
    app_version: str = "0.1.0"
    # No default: every environment (dev, test, CI, production) must set this
    # explicitly. A silent default is exactly the kind of footgun that lets a
    # misconfigured deployment run with development-grade security by accident.
    environment: Environment
    api_v1_prefix: str = "/api/v1"
    frontend_origin: str = _DEV_FRONTEND_ORIGIN
    # Comma-separated Host header allow-list for TrustedHostMiddleware. A
    # plain string (not a list) so it can be set from a single dashboard env
    # var without relying on JSON parsing of complex pydantic-settings types.
    allowed_hosts: str = _DEV_ALLOWED_HOSTS
    session_ttl_minutes: int = 720
    password_reset_ttl_minutes: int = 30

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str | None = None
    smtp_timeout_seconds: float = 10.0

    # Independent secret for HMAC-keyed rate-limiting identifiers. Never
    # reused as a password pepper, session secret, or CSRF material.
    rate_limit_hmac_key: str | None = None

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @model_validator(mode="after")
    def _reject_wildcard_frontend_origin(self) -> "Settings":
        # Never valid regardless of environment: allow_credentials=True combined
        # with a wildcard origin is rejected by browsers anyway, but failing
        # closed here means a misconfiguration is caught at startup, not
        # discovered later as a silently broken (or worse, tolerated-by-some-
        # client) CORS setup.
        if self.frontend_origin.strip() == "*":
            raise ValueError(
                "FREYJA_FRONTEND_ORIGIN no puede ser '*': CORS con credenciales exige "
                "un origen exacto."
            )
        return self

    @model_validator(mode="after")
    def _require_consistent_smtp_configuration(self) -> "Settings":
        # Applies in every environment, not just production: a partial SMTP
        # configuration is nonsensical regardless of where it runs. SMTP
        # itself stays fully optional — there is no provider approved yet
        # (see README, "SMTP pendiente"), and production must be able to
        # start with none of it set at all. What is never acceptable is
        # *half* a configuration (e.g. a host with no sender address, or a
        # username with no password) — those fail closed everywhere.
        # Never includes any configured value in the error message.
        missing = []
        if self.smtp_host and not self.smtp_from_address:
            missing.append("FREYJA_SMTP_FROM_ADDRESS (requerido si se define FREYJA_SMTP_HOST)")
        if self.smtp_from_address and not self.smtp_host:
            missing.append("FREYJA_SMTP_HOST (requerido si se define FREYJA_SMTP_FROM_ADDRESS)")
        if self.smtp_username and not self.smtp_password:
            missing.append("FREYJA_SMTP_PASSWORD (requerido si se define FREYJA_SMTP_USERNAME)")

        if missing:
            raise ValueError(
                "Configuración SMTP incompleta/inconsistente, faltan: " + ", ".join(missing)
            )
        return self

    @model_validator(mode="after")
    def _require_production_configuration(self) -> "Settings":
        if self.environment != "production":
            return self

        # SMTP is deliberately NOT required here: no provider is approved yet
        # (see README, "SMTP pendiente"). Production must be able to start
        # (registration, login, sessions) with password recovery simply
        # left non-operational until a real provider is configured later —
        # never by inventing placeholder SMTP values to satisfy this check.
        missing = []
        if not self.rate_limit_hmac_key:
            missing.append("FREYJA_RATE_LIMIT_HMAC_KEY")
        # Blank/whitespace-only is checked separately from the dev-default
        # sentinel: neither is byte-for-byte equal to it, but both are just as
        # broken — an empty allowed_hosts makes TrustedHostMiddleware reject
        # every request (including Render's own health check), and an empty
        # frontend_origin silently breaks CORS for every browser request.
        if not self.frontend_origin.strip() or self.frontend_origin.strip() == _DEV_FRONTEND_ORIGIN:
            missing.append(
                "FREYJA_FRONTEND_ORIGIN (no puede quedar vacío ni en el valor de desarrollo)"
            )
        if not self.allowed_hosts_list or self.allowed_hosts.strip() == _DEV_ALLOWED_HOSTS:
            missing.append(
                "FREYJA_ALLOWED_HOSTS (no puede quedar vacío ni en el valor de desarrollo)"
            )

        if missing:
            raise ValueError(
                "Configuración de producción incompleta, faltan: " + ", ".join(missing)
            )
        return self


def get_settings() -> Settings:
    return Settings()
