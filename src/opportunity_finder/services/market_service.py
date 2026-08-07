"""Application service for refreshing domestic supplier prices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.clients.rakuten_ichiba import RakutenIchibaClient
from opportunity_finder.clients.rakuten_product import RakutenProductClient
from opportunity_finder.clients.yahoo_shopping import YahooShoppingClient
from opportunity_finder.db.models import Product
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository
from opportunity_finder.domain.models import SupplierOffer
from opportunity_finder.normalizers.rakuten_normalizer import (
    normalize_ichiba_response,
    normalize_product_response,
)
from opportunity_finder.normalizers.yahoo_normalizer import normalize_yahoo_response
from opportunity_finder.services.matching_service import MatchingService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketRefreshSummary:
    """Counts produced by one domestic-market refresh."""

    products_checked: int
    offers_matched: int
    yahoo_errors: int
    rakuten_errors: int


@dataclass(frozen=True, slots=True)
class _ProductMatchTarget:
    """Expose a database product through ``MatchingService``'s protocol."""

    product: Product
    jan_code: str | None
    brand: str | None
    model_number: str | None
    title: str
    condition: str
    unit_count: int

    @classmethod
    def from_product(cls, product: Product) -> _ProductMatchTarget:
        return cls(
            product=product,
            jan_code=product.jan_code,
            brand=product.brand,
            model_number=product.model_number,
            title=product.original_name,
            condition="new",
            unit_count=product.unit_count,
        )


@dataclass(frozen=True, slots=True)
class _OfferMatchCandidate:
    """Expose a normalized supplier offer through the matching protocol."""

    jan_code: str | None
    brand: str | None
    model_number: str | None
    title: str
    condition: str = "new"
    unit_count: int = 1

    @classmethod
    def from_offer(cls, offer: SupplierOffer) -> _OfferMatchCandidate:
        return cls(
            jan_code=offer.jan_code,
            brand=offer.brand,
            model_number=offer.model_number,
            title=offer.title,
        )


class MarketService:
    """Fetch, match, and persist prices from Yahoo! Shopping and Rakuten.

    The caller owns the SQLAlchemy transaction. External-provider failures are
    logged and counted independently so existing database prices remain usable.
    """

    def __init__(
        self,
        session: Session,
        yahoo_client: YahooShoppingClient,
        rakuten_ichiba_client: RakutenIchibaClient,
        rakuten_product_client: RakutenProductClient,
    ) -> None:
        self._session = session
        self._products = ProductRepository(session)
        self._suppliers = SupplierRepository(session)
        self._matching = MatchingService()
        self._yahoo = yahoo_client
        self._rakuten_ichiba = rakuten_ichiba_client
        self._rakuten_product = rakuten_product_client

    def refresh_domestic_prices(self, product_ids: list[int] | None = None) -> MarketRefreshSummary:
        """Refresh matching supplier offers without failing on one provider."""
        products = self._load_products(product_ids)
        offers: dict[tuple[str, str], SupplierOffer] = {}
        yahoo_errors = 0
        rakuten_errors = 0

        for product in products:
            query = _search_query(product)

            yahoo_offers, failed = self._fetch_yahoo(product, query)
            yahoo_errors += int(failed)
            _add_unique_offers(offers, yahoo_offers)

            ichiba_offers, failed = self._fetch_rakuten_ichiba(product, query)
            rakuten_errors += int(failed)
            _add_unique_offers(offers, ichiba_offers)

            if product.jan_code:
                product_offers, failed = self._fetch_rakuten_product(product)
                rakuten_errors += int(failed)
                _add_unique_offers(offers, product_offers)

        targets = [_ProductMatchTarget.from_product(product) for product in products]
        offers_matched = 0
        for offer in offers.values():
            target, match_method, confidence = self._matching.find_best_match(
                _OfferMatchCandidate.from_offer(offer),
                targets,
            )
            if not isinstance(target, _ProductMatchTarget):
                continue

            supplier_item = self._suppliers.upsert_supplier_item(
                product_id=target.product.id,
                source=offer.source,
                external_item_id=offer.external_item_id,
                title=offer.title,
                jan_code=offer.jan_code,
                brand=offer.brand,
                model_number=offer.model_number,
                match_method=match_method,
                match_confidence=confidence,
                is_active=offer.available,
                last_seen_at=offer.captured_at,
                raw_payload=offer.raw_payload,
            )
            self._suppliers.add_price_snapshot(
                supplier_item_id=supplier_item.id,
                item_price_jpy=offer.item_price_jpy,
                domestic_shipping_jpy=offer.domestic_shipping_jpy,
                points_value_jpy=offer.points_value_jpy,
                coupon_value_jpy=offer.coupon_value_jpy,
                available=offer.available,
                effective_cost_jpy=offer.effective_cost_jpy,
                captured_at=offer.captured_at,
                raw_payload=offer.raw_payload,
            )
            offers_matched += 1

        return MarketRefreshSummary(
            products_checked=len(products),
            offers_matched=offers_matched,
            yahoo_errors=yahoo_errors,
            rakuten_errors=rakuten_errors,
        )

    def _load_products(self, product_ids: list[int] | None) -> list[Product]:
        if product_ids is None:
            requested_ids = list(
                self._session.scalars(select(Product.id).order_by(Product.id)).all()
            )
        else:
            requested_ids = list(dict.fromkeys(product_ids))

        products: list[Product] = []
        for product_id in requested_ids:
            product = self._products.get_by_id(product_id)
            if product is not None and _has_matching_identifier(product):
                products.append(product)
        return products

    def _fetch_yahoo(self, product: Product, query: str) -> tuple[list[SupplierOffer], bool]:
        try:
            raw_response = self._yahoo.search(jan_code=product.jan_code, query=query)
            return normalize_yahoo_response(raw_response), False
        # Provider adapters may surface transport, status, or validation errors.
        except Exception as exc:  # noqa: BLE001
            _log_provider_error("YAHOO", product.id, exc)
            return [], True

    def _fetch_rakuten_ichiba(
        self, product: Product, query: str
    ) -> tuple[list[SupplierOffer], bool]:
        try:
            raw_response = self._rakuten_ichiba.search_by_keyword(query)
            return normalize_ichiba_response(raw_response), False
        # Isolate every provider call so one Rakuten API cannot stop the other.
        except Exception as exc:  # noqa: BLE001
            _log_provider_error("RAKUTEN_ICHIBA", product.id, exc)
            return [], True

    def _fetch_rakuten_product(self, product: Product) -> tuple[list[SupplierOffer], bool]:
        try:
            assert product.jan_code is not None
            raw_response = self._rakuten_product.search_by_jan(product.jan_code)
            return normalize_product_response(
                raw_response,
                jan_code=product.jan_code,
            ), False
        # See above: API client and response validation exceptions are recoverable here.
        except Exception as exc:  # noqa: BLE001
            _log_provider_error("RAKUTEN_PRODUCT", product.id, exc)
            return [], True


def _has_matching_identifier(product: Product) -> bool:
    return any(
        value is not None and value.strip()
        for value in (product.jan_code, product.brand, product.model_number)
    )


def _search_query(product: Product) -> str:
    if product.model_number:
        return " ".join(part.strip() for part in (product.brand, product.model_number) if part)
    return product.original_name.strip()


def _add_unique_offers(
    collected: dict[tuple[str, str], SupplierOffer],
    new_offers: list[SupplierOffer],
) -> None:
    for offer in new_offers:
        collected.setdefault((offer.source, offer.external_item_id), offer)


def _log_provider_error(source: str, product_id: int, exc: Exception) -> None:
    logger.exception(
        "%s domestic price refresh failed for product %s",
        source,
        product_id,
        extra={
            "source": source,
            "product_id": product_id,
            "status": "error",
            "error_type": type(exc).__name__,
        },
    )


__all__ = ["MarketRefreshSummary", "MarketService"]
