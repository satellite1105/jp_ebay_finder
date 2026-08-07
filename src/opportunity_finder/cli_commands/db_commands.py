"""Commands for inspecting and migrating the application database."""

from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from opportunity_finder.db.session import create_db_engine

app = typer.Typer(help="Inspect and manage the database.")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    """Load the project Alembic configuration with an absolute script path."""
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    return config


@app.command()
def check() -> None:
    """Check database connectivity."""
    engine = None
    try:
        engine = create_db_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        typer.echo(
            f"Database connection failed ({type(exc).__name__}).",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    finally:
        if engine is not None:
            engine.dispose()

    typer.echo("Database connection successful.")


@app.command()
def upgrade() -> None:
    """Upgrade the database schema."""
    try:
        command.upgrade(_alembic_config(), "head")
    except Exception as exc:
        typer.echo(f"Database upgrade failed ({type(exc).__name__}).", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Database upgrade complete.")


@app.command()
def current() -> None:
    """Show the current database revision."""
    # alembic.command.current() writes via Config.print_stdout(), which is not
    # reliably captured by Typer's/Click's CliRunner in tests. Query the
    # revision directly instead, so the output is deterministic and testable.
    engine = None
    try:
        engine = create_db_engine()
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
    except Exception as exc:
        typer.echo(
            f"Unable to read the current database revision ({type(exc).__name__}).",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    finally:
        if engine is not None:
            engine.dispose()

    if revision is None:
        typer.echo("No migrations applied yet.")
    else:
        typer.echo(revision)
