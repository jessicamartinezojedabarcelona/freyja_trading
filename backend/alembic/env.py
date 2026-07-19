from logging.config import fileConfig

from sqlalchemy import URL, create_engine, pool

from alembic import context
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> URL:
    if "database_url" not in config.attributes:
        return get_postgres_settings().url

    override = config.attributes["database_url"]
    if not isinstance(override, URL):
        raise TypeError("Alembic database_url must be a sqlalchemy.URL instance.")

    return override


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Freyja requiere ejecutar migraciones en modo online contra "
        "PostgreSQL real; el modo offline no esta soportado."
    )


def run_migrations_online() -> None:
    database_url = _get_database_url()
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
