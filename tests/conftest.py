"""Shared pytest fixtures for tests that require the MySQL test database."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opportunity_finder.config import Settings
from opportunity_finder.db.session import create_db_engine


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Create a lazily connecting engine configured from the project environment."""
    engine = create_db_engine(Settings())
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Provide a session isolated by a transaction that is always rolled back."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def clean_db(db_session: Session) -> Iterator[None]:
    """Explicitly mark a test for database cleanup through transaction rollback."""
    try:
        yield
    finally:
        db_session.rollback()
