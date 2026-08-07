"""Integration tests for the database CLI commands against MySQL."""

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine
from typer.testing import CliRunner

from opportunity_finder.cli import app

runner = CliRunner()


def test_db_check_succeeds_when_mysql_is_available() -> None:
    result = runner.invoke(app, ["db", "check"])

    assert result.exit_code == 0, result.output
    assert "Database connection successful." in result.output


def test_db_current_displays_database_revision(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()

    assert revision is not None, "The test database has no Alembic revision"

    result = runner.invoke(app, ["db", "current"])

    assert result.exit_code == 0, result.output
    assert revision in result.output
