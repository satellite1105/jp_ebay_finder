"""Application service for refreshing active eBay listings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from opportunity_finder.clients.ebay_browse import (
    EbayAccessDeniedError,
    EbayBrowseClient,
    EbayBrowseDisabledError,
)
from opportunity_finder.config import Settings
from opportunity_finder.db.models import MarketQuery
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.run_repository import RunRepository
from opportunity_finder.domain.matching import match_products
from opportunity_finder.normalizers.ebay_normalizer import (
    NormalizedEbayListing,
    normalize_ebay_condition,
    normalize_ebay_response,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EbayRefreshSummary:
    """Counts and mode selected by one eBay refresh."""

    queries_checked: int
    listings_saved: int
    fallback_to_csv: bool


class EbayService:
    """Fetch and persist Browse results while retaining CSV data on access denial.

    The caller owns the SQLAlchemy transaction. A disabled or unauthorized Browse
    integration records the fallback in the same transaction without deleting or
    replacing any existing listing or Product Research data.
    """

    def __init__(
        self,
        session: Session,
        ebay_client: EbayBrowseClient | None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._client = ebay_client
        self._markets = MarketRepository(session)
        self._products = ProductRepository(session)
        self._runs = RunRepository(session)
        if settings is not None:
            self._enabled = settings.ebay_enabled
        elif ebay_client is not None:
            self._enabled = bool(getattr(ebay_client, "enabled", True))
        else:
            self._enabled = Settings().ebay_enabled

    def refresh_listings(self, query_ids: list[int]) -> EbayRefreshSummary:
        """Refresh selected queries, falling back to existing CSV/DB data when needed."""
        requested_ids = list(dict.fromkeys(query_ids))
        if not self._enabled:
            return self._fallback(
                reason="eBay Browse is disabled by configuration",
                query_ids=requested_ids,
            )
        if self._client is None:
            return self._fallback(
                reason="eBay Browse client is unavailable",
                query_ids=requested_ids,
            )

        queries_checked = 0
        pending_results: list[tuple[MarketQuery, list[NormalizedEbayListing]]] = []
        for query_id in requested_ids:
            query = self._markets.get_query(query_id)
            if query is None or not query.enabled:
                continue
            queries_checked += 1
            try:
                raw_response = self._search(query)
            except (EbayAccessDeniedError, EbayBrowseDisabledError):
                return self._fallback(
                    reason="eBay Browse access denied; existing CSV data retained",
                    query_ids=requested_ids,
                    entity_id=query.id,
                    queries_checked=queries_checked,
                )

            normalized = normalize_ebay_response(raw_response)
            pending_results.append((query, normalized))

        listings_saved = sum(
            self._save_query_results(query, normalized) for query, normalized in pending_results
        )

        return EbayRefreshSummary(
            queries_checked=queries_checked,
            listings_saved=listings_saved,
            fallback_to_csv=False,
        )

    def _search(self, query: MarketQuery) -> dict:
        assert self._client is not None
        query_type = query.query_type.strip().upper()
        if query_type in {"GTIN", "JAN", "EAN", "UPC", "ISBN"}:
            return self._client.search(gtin=query.query_text)
        return self._client.search(keyword=query.query_text)

    def _save_query_results(
        self,
        query: MarketQuery,
        normalized: list[NormalizedEbayListing],
    ) -> int:
        unique_results = {item.external_item_id: item for item in normalized}
        saved: list[NormalizedEbayListing] = []
        for item in unique_results.values():
            match_method, match_confidence = self._match(item, query)
            observed_at = _as_utc_naive(item.captured_at)
            listing = self._markets.upsert_ebay_listing(
                query_id=query.id,
                product_id=query.product_id,
                source="EBAY_BROWSE",
                external_item_id=item.external_item_id,
                title=item.title,
                item_url=item.item_url,
                condition_raw=item.condition_raw,
                condition_normalized=item.condition_normalized,
                seller_country=item.seller_country,
                match_method=match_method,
                match_confidence=match_confidence,
                is_active=True,
                last_seen_at=observed_at,
            )
            self._markets.add_listing_snapshot(
                listing_id=listing.id,
                price_usd=item.price_usd,
                shipping_usd=item.shipping_usd,
                currency=item.currency,
                quantity_available=item.quantity_available,
                captured_at=observed_at,
                raw_payload=item.raw_payload,
            )
            saved.append(item)

        self._save_active_listing_metric(query.id, saved)
        return len(saved)

    def _match(
        self,
        item: NormalizedEbayListing,
        query: MarketQuery,
    ) -> tuple[str, Decimal]:
        if query.product_id is None:
            return "query", Decimal(100)
        product = self._products.get_by_id(query.product_id)
        if product is None:
            return "none", Decimal(0)

        expected_condition = (
            normalize_ebay_condition(query.condition_filter) or item.condition_normalized or "other"
        )
        return match_products(
            candidate_jan=item.gtin,
            candidate_brand=item.brand,
            candidate_model_number=item.model_number,
            candidate_title=item.title,
            candidate_condition=item.condition_normalized or expected_condition,
            candidate_unit_count=1,
            target_jan=product.jan_code,
            target_brand=product.brand,
            target_model_number=product.model_number,
            target_title=product.original_name,
            target_condition=expected_condition,
            target_unit_count=product.unit_count,
        )

    def _save_active_listing_metric(
        self,
        query_id: int,
        listings: list[NormalizedEbayListing],
    ) -> None:
        captured_at = (
            _as_utc_naive(listings[0].captured_at)
            if listings
            else datetime.now(UTC).replace(tzinfo=None)
        )
        currency = listings[0].currency if listings else "USD"
        currency_listings = [item for item in listings if item.currency == currency]
        filtered = _exclude_iqr_price_outliers(currency_listings)
        prices = [item.price_usd for item in filtered]
        shipping = [item.shipping_usd for item in filtered]
        seller_names = {item.seller_username for item in listings if item.seller_username}

        self._markets.add_research_metric(
            query_id=query_id,
            source="EBAY_BROWSE",
            period_days=0,
            active_count=len(listings),
            seller_count=len(seller_names) if seller_names else None,
            median_sold_price=_median(prices),
            average_sold_price=_mean(prices),
            minimum_sold_price=min(prices) if prices else None,
            maximum_sold_price=max(prices) if prices else None,
            average_shipping=_mean(shipping),
            currency=currency,
            researched_at=captured_at,
            notes=(
                "Active Browse listing statistics; price outliers excluded by IQR; "
                f"actual saved listing count={len(listings)}"
            ),
        )

    def _fallback(
        self,
        *,
        reason: str,
        query_ids: list[int],
        entity_id: int | None = None,
        queries_checked: int = 0,
        listings_saved: int = 0,
    ) -> EbayRefreshSummary:
        logger.warning(
            "eBay refresh falling back to CSV and existing database data: %s",
            reason,
            extra={"mode": "CSV", "fallback": True},
        )
        self._runs.add_audit_log(
            entity_type="ebay_refresh",
            entity_id=entity_id,
            action="fallback_to_csv",
            actor="EbayService",
            after_value={"mode": "CSV", "query_ids": query_ids},
            reason=reason,
        )
        return EbayRefreshSummary(
            queries_checked=queries_checked,
            listings_saved=listings_saved,
            fallback_to_csv=True,
        )


def _exclude_iqr_price_outliers(
    listings: list[NormalizedEbayListing],
) -> list[NormalizedEbayListing]:
    if len(listings) < 4:
        return listings
    ordered_prices = sorted(item.price_usd for item in listings)
    first_quartile = _percentile(ordered_prices, Decimal("0.25"))
    third_quartile = _percentile(ordered_prices, Decimal("0.75"))
    iqr = third_quartile - first_quartile
    lower_bound = first_quartile - Decimal("1.5") * iqr
    upper_bound = third_quartile + Decimal("1.5") * iqr
    return [item for item in listings if lower_bound <= item.price_usd <= upper_bound]


def _percentile(values: list[Decimal], fraction: Decimal) -> Decimal:
    position = Decimal(len(values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - Decimal(lower_index)
    return values[lower_index] + (values[upper_index] - values[lower_index]) * weight


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal(0)) / Decimal(len(values))


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


__all__ = ["EbayRefreshSummary", "EbayService"]
