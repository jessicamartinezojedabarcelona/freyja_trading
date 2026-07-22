from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine, make_url
from sqlalchemy.engine import Engine

_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# Neon (and most managed Postgres providers reachable over the public
# internet) rejects plaintext connections outright, but this project's own
# config validation does not rely on that alone: an external connection
# string must *declare* one of these sslmode values itself, or Settings
# fails closed at startup rather than silently attempting — and possibly
# succeeding at — a connection whose encryption was never actually verified
# by this code.
_TLS_REQUIRED_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    # Single connection-string secret for runtime queries (e.g. Neon's pooled
    # connection string). Takes precedence over the individual POSTGRES_*
    # fields below when set, so a hosting platform can supply one secret
    # instead of five. Local development keeps using the component fields
    # unchanged.
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # Separate, direct (unpooled) connection string used only for Alembic
    # migrations — Neon's own guidance is that PgBouncer transaction-mode
    # pooling (what DATABASE_URL points at) does not support the session-
    # level features (SET, LISTEN/NOTIFY, PREPARE) schema migration tools
    # rely on. Optional: falls back to DATABASE_URL if not set (see
    # migration_url below), so this is only required for providers that
    # actually separate the two, not for local development.
    database_direct_url: str | None = Field(default=None, alias="DATABASE_DIRECT_URL")

    postgres_db: str | None = Field(default=None, alias="POSTGRES_DB")
    postgres_user: str | None = Field(default=None, alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    # Only meaningful for the component-based (local development) path: an
    # external connection string's TLS requirement is instead enforced via
    # its own sslmode query parameter (see _require_tls_for_external_urls).
    postgres_sslmode: str | None = Field(default=None, alias="POSTGRES_SSLMODE")

    @model_validator(mode="after")
    def _require_database_url_or_components(self) -> "PostgresSettings":
        if self.database_url:
            return self
        if not (self.postgres_db and self.postgres_user and self.postgres_password):
            raise ValueError(
                "Configuración de base de datos incompleta: define DATABASE_URL, o bien "
                "POSTGRES_DB, POSTGRES_USER y POSTGRES_PASSWORD."
            )
        return self

    @model_validator(mode="after")
    def _require_tls_for_external_urls(self) -> "PostgresSettings":
        for label, value in (
            ("DATABASE_URL", self.database_url),
            ("DATABASE_DIRECT_URL", self.database_direct_url),
        ):
            if not value:
                continue
            sslmode = make_url(value).query.get("sslmode")
            if sslmode not in _TLS_REQUIRED_SSLMODES:
                raise ValueError(
                    f"{label} debe declarar sslmode=require (o verify-ca/verify-full): "
                    "TLS es obligatorio para una conexión externa como Neon."
                )
        return self

    @staticmethod
    def _normalize_to_psycopg(raw_url: str) -> URL:
        # Normalizes whatever scheme the provider hands back ("postgres://"
        # and "postgresql://" are both common) to the psycopg v3 driver this
        # project actually has installed.
        return make_url(raw_url).set(drivername="postgresql+psycopg")

    @property
    def url(self) -> URL:
        if self.database_url:
            return self._normalize_to_psycopg(self.database_url)
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def migration_url(self) -> URL:
        """The URL Alembic should connect with — the direct (unpooled)
        connection when one was supplied, otherwise the same URL runtime
        queries use (correct for local development and any provider that
        does not distinguish the two)."""
        if self.database_direct_url:
            return self._normalize_to_psycopg(self.database_direct_url)
        return self.url

    @property
    def safe_url(self) -> str:
        return self.url.render_as_string(hide_password=True)

    @property
    def safe_migration_url(self) -> str:
        return self.migration_url.render_as_string(hide_password=True)


def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings()


def create_database_engine(settings: PostgresSettings | None = None) -> Engine:
    resolved = settings if settings is not None else get_postgres_settings()
    # postgres_sslmode is a connect_args override for the component-based
    # (local) path only: an external DATABASE_URL already carries its own
    # sslmode in its query string (enforced by the validator above), and
    # passing both would conflict.
    connect_args = (
        {"sslmode": resolved.postgres_sslmode}
        if resolved.postgres_sslmode and not resolved.database_url
        else {}
    )
    return create_engine(resolved.url, connect_args=connect_args)
