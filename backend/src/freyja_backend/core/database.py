from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

_ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    @property
    def url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def safe_url(self) -> str:
        return self.url.render_as_string(hide_password=True)


def get_postgres_settings() -> PostgresSettings:
    return PostgresSettings()


def create_database_engine(settings: PostgresSettings | None = None) -> Engine:
    resolved = settings if settings is not None else get_postgres_settings()
    return create_engine(resolved.url)
