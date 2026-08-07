"""Integration tests for refreshing domestic marketplace prices."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import SupplierItem, SupplierPriceSnapshot
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.services.market_service import MarketService


class YahooStub:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str | None, str | None]] = []

    def search(self, jan_code: str | None = None, query: str | None = None) -> dict[str, Any]:
        self.calls.append((jan_code, query))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class RakutenIchibaStub:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[str] = []

    def search_by_keyword(self, keyword: str, *, page: int = 1) -> dict[str, Any]:
        self.calls.append(keyword)
        return self.response


class RakutenProductStub:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[str] = []

    def search_by_jan(self, jan_code: str, *, page: int = 1) -> dict[str, Any]:
        self.calls.append(jan_code)
        return self.response


def test_refresh_matches_and_saves_yahoo_and_rakuten_offers(
    db_session: Session, clean_db: None
) -> None:
    product = ProductRepository(db_session).get_or_create(
        "4901234567801",
        internal_sku="T33-MATCH",
        normalized_name="sony wh-1000xm5 headphones",
        original_name="Sony WH-1000XM5 Headphones",
        brand="Sony",
        model_number="WH-1000XM5",
    )
    yahoo = YahooStub(
        {
            "hits": [
                {
                    "code": "yahoo-t33-1",
                    "name": "Sony WH-1000XM5 Headphones",
                    "price": 1200,
                    "inStock": True,
                    "janCode": product.jan_code,
                    "brand": {"name": "Sony"},
                    "modelNumber": "WH-1000XM5",
                    "point": {"amount": 100, "bonusAmount": 0},
                }
            ]
        }
    )
    ichiba = RakutenIchibaStub(
        {
            "Items": [
                {
                    "Item": {
                        "itemCode": "rakuten-t33-1",
                        "itemName": "Sony WH-1000XM5 Headphones",
                        "itemPrice": 2000,
                        "availability": 1,
                        "shippingPrice": 500,
                        "pointRate": 10,
                        "janCode": product.jan_code,
                        "brandName": "Sony",
                        "modelNumber": "WH-1000XM5",
                    }
                }
            ]
        }
    )
    rakuten_product = RakutenProductStub(
        {
            "Products": [
                {
                    "Product": {
                        "productId": "rakuten-product-t33-1",
                        "productName": "Sony WH-1000XM5 Headphones",
                        "salesMinPrice": 1800,
                        "janCode": product.jan_code,
                        "brandName": "Sony",
                        "modelNumber": "WH-1000XM5",
                    }
                }
            ]
        }
    )

    summary = MarketService(
        db_session,
        yahoo_client=yahoo,
        rakuten_ichiba_client=ichiba,
        rakuten_product_client=rakuten_product,
    ).refresh_domestic_prices([product.id])

    rows = db_session.execute(
        select(SupplierItem, SupplierPriceSnapshot)
        .join(
            SupplierPriceSnapshot,
            SupplierPriceSnapshot.supplier_item_id == SupplierItem.id,
        )
        .where(SupplierItem.product_id == product.id)
        .order_by(SupplierItem.external_item_id)
    ).all()
    snapshots = {item.external_item_id: snapshot for item, snapshot in rows}

    assert summary.products_checked == 1
    assert summary.offers_matched == 3
    assert summary.yahoo_errors == 0
    assert summary.rakuten_errors == 0
    assert set(snapshots) == {
        "yahoo-t33-1",
        "rakuten-t33-1",
        "rakuten-product-t33-1",
    }
    assert snapshots["rakuten-t33-1"].item_price_jpy == Decimal("2000.0000")
    assert snapshots["rakuten-t33-1"].domestic_shipping_jpy == Decimal("500.0000")
    assert snapshots["rakuten-t33-1"].points_value_jpy == Decimal("200.0000")
    assert snapshots["rakuten-t33-1"].effective_cost_jpy == Decimal("2300.0000")
    assert snapshots["yahoo-t33-1"].effective_cost_jpy == Decimal("1100.0000")
    assert yahoo.calls == [(product.jan_code, "Sony WH-1000XM5")]
    assert ichiba.calls == ["Sony WH-1000XM5"]
    assert rakuten_product.calls == [product.jan_code]


def test_refresh_continues_with_rakuten_when_yahoo_fails(
    db_session: Session,
    clean_db: None,
    caplog: Any,
) -> None:
    product = ProductRepository(db_session).get_or_create(
        "4901234567802",
        internal_sku="T33-FALLBACK",
        normalized_name="canon eos r5 camera",
        original_name="Canon EOS R5 Camera",
        brand="Canon",
        model_number="EOS-R5",
    )
    yahoo = YahooStub(TimeoutError("simulated Yahoo timeout"))
    ichiba = RakutenIchibaStub(
        {
            "Items": [
                {
                    "Item": {
                        "itemCode": "rakuten-t33-fallback",
                        "itemName": "Canon EOS R5 Camera",
                        "itemPrice": 3000,
                        "availability": 1,
                        "shippingPrice": 250,
                        "pointRate": 0,
                        "janCode": product.jan_code,
                        "brandName": "Canon",
                        "modelNumber": "EOS-R5",
                    }
                }
            ]
        }
    )
    rakuten_product = RakutenProductStub({"Products": []})

    summary = MarketService(
        db_session,
        yahoo_client=yahoo,
        rakuten_ichiba_client=ichiba,
        rakuten_product_client=rakuten_product,
    ).refresh_domestic_prices([product.id])

    saved_cost = db_session.scalar(
        select(SupplierPriceSnapshot.effective_cost_jpy)
        .join(SupplierItem)
        .where(SupplierItem.external_item_id == "rakuten-t33-fallback")
    )
    assert summary.products_checked == 1
    assert summary.offers_matched == 1
    assert summary.yahoo_errors == 1
    assert summary.rakuten_errors == 0
    assert saved_cost == Decimal("3250.0000")
    assert "YAHOO" in caplog.text
    assert ichiba.calls == ["Canon EOS-R5"]
    assert rakuten_product.calls == [product.jan_code]
