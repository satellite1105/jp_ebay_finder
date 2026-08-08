"""Fixtures that keep the shared MySQL integration database deterministic.

Rollback-based isolation (``db_session``/``clean_db`` in ``tests/conftest.py``)
only protects against writes made inside that one test's own transaction. It
cannot remove rows committed through a different connection or session -- for
example a CLI command under test that legitimately commits, or data left
behind by a manual ``uv run finder ...`` invocation against the same MySQL
instance outside of pytest. Any such leftover data makes assertions that rely
on exact counts or rankings flaky depending on what earlier runs happened to
leave behind.

To make ``uv run pytest`` deterministic regardless of what is already in the
database, every test under ``tests/integration/`` starts from an empty
database: all mapped tables are deleted (children before parents, driven by
``Base.metadata`` so newly added tables are picked up automatically) before
the test body runs.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

import opportunity_finder.db.models  # noqa: F401  (registers all tables on Base.metadata)
from opportunity_finder.db.base import Base

_TEST_DATABASE_SUFFIX = "_test"


def _assert_safe_test_database(engine: Engine) -> None:
    """Refuse to operate on anything that isn't clearly a test database.

    This is the only thing standing between the integration test suite and
    accidentally wiping a real development/production database, so it fails
    loudly (raises) instead of silently skipping cleanup.
    """
    database_name = (engine.url.database or "").strip()
    if not database_name.lower().endswith(_TEST_DATABASE_SUFFIX):
        raise RuntimeError(
            "Refusing to reset database "
            f"{database_name!r} for integration tests: its name does not end "
            f"with {_TEST_DATABASE_SUFFIX!r} (e.g. 'ebay_opportunity_test'). "
            "Point MYSQL_DATABASE (via .env or the environment) at a "
            "dedicated test database before running the integration suite."
        )


def _delete_all_rows(engine: Engine) -> None:
    """Delete every row from every ORM-mapped table in one committed transaction."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def _reset_test_database(db_engine: Engine) -> Iterator[None]:
    """Empty the test database before every integration test runs."""
    _assert_safe_test_database(db_engine)
    _delete_all_rows(db_engine)
    yield
