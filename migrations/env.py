"""Alembic environment for the application's MySQL schema."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from opportunity_finder.config import Settings
from opportunity_finder.db.models import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: alembic.ini only declares root/sqlalchemy/
    # alembic loggers. The default (True) would silently disable every other
    # logger already created in-process (e.g. opportunity_finder.* loggers,
    # or pytest's caplog handler) as soon as any `finder db ...` command runs.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> URL:
    """Build the MySQL URL without rendering credentials into logs or config."""
    settings = Settings()
    if not settings.mysql_database.strip():
        raise RuntimeError("MYSQL_DATABASE must name the target database")
    if not settings.mysql_user.strip():
        raise RuntimeError("MYSQL_USER must be set")
    if settings.mysql_user.strip().casefold() == "root":
        raise RuntimeError("Alembic migrations must not run as the MySQL root user")

    return URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured MySQL database."""
    database_url = _database_url()
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_migrations(supplied_connection)
        return

    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            _run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
