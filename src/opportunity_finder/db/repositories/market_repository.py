"""Persistence helpers for market research data and eBay listings."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import (
    EbayListing,
    EbayListingSnapshot,
    MarketQuery,
    MarketResearchMetric,
)


def _utc_now() -> datetime:
    """Return a naive UTC timestamp suitable for the schema's DATETIME columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class MarketRepository:
    """Store and retrieve market queries, metrics, listings, and snapshots.

    Methods flush changes so generated primary keys and constraint violations are
    visible immediately. Transaction boundaries remain the caller's responsibility.
    """

    _QUERY_UPDATE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "product_id",
            "marketplace",
            "query_text",
            "category_id",
            "condition_filter",
            "query_type",
            "enabled",
        }
    )
    _RESEARCH_METRIC_UPDATE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "query_id",
            "source",
            "period_days",
            "sold_count",
            "active_count",
            "seller_count",
            "median_sold_price",
            "average_sold_price",
            "minimum_sold_price",
            "maximum_sold_price",
            "average_shipping",
            "currency",
            "sell_through_rate",
            "researched_at",
            "valid_until",
            "notes",
            "import_batch_id",
        }
    )
    _LISTING_SNAPSHOT_UPDATE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "ebay_listing_id",
            "price_usd",
            "shipping_usd",
            "currency",
            "quantity_available",
            "captured_at",
            "raw_payload",
        }
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_query(self, query_id: int) -> MarketQuery | None:
        """Return a market query by primary key."""
        return self.session.get(MarketQuery, query_id)

    def get_or_create_query(
        self,
        *,
        query_text: str,
        query_type: str,
        product_id: int | None = None,
        marketplace: str = "EBAY_US",
        category_id: str | None = None,
        condition_filter: str | None = None,
        enabled: bool = True,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> MarketQuery:
        """Return the query with the same search identity, creating it if absent.

        ``enabled`` and timestamps are mutable state rather than identity fields, so
        they are only applied when a new row is created.
        """
        statement = select(MarketQuery).where(
            MarketQuery.product_id == product_id,
            MarketQuery.marketplace == marketplace,
            MarketQuery.query_text == query_text,
            MarketQuery.category_id == category_id,
            MarketQuery.condition_filter == condition_filter,
            MarketQuery.query_type == query_type,
        )
        existing = self.session.scalar(statement)
        if existing is not None:
            return existing

        created_timestamp = created_at or _utc_now()
        query = MarketQuery(
            product_id=product_id,
            marketplace=marketplace,
            query_text=query_text,
            category_id=category_id,
            condition_filter=condition_filter,
            query_type=query_type,
            enabled=enabled,
            created_at=created_timestamp,
            updated_at=updated_at or created_timestamp,
        )
        self.session.add(query)
        self.session.flush()
        return query

    def update_query(self, query_id: int, **changes: Any) -> MarketQuery | None:
        """Update mutable query fields and return the row, or ``None`` if absent."""
        unknown_fields = changes.keys() - self._QUERY_UPDATE_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported market query fields: {names}")

        query = self.get_query(query_id)
        if query is None:
            return None
        for field, value in changes.items():
            setattr(query, field, value)
        query.updated_at = _utc_now()
        self.session.flush()
        return query

    def delete_query(self, query_id: int) -> bool:
        """Delete a market query without cascading its dependent rows."""
        query = self.get_query(query_id)
        if query is None:
            return False
        self.session.delete(query)
        self.session.flush()
        return True

    def add_research_metric(
        self,
        *,
        query_id: int,
        period_days: int,
        currency: str,
        researched_at: datetime,
        source: str = "PRODUCT_RESEARCH",
        sold_count: int | None = None,
        active_count: int | None = None,
        seller_count: int | None = None,
        median_sold_price: Decimal | None = None,
        average_sold_price: Decimal | None = None,
        minimum_sold_price: Decimal | None = None,
        maximum_sold_price: Decimal | None = None,
        average_shipping: Decimal | None = None,
        sell_through_rate: Decimal | None = None,
        valid_until: datetime | None = None,
        notes: str | None = None,
        import_batch_id: int | None = None,
    ) -> MarketResearchMetric:
        """Append a point-in-time Product Research metric."""
        metric = MarketResearchMetric(
            query_id=query_id,
            source=source,
            period_days=period_days,
            sold_count=sold_count,
            active_count=active_count,
            seller_count=seller_count,
            median_sold_price=median_sold_price,
            average_sold_price=average_sold_price,
            minimum_sold_price=minimum_sold_price,
            maximum_sold_price=maximum_sold_price,
            average_shipping=average_shipping,
            currency=currency,
            sell_through_rate=sell_through_rate,
            researched_at=researched_at,
            valid_until=valid_until,
            notes=notes,
            import_batch_id=import_batch_id,
        )
        self.session.add(metric)
        self.session.flush()
        return metric

    def get_research_metric(self, metric_id: int) -> MarketResearchMetric | None:
        """Return a research metric by primary key."""
        return self.session.get(MarketResearchMetric, metric_id)

    def get_latest_research_metric(self, query_id: int) -> MarketResearchMetric | None:
        """Return the newest metric for a query by ``researched_at``."""
        statement = (
            select(MarketResearchMetric)
            .where(MarketResearchMetric.query_id == query_id)
            .order_by(MarketResearchMetric.researched_at.desc(), MarketResearchMetric.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def update_research_metric(self, metric_id: int, **changes: Any) -> MarketResearchMetric | None:
        """Update a research metric and return it, or ``None`` if absent."""
        unknown_fields = changes.keys() - self._RESEARCH_METRIC_UPDATE_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported research metric fields: {names}")

        metric = self.get_research_metric(metric_id)
        if metric is None:
            return None
        for field, value in changes.items():
            setattr(metric, field, value)
        self.session.flush()
        return metric

    def delete_research_metric(self, metric_id: int) -> bool:
        """Delete one research metric if it exists."""
        metric = self.get_research_metric(metric_id)
        if metric is None:
            return False
        self.session.delete(metric)
        self.session.flush()
        return True

    def get_ebay_listing(self, listing_id: int) -> EbayListing | None:
        """Return an eBay listing by primary key."""
        return self.session.get(EbayListing, listing_id)

    def get_ebay_listing_by_external_id(
        self, *, source: str, external_item_id: str
    ) -> EbayListing | None:
        """Look up a listing using its database-enforced natural key."""
        statement = select(EbayListing).where(
            EbayListing.source == source,
            EbayListing.external_item_id == external_item_id,
        )
        return self.session.scalar(statement)

    def upsert_ebay_listing(
        self,
        *,
        query_id: int,
        external_item_id: str,
        title: str,
        match_method: str,
        match_confidence: Decimal,
        last_seen_at: datetime,
        source: str = "EBAY_BROWSE",
        product_id: int | None = None,
        item_url: str | None = None,
        condition_raw: str | None = None,
        condition_normalized: str | None = None,
        seller_country: str | None = None,
        is_active: bool = True,
        first_seen_at: datetime | None = None,
    ) -> EbayListing:
        """Insert or update a listing keyed by ``(source, external_item_id)``.

        On update, the original ``first_seen_at`` is retained while all current
        descriptive and matching fields are refreshed.
        """
        listing = self.get_ebay_listing_by_external_id(
            source=source, external_item_id=external_item_id
        )
        if listing is None:
            listing = EbayListing(
                query_id=query_id,
                product_id=product_id,
                source=source,
                external_item_id=external_item_id,
                title=title,
                item_url=item_url,
                condition_raw=condition_raw,
                condition_normalized=condition_normalized,
                seller_country=seller_country,
                match_method=match_method,
                match_confidence=match_confidence,
                is_active=is_active,
                first_seen_at=first_seen_at or last_seen_at,
                last_seen_at=last_seen_at,
            )
            self.session.add(listing)
        else:
            listing.query_id = query_id
            listing.product_id = product_id
            listing.title = title
            listing.item_url = item_url
            listing.condition_raw = condition_raw
            listing.condition_normalized = condition_normalized
            listing.seller_country = seller_country
            listing.match_method = match_method
            listing.match_confidence = match_confidence
            listing.is_active = is_active
            listing.last_seen_at = last_seen_at

        self.session.flush()
        return listing

    def get_active_listings(self, query_id: int) -> list[EbayListing]:
        """Return active listings for a query, newest observations first."""
        statement = (
            select(EbayListing)
            .where(EbayListing.query_id == query_id, EbayListing.is_active.is_(True))
            .order_by(EbayListing.last_seen_at.desc(), EbayListing.id.desc())
        )
        return list(self.session.scalars(statement))

    def delete_ebay_listing(self, listing_id: int) -> bool:
        """Delete a listing without cascading its snapshots."""
        listing = self.get_ebay_listing(listing_id)
        if listing is None:
            return False
        self.session.delete(listing)
        self.session.flush()
        return True

    def add_listing_snapshot(
        self,
        *,
        listing_id: int,
        price_usd: Decimal,
        captured_at: datetime,
        shipping_usd: Decimal = Decimal(0),
        currency: str = "USD",
        quantity_available: int | None = None,
        raw_payload: dict[str, Any] | list[Any] | None = None,
    ) -> EbayListingSnapshot:
        """Append a current-price snapshot for an eBay listing."""
        snapshot = EbayListingSnapshot(
            ebay_listing_id=listing_id,
            price_usd=price_usd,
            shipping_usd=shipping_usd,
            currency=currency,
            quantity_available=quantity_available,
            captured_at=captured_at,
            raw_payload=raw_payload,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def get_listing_snapshot(self, snapshot_id: int) -> EbayListingSnapshot | None:
        """Return a listing snapshot by primary key."""
        return self.session.get(EbayListingSnapshot, snapshot_id)

    def get_latest_listing_snapshot(self, listing_id: int) -> EbayListingSnapshot | None:
        """Return the newest listing snapshot by ``captured_at``."""
        statement = (
            select(EbayListingSnapshot)
            .where(EbayListingSnapshot.ebay_listing_id == listing_id)
            .order_by(EbayListingSnapshot.captured_at.desc(), EbayListingSnapshot.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def update_listing_snapshot(
        self, snapshot_id: int, **changes: Any
    ) -> EbayListingSnapshot | None:
        """Update a listing snapshot and return it, or ``None`` if absent."""
        unknown_fields = changes.keys() - self._LISTING_SNAPSHOT_UPDATE_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported listing snapshot fields: {names}")

        snapshot = self.get_listing_snapshot(snapshot_id)
        if snapshot is None:
            return None
        for field, value in changes.items():
            setattr(snapshot, field, value)
        self.session.flush()
        return snapshot

    def delete_listing_snapshot(self, snapshot_id: int) -> bool:
        """Delete one listing snapshot if it exists."""
        snapshot = self.get_listing_snapshot(snapshot_id)
        if snapshot is None:
            return False
        self.session.delete(snapshot)
        self.session.flush()
        return True
