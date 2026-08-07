"""Integration tests for eBay listing refresh and fallback auditing."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_finder.config import Settings
from opportunity_finder.db.models import (
    AuditLog,
    EbayListing,
    EbayListingSnapshot,
    MarketResearchMetric,
)
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.services.ebay_service import EbayService


class EbayStub:
    enabled = True

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str | None, str | None]] = []

    def search(self, keyword: str | None = None, gtin: str | None = None) -> dict[str, Any]:
        self.calls.append((keyword, gtin))
        return self.response


def _item(item_id: str, price: str, *, shipping: str = "5.00") -> dict[str, Any]:
    return {
        "itemId": item_id,
        "title": "Sony WH-1000XM5 Headphones",
        "itemWebUrl": f"https://www.ebay.com/itm/{item_id}",
        "price": {"value": price, "currency": "USD"},
        "shippingOptions": [{"shippingCost": {"value": shipping, "currency": "USD"}}],
        "condition": "New",
        "itemLocation": {"country": "US"},
        "seller": {"username": f"seller-{item_id}"},
        "estimatedAvailabilities": [{"estimatedAvailableQuantity": 1}],
        "localizedAspects": [
            {"name": "Brand", "value": "Sony"},
            {"name": "MPN", "value": "WH-1000XM5"},
        ],
    }


def test_refresh_saves_listings_snapshots_and_actual_competition_count(
    db_session: Session,
    clean_db: None,
) -> None:
    product = ProductRepository(db_session).get_or_create(
        "4901234567836",
        internal_sku="T36-API",
        normalized_name="sony wh-1000xm5 headphones",
        original_name="Sony WH-1000XM5 Headphones",
        brand="Sony",
        model_number="WH-1000XM5",
    )
    markets = MarketRepository(db_session)
    query = markets.get_or_create_query(
        product_id=product.id,
        query_text="Sony WH-1000XM5",
        query_type="KEYWORD",
        condition_filter="NEW",
    )
    response = {
        "total": 999_999,
        "itemSummaries": [
            _item("t36-1", "10.00"),
            _item("t36-2", "11.00"),
            _item("t36-3", "12.00"),
            _item("t36-4", "13.00"),
            _item("t36-outlier", "1000.00"),
        ],
    }
    client = EbayStub(response)

    summary = EbayService(
        db_session,
        client,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, ebay_enabled=True),
    ).refresh_listings([query.id])

    listings = list(
        db_session.scalars(
            select(EbayListing)
            .where(EbayListing.query_id == query.id)
            .order_by(EbayListing.external_item_id)
        )
    )
    snapshots = list(
        db_session.scalars(
            select(EbayListingSnapshot).join(EbayListing).where(EbayListing.query_id == query.id)
        )
    )
    metric = db_session.scalar(
        select(MarketResearchMetric)
        .where(
            MarketResearchMetric.query_id == query.id,
            MarketResearchMetric.source == "EBAY_BROWSE",
        )
        .order_by(MarketResearchMetric.id.desc())
        .limit(1)
    )

    assert summary.queries_checked == 1
    assert summary.listings_saved == 5
    assert summary.fallback_to_csv is False
    assert client.calls == [("Sony WH-1000XM5", None)]
    assert len(listings) == 5
    assert len(snapshots) == 5
    assert listings[0].condition_normalized == "new"
    assert listings[0].seller_country == "US"
    assert snapshots[0].shipping_usd == Decimal("5.000000")
    assert metric is not None
    assert metric.active_count == 5
    assert metric.median_sold_price == Decimal("11.5000")
    assert metric.average_shipping == Decimal("5.0000")


def test_disabled_api_keeps_existing_data_and_records_fallback_audit(
    db_session: Session,
    clean_db: None,
    caplog: Any,
) -> None:
    markets = MarketRepository(db_session)
    query = markets.get_or_create_query(
        query_text="existing CSV research",
        query_type="PRODUCT_RESEARCH",
    )
    observed_at = datetime(2026, 8, 8, tzinfo=UTC).replace(tzinfo=None)
    existing = markets.upsert_ebay_listing(
        query_id=query.id,
        source="MANUAL_CSV",
        external_item_id="t36-existing",
        title="Existing CSV listing",
        match_method="EXTERNAL_KEY",
        match_confidence=Decimal(1),
        last_seen_at=observed_at,
    )
    markets.add_listing_snapshot(
        listing_id=existing.id,
        price_usd=Decimal("49.99"),
        captured_at=observed_at,
    )
    markets.add_research_metric(
        query_id=query.id,
        source="PRODUCT_RESEARCH",
        period_days=90,
        active_count=12,
        median_sold_price=Decimal("44.50"),
        currency="USD",
        researched_at=observed_at,
    )
    before_listing_count = db_session.scalar(select(func.count(EbayListing.id)))
    before_metric_count = db_session.scalar(select(func.count(MarketResearchMetric.id)))

    summary = EbayService(
        db_session,
        None,
        settings=Settings(_env_file=None, ebay_enabled=False),
    ).refresh_listings([query.id])

    assert summary.fallback_to_csv is True
    assert summary.listings_saved == 0
    assert db_session.scalar(select(func.count(EbayListing.id))) == before_listing_count
    assert db_session.scalar(select(func.count(MarketResearchMetric.id))) == before_metric_count
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.action == "fallback_to_csv")
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.after_value is not None
    assert audit.after_value["mode"] == "CSV"
    assert "falling back to csv" in caplog.text.lower()
