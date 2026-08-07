"""Commands for importing CSV data into the application database."""

from pathlib import Path

import typer

from opportunity_finder.db.session import create_session_factory
from opportunity_finder.services.import_service import ImportService, ImportSummary

app = typer.Typer(help="Import data from files.")


def _run_import(path: Path, method_name: str) -> None:
    """Run one ImportService method and render its result consistently."""
    try:
        session_factory = create_session_factory()
        with session_factory() as session:
            service = ImportService(session)
            summary = getattr(service, method_name)(str(path))
    except Exception as exc:
        typer.echo(f"Import failed ({type(exc).__name__}).", err=True)
        raise typer.Exit(code=1) from exc

    _echo_summary(summary)


def _echo_summary(summary: ImportSummary) -> None:
    already_processed = "yes" if summary.already_processed else "no"
    typer.echo(
        "Import complete: "
        f"total={summary.rows_total}, "
        f"imported={summary.rows_imported}, "
        f"quarantined={summary.rows_quarantined}, "
        f"already_processed={already_processed}."
    )


@app.command()
def products(path: Path) -> None:
    """Import products from PATH."""
    _run_import(path, "import_products")


@app.command("product-research")
def product_research(path: Path) -> None:
    """Import eBay Product Research data from PATH."""
    _run_import(path, "import_product_research")


@app.command()
def shipping(path: Path) -> None:
    """Import shipping rates from PATH."""
    _run_import(path, "import_shipping")


@app.command()
def fees(path: Path) -> None:
    """Import fee profiles from PATH."""
    _run_import(path, "import_fees")


@app.command()
def exchange(path: Path) -> None:
    """Import exchange rates from PATH."""
    _run_import(path, "import_exchange")
