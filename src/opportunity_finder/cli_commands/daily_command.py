"""Command for running the complete daily workflow."""

from pathlib import Path
from typing import Annotated

import typer

from opportunity_finder.config import Settings
from opportunity_finder.db.session import create_session_factory
from opportunity_finder.services.daily_service import DailyRunSummary, DailyService

app = typer.Typer(help="Run the daily workflow.")


@app.callback(invoke_without_command=True)
def daily(
    export_dir: Annotated[Path, typer.Option("--export-dir")],
    stale_only: Annotated[bool, typer.Option("--stale-only")] = False,
) -> None:
    """Run the daily workflow and export its results."""
    try:
        settings = Settings()
        session_factory = create_session_factory(settings)
        with session_factory() as session:
            summary = DailyService(session, settings=settings).run(
                stale_only=stale_only,
                export_dir=str(export_dir),
            )
    except Exception as exc:
        typer.echo(f"Daily workflow failed ({type(exc).__name__}).", err=True)
        raise typer.Exit(code=1) from exc

    _echo_summary(summary)
    if summary.exceeded_failure_threshold:
        raise typer.Exit(code=1)


def _echo_summary(summary: DailyRunSummary) -> None:
    typer.echo(
        "Daily workflow complete: "
        f"run_id={summary.run_id}, "
        f"status={summary.status}, "
        f"rows_read={summary.rows_read}, "
        f"rows_written={summary.rows_written}, "
        f"failures={summary.failure_count}, "
        f"export={summary.export_path}."
    )
