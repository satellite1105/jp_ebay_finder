"""SQLAlchemy engine and session factory construction."""

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from opportunity_finder.config import Settings


def create_database_url(settings: Settings) -> URL:
    """Build a password-safe SQLAlchemy URL from application settings."""
    return URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create the MySQL engine configured for resilient pooled connections."""
    resolved_settings = settings or Settings()
    return create_engine(
        create_database_url(resolved_settings),
        pool_pre_ping=True,
        pool_size=resolved_settings.mysql_pool_size,
        max_overflow=resolved_settings.mysql_max_overflow,
    )


def create_session_factory(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
) -> sessionmaker[Session]:
    """Create a reusable SQLAlchemy session factory."""
    bind = engine or create_db_engine(settings)
    return sessionmaker(bind=bind, class_=Session, autoflush=False, expire_on_commit=False)
