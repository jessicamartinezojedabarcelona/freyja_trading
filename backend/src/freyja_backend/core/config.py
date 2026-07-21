from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


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
    frontend_origin: str = "http://localhost:4200"
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

    @model_validator(mode="after")
    def _require_production_configuration(self) -> "Settings":
        if self.environment != "production":
            return self

        missing = []
        if not self.smtp_host:
            missing.append("FREYJA_SMTP_HOST")
        if not self.smtp_from_address:
            missing.append("FREYJA_SMTP_FROM_ADDRESS")
        if not self.rate_limit_hmac_key:
            missing.append("FREYJA_RATE_LIMIT_HMAC_KEY")
        if self.smtp_username and not self.smtp_password:
            missing.append("FREYJA_SMTP_PASSWORD")

        if missing:
            raise ValueError(
                "Configuración de producción incompleta, faltan: " + ", ".join(missing)
            )
        return self


def get_settings() -> Settings:
    return Settings()
