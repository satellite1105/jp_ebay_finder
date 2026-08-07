"""Integration tests for the domestic market fetch CLI commands."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder import cli
from opportunity_finder.cli_commands import fetch_commands
from opportunity_finder.db.models import SupplierItem
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository

runner = CliRunner()


class _TestSessionFactory:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def begin(self) -> Iterator[Session]:
        yield self._session


class _YahooStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None]] = []

    def search(self, jan_code: str | None = None, query: str | None = None) -> dict[str, Any]:
        self.calls.append((jan_code, query))
        return {
            "hits": [
                {
                    "code": f"yahoo-cli-{jan_code}",
                    "name": query,
                    "price": 1200,
                    "inStock": True,
                    "janCode": jan_code,
                    "brand": {"name": "CLI Brand"},
                    "modelNumber": query,
                    "point": {"amount": 100, "bonusAmount": 0},
                }
            ]
        }


class _RakutenIchibaStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_by_keyword(self, keyword: str, *, page: int = 1) -> dict[str, Any]:
        self.calls.append(keyword)
        return {
            "Items": [
                {
                    "Item": {
                        "itemCode": f"ichiba-cli-{keyword}",
                        "itemName": keyword,
                        "itemPrice": 1400,
                        "availability": 1,
                        "shippingPrice": 200,
                        "pointRate": 1,
                    }
                }
            ]
        }


class _RakutenProductStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_by_jan(self, jan_code: str, *, page: int = 1) -> dict[str, Any]:
        self.calls.append(jan_code)
        return {
            "Products": [
                {
                    "Product": {
                        "productId": f"product-cli-{jan_code}",
                        "productName": f"CLI Brand {jan_code}",
                        "salesMinPrice": 1300,
                        "janCode": jan_code,
                        "brandName": "CLI Brand",
                    }
                }
            ]
        }


@pytest.fixture
def cli_clients(
    db_session: Session,
    clean_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_YahooStub, _RakutenIchibaStub, _RakutenProductStub]:
    yahoo = _YahooStub()
    ichiba = _RakutenIchibaStub()
    product = _RakutenProductStub()
    session_factory = _TestSessionFactory(db_session)

    monkeypatch.setattr(
        fetch_commands,
        "create_session_factory",
        lambda settings=None: session_factory,
    )
    monkeypatch.setattr(fetch_commands, "YahooShoppingClient", lambda **kwargs: yahoo)
    monkeypatch.setattr(
        fetch_commands,
        "RakutenIchibaClient",
        lambda *args, **kwargs: ichiba,
    )
    monkeypatch.setattr(
        fetch_commands,
        "RakutenProductClient",
        lambda *args, **kwargs: product,
    )
    return yahoo, ichiba, product


def _create_product(session: Session, suffix: str) -> int:
    product = ProductRepository(session).get_or_create(
        f"49000000000{suffix}",
        internal_sku=f"T34-{suffix}",
        normalized_name=f"cli brand cli model {suffix}",
        original_name=f"CLI Brand CLI Model {suffix}",
        brand="CLI Brand",
        model_number=f"CLI Model {suffix}",
    )
    return product.id


@pytest.mark.parametrize(
    ("source", "expected_offers", "expected_yahoo_calls", "expected_ichiba_calls"),
    [
        ("yahoo", 1, 1, 0),
        ("rakuten", 2, 0, 1),
    ],
)
def test_domestic_source_fetches_selected_provider_and_prints_summary(
    db_session: Session,
    cli_clients: tuple[_YahooStub, _RakutenIchibaStub, _RakutenProductStub],
    source: str,
    expected_offers: int,
    expected_yahoo_calls: int,
    expected_ichiba_calls: int,
) -> None:
    product_id = _create_product(db_session, "01")
    yahoo, ichiba, _ = cli_clients

    result = runner.invoke(
        cli.app,
        ["fetch", "domestic", "--source", source, "--limit", "10"],
    )

    supplier_items = list(
        db_session.scalars(select(SupplierItem).where(SupplierItem.product_id == product_id)).all()
    )
    assert result.exit_code == 0, result.output
    assert len(yahoo.calls) == expected_yahoo_calls
    assert len(ichiba.calls) == expected_ichiba_calls
    assert len(supplier_items) == expected_offers
    assert "Domestic fetch complete: products_checked=1" in result.output
    assert f"offers_matched={expected_offers}" in result.output
    assert "yahoo_errors=0" in result.output
    assert "rakuten_errors=0" in result.output


def test_domestic_without_source_fetches_both_providers(
    db_session: Session,
    cli_clients: tuple[_YahooStub, _RakutenIchibaStub, _RakutenProductStub],
) -> None:
    _create_product(db_session, "02")
    yahoo, ichiba, product = cli_clients

    result = runner.invoke(cli.app, ["fetch", "domestic", "--limit", "10"])

    assert result.exit_code == 0, result.output
    assert len(yahoo.calls) == 1
    assert len(ichiba.calls) == 1
    assert len(product.calls) == 1
    assert "products_checked=1" in result.output
    assert "offers_matched=3" in result.output


def test_domestic_limit_bounds_products_checked(
    db_session: Session,
    cli_clients: tuple[_YahooStub, _RakutenIchibaStub, _RakutenProductStub],
) -> None:
    _create_product(db_session, "03")
    _create_product(db_session, "04")
    yahoo, _, _ = cli_clients

    result = runner.invoke(
        cli.app,
        ["fetch", "domestic", "--source", "yahoo", "--limit", "1"],
    )

    assert result.exit_code == 0, result.output
    assert len(yahoo.calls) == 1
    assert "products_checked=1" in result.output


def test_fetch_all_stale_only_refreshes_only_products_without_fresh_prices(
    db_session: Session,
    cli_clients: tuple[_YahooStub, _RakutenIchibaStub, _RakutenProductStub],
) -> None:
    stale_product_id = _create_product(db_session, "05")
    fresh_product_id = _create_product(db_session, "06")
    now = datetime.now(UTC)
    suppliers = SupplierRepository(db_session)
    fresh_item = suppliers.upsert_supplier_item(
        product_id=fresh_product_id,
        source="YAHOO",
        external_item_id="fresh-cli-price",
        title="CLI Brand CLI Model 06",
        jan_code="4900000000006",
        brand="CLI Brand",
        model_number="CLI Model 06",
        match_method="jan",
        match_confidence=Decimal(1),
        last_seen_at=now,
    )
    suppliers.add_price_snapshot(
        supplier_item_id=fresh_item.id,
        item_price_jpy=Decimal(1000),
        available=True,
        effective_cost_jpy=Decimal(1000),
        captured_at=now,
    )
    yahoo, _, _ = cli_clients

    result = runner.invoke(cli.app, ["fetch", "all", "--stale-only"])

    refreshed_product_ids = set(
        db_session.scalars(
            select(SupplierItem.product_id).where(
                SupplierItem.external_item_id != "fresh-cli-price"
            )
        ).all()
    )
    assert result.exit_code == 0, result.output
    assert len(yahoo.calls) == 1
    assert refreshed_product_ids == {stale_product_id}
    assert "Domestic fetch complete: products_checked=1" in result.output
    # eBay fetch was a stub when this test was first written (T34); T37 later
    # implemented it, so `fetch all` now also reports real eBay fetch output
    # (falling back to CSV mode here, since eBay is disabled in this test env).
    assert "eBay fetch complete:" in result.output
