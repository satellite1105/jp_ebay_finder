"""Commands for calculating and displaying product opportunities."""

from decimal import Decimal
from typing import Annotated

import typer

from opportunity_finder.db.session import create_session_factory
from opportunity_finder.domain.models import OpportunityResult
from opportunity_finder.services.opportunity_service import OpportunityService

app = typer.Typer(help="Calculate opportunities and prices.")

_SCENARIO_ORDER = ("optimistic", "base", "conservative")


@app.command()
def opportunities() -> None:
    """Calculate all opportunities."""
    results = _calculate_opportunities()
    typer.echo(f"Calculated opportunities: {len(results)} product(s).")


@app.command()
def opportunity(product_id: Annotated[int, typer.Option("--product-id", min=1)]) -> None:
    """Calculate an opportunity for one product."""
    result = _calculate_product(product_id)

    typer.echo(f"Product ID: {result.product_id}")
    typer.echo(f"Query ID: {result.query_id}")
    typer.echo(f"Decision: {result.decision}")
    typer.echo(f"Opportunity score: {_decimal_text(result.opportunity_score)}")
    typer.echo(f"Confidence score: {_decimal_text(result.confidence_score)}")
    typer.echo(f"Reason codes: {', '.join(result.reason_codes) or '-'}")
    for scenario_name in _SCENARIO_ORDER:
        scenario = result.scenarios[scenario_name]
        typer.echo(f"{scenario_name}:")
        typer.echo(f"  Net profit (JPY): {_decimal_text(scenario.net_profit_jpy)}")
        typer.echo(f"  Net margin: {_decimal_text(scenario.net_margin)}")
        typer.echo(
            f"  Break-even price (USD): {_decimal_text(scenario.break_even_buyer_total_usd)}"
        )
        typer.echo(f"  Target price (USD): {_decimal_text(scenario.target_price_usd)}")


@app.command("break-even")
def break_even(product_id: Annotated[int, typer.Option("--product-id", min=1)]) -> None:
    """Calculate the base-scenario break-even price for one product."""
    result = _calculate_product(product_id)
    base = result.scenarios["base"]

    typer.echo(f"Product ID: {result.product_id}")
    typer.echo(f"Break-even price (USD): {_decimal_text(base.break_even_buyer_total_usd)}")


def _calculate_product(product_id: int) -> OpportunityResult:
    result = next(
        (
            opportunity_result
            for opportunity_result in _calculate_opportunities()
            if opportunity_result.product_id == product_id
        ),
        None,
    )
    if result is None:
        typer.echo(
            f"No calculable opportunity found for product ID {product_id}.",
            err=True,
        )
        raise typer.Exit(code=1)
    return result


def _calculate_opportunities() -> list[OpportunityResult]:
    try:
        session_factory = create_session_factory()
        with session_factory.begin() as session:
            return OpportunityService(session).calculate_opportunities()
    except Exception as exc:
        typer.echo(
            f"Opportunity calculation failed ({type(exc).__name__}).",
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")
