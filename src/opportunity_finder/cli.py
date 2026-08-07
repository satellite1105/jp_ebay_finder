"""Command-line interface for Opportunity Finder."""

import typer

from opportunity_finder.cli_commands.calculate_commands import app as calculate_app
from opportunity_finder.cli_commands.daily_command import app as daily_app
from opportunity_finder.cli_commands.db_commands import app as db_app
from opportunity_finder.cli_commands.fetch_commands import app as fetch_app
from opportunity_finder.cli_commands.import_commands import app as import_app
from opportunity_finder.cli_commands.report_commands import export_app, report_app

app = typer.Typer(help="Find Japanese products with eBay sales opportunities.")

app.add_typer(db_app, name="db")
app.add_typer(import_app, name="import")
app.add_typer(fetch_app, name="fetch")
app.add_typer(calculate_app, name="calculate")
app.add_typer(report_app, name="report")
app.add_typer(export_app, name="export")
app.add_typer(daily_app, name="daily")


if __name__ == "__main__":
    app()
