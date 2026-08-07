"""Commands for fetching domestic and eBay market data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import typer
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from opportunity_finder.clients.ebay_browse import EbayBrowseClient
from opportunity_finder.clients.rakuten_ichiba import RakutenIchibaClient
from opportunity_finder.clients.rakuten_product import RakutenProductClient
from opportunity_finder.clients.yahoo_shopping import YahooShoppingClient
from opportunity_finder.config import Settings
from opportunity_finder.db.models import MarketQuery, Product, SupplierItem, SupplierPriceSnapshot
from opportunity_finder.db.session import create_session_factory
from opportunity_finder.services.ebay_service import EbayRefreshSummary, EbayService
from opportunity_finder.services.market_service import MarketRefreshSummary, MarketService

app = typer.Typer(help="Fetch market data.")

_SOURCE_DATA_MAX_AGE_DAYS = 7


class _EmptyYahooClient:
    """Return no Yahoo offers when only Rakuten was requested."""

    def search(self, jan_code: str | None = None, query: str | None = None) -> dict[str, Any]:
        return {"hits": []}


class _EmptyRakutenIchibaClient:
    """Return no Ichiba offers when only Yahoo was requested."""

    def search_by_keyword(self, keyword: str, *, page: int = 1) -> dict[str, Any]:
        return {"Items": []}


class _EmptyRakutenProductClient:
    """Return no Rakuten Product offers when only Yahoo was requested."""

    def search_by_jan(self, jan_code: str, *, page: int = 1) -> dict[str, Any]:
        return {"Products": []}


@app.command()
def domestic(
    limit: Annotated[int, typer.Option("--limit", min=1)],
    source: Annotated[
        Literal["yahoo", "rakuten"] | None,
        typer.Option("--source"),
    ] = None,
) -> None:
    """Fetch domestic listings from Yahoo, Rakuten, or both."""
    summary = _refresh_domestic(source=source, limit=limit)
    _echo_domestic_summary(summary)


@app.command()
def ebay(query_id: Annotated[int, typer.Option("--query-id", min=1)]) -> None:
    """Fetch eBay listings for a query."""
    summary = _refresh_ebay([query_id])
    _echo_ebay_summary(summary)


@app.command("all")
def fetch_all(stale_only: Annotated[bool, typer.Option("--stale-only")] = False) -> None:
    """Fetch all configured market data."""
    if stale_only:
        summary = _refresh_domestic(source=None, limit=None, stale_only=True)
        _echo_domestic_summary(summary)

    ebay_summary = _refresh_ebay(None)
    _echo_ebay_summary(ebay_summary)


def _refresh_ebay(query_ids: list[int] | None) -> EbayRefreshSummary:
    client: EbayBrowseClient | None = None
    try:
        settings = Settings()
        client = _build_ebay_client(settings)
        session_factory = create_session_factory()
        with session_factory.begin() as session:
            selected_query_ids = query_ids if query_ids is not None else _ebay_query_ids(session)
            return EbayService(
                session,
                client,
                settings=settings,
            ).refresh_listings(selected_query_ids)
    except Exception as exc:
        typer.echo(
            f"eBay fetch failed ({type(exc).__name__}).",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    finally:
        if client is not None:
            client.close()


def _build_ebay_client(settings: Settings) -> EbayBrowseClient | None:
    if not (
        settings.ebay_enabled
        and settings.ebay_client_id.strip()
        and settings.ebay_client_secret.strip()
    ):
        return None
    return EbayBrowseClient(settings=settings)


def _ebay_query_ids(session: Session) -> list[int]:
    statement = select(MarketQuery.id).where(MarketQuery.enabled.is_(True)).order_by(MarketQuery.id)
    return list(session.scalars(statement).all())


def _refresh_domestic(
    *,
    source: Literal["yahoo", "rakuten"] | None,
    limit: int | None,
    stale_only: bool = False,
) -> MarketRefreshSummary:
    clients: tuple[object, object, object] | None = None
    try:
        settings = Settings()
        clients = _build_domestic_clients(settings, source)
        session_factory = create_session_factory()
        with session_factory.begin() as session:
            product_ids = _domestic_product_ids(
                session,
                limit=limit,
                stale_only=stale_only,
            )
            return MarketService(
                session,
                yahoo_client=clients[0],
                rakuten_ichiba_client=clients[1],
                rakuten_product_client=clients[2],
            ).refresh_domestic_prices(product_ids)
    except Exception as exc:
        typer.echo(
            f"Domestic fetch failed ({type(exc).__name__}).",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    finally:
        if clients is not None:
            _close_clients(clients)


def _build_domestic_clients(
    settings: Settings,
    source: Literal["yahoo", "rakuten"] | None,
) -> tuple[object, object, object]:
    yahoo_client: object
    rakuten_ichiba_client: object
    rakuten_product_client: object

    if source in (None, "yahoo"):
        yahoo_client = YahooShoppingClient(settings=settings)
    else:
        yahoo_client = _EmptyYahooClient()

    if source in (None, "rakuten"):
        affiliate_id = settings.rakuten_affiliate_id or None
        rakuten_ichiba_client = RakutenIchibaClient(
            settings.rakuten_application_id,
            affiliate_id=affiliate_id,
        )
        rakuten_product_client = RakutenProductClient(
            settings.rakuten_application_id,
            affiliate_id=affiliate_id,
        )
    else:
        rakuten_ichiba_client = _EmptyRakutenIchibaClient()
        rakuten_product_client = _EmptyRakutenProductClient()

    return yahoo_client, rakuten_ichiba_client, rakuten_product_client


def _domestic_product_ids(
    session: Session,
    *,
    limit: int | None,
    stale_only: bool,
) -> list[int]:
    has_matching_identifier = or_(
        func.length(func.trim(Product.jan_code)) > 0,
        func.length(func.trim(Product.brand)) > 0,
        func.length(func.trim(Product.model_number)) > 0,
    )
    statement = select(Product.id).where(has_matching_identifier).order_by(Product.id)

    if stale_only:
        fresh_after = (datetime.now(UTC) - timedelta(days=_SOURCE_DATA_MAX_AGE_DAYS)).replace(
            tzinfo=None
        )
        has_fresh_domestic_price = (
            select(SupplierPriceSnapshot.id)
            .join(
                SupplierItem,
                SupplierItem.id == SupplierPriceSnapshot.supplier_item_id,
            )
            .where(
                SupplierItem.product_id == Product.id,
                SupplierPriceSnapshot.captured_at >= fresh_after,
            )
            .exists()
        )
        statement = statement.where(~has_fresh_domestic_price)

    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all())


def _close_clients(clients: tuple[object, object, object]) -> None:
    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _echo_domestic_summary(summary: MarketRefreshSummary) -> None:
    typer.echo(
        "Domestic fetch complete: "
        f"products_checked={summary.products_checked}, "
        f"offers_matched={summary.offers_matched}, "
        f"yahoo_errors={summary.yahoo_errors}, "
        f"rakuten_errors={summary.rakuten_errors}."
    )


def _echo_ebay_summary(summary: EbayRefreshSummary) -> None:
    mode = "CSV" if summary.fallback_to_csv else "API"
    typer.echo(
        "eBay fetch complete: "
        f"queries_checked={summary.queries_checked}, "
        f"listings_saved={summary.listings_saved}, "
        f"mode={mode}."
    )
