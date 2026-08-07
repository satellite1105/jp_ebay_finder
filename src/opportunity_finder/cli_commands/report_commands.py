"""Commands for reporting and exporting opportunity data."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from opportunity_finder.db.session import create_session_factory
from opportunity_finder.services.reporting_service import ReportingService

report_app = typer.Typer(help="Display opportunity reports.")
export_app = typer.Typer(help="Export opportunity data.")


@report_app.command()
def top(
    limit: Annotated[int, typer.Option("--limit", min=1)],
    decision: Annotated[str | None, typer.Option("--decision")] = None,
    output_format: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Display the top opportunities."""
    if output_format != "table":
        raise typer.BadParameter(
            'Only "table" is supported.',
            param_hint="--format",
        )

    session_factory = create_session_factory()
    with session_factory() as session:
        records = ReportingService(session).get_top_opportunities(
            limit=limit,
            decision=decision,
        )

        table = Table(title="Top Opportunities")
        table.add_column("ID", justify="right")
        table.add_column("Product", justify="right")
        table.add_column("Scenario")
        table.add_column("Score", justify="right")
        table.add_column("Profit (JPY)", justify="right")
        table.add_column("Margin", justify="right")
        table.add_column("Decision")

        for record in records:
            table.add_row(
                str(record.id),
                str(record.product_id),
                record.scenario,
                f"{record.opportunity_score:.4f}",
                f"{record.net_profit_jpy:.2f}",
                f"{record.net_margin:.2%}",
                record.decision,
            )

    Console().print(table)


@export_app.command()
def opportunities(
    path: Path,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    decision: Annotated[str | None, typer.Option("--decision")] = None,
) -> None:
    """Export opportunities to PATH."""
    session_factory = create_session_factory()
    with session_factory() as session:
        count = ReportingService(session).export_opportunities(
            path=path,
            limit=limit,
            decision=decision,
        )

    typer.echo(f"Exported {count} opportunity records to {path}.")


@export_app.command()
def audit(
    path: Path,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Export audit events to PATH."""
    session_factory = create_session_factory()
    with session_factory() as session:
        count = ReportingService(session).export_audit(path=path, run_id=run_id)

    typer.echo(f"Exported {count} audit records to {path}.")
