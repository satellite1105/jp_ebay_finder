"""Persistence operations for supplier items and their price history."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import SupplierItem, SupplierPriceSnapshot


class SupplierRepository:
    """Store and retrieve supplier data in a caller-owned session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_supplier_item_by_id(self, id: int) -> SupplierItem | None:
        """Return a supplier item by primary key."""
        return self.session.get(SupplierItem, id)

    def get_supplier_item(self, source: str, external_item_id: str) -> SupplierItem | None:
        """Return a supplier item by its source-specific identity."""
        statement = select(SupplierItem).where(
            SupplierItem.source == source,
            SupplierItem.external_item_id == external_item_id,
        )
        return self.session.scalar(statement)

    def list_supplier_items_for_product(
        self, product_id: int, *, active_only: bool = True
    ) -> list[SupplierItem]:
        """Return supplier items linked to a product."""
        statement = select(SupplierItem).where(SupplierItem.product_id == product_id)
        if active_only:
            statement = statement.where(SupplierItem.is_active.is_(True))
        statement = statement.order_by(SupplierItem.source, SupplierItem.id)
        return list(self.session.scalars(statement))

    def upsert_supplier_item(
        self,
        *,
        product_id: int,
        source: str,
        external_item_id: str,
        title: str,
        match_method: str,
        match_confidence: Decimal,
        shop_name: str | None = None,
        item_url: str | None = None,
        jan_code: str | None = None,
        brand: str | None = None,
        model_number: str | None = None,
        is_active: bool = True,
        first_seen_at: datetime | None = None,
        last_seen_at: datetime | None = None,
        raw_payload: dict[str, Any] | list[Any] | None = None,
    ) -> SupplierItem:
        """Insert or update a supplier item keyed by source and external ID."""
        item = self.get_supplier_item(source, external_item_id)
        if item is None:
            first_seen = _initial_seen_at(first_seen_at, last_seen_at)
            item = SupplierItem(
                product_id=product_id,
                source=source,
                external_item_id=external_item_id,
                shop_name=shop_name,
                title=title,
                item_url=item_url,
                jan_code=jan_code,
                brand=brand,
                model_number=model_number,
                match_method=match_method,
                match_confidence=match_confidence,
                is_active=is_active,
                first_seen_at=first_seen,
                last_seen_at=(
                    _as_utc_naive(last_seen_at) if last_seen_at is not None else first_seen
                ),
                raw_payload=raw_payload,
            )
            self.session.add(item)
        else:
            item.product_id = product_id
            item.shop_name = shop_name
            item.title = title
            item.item_url = item_url
            item.jan_code = jan_code
            item.brand = brand
            item.model_number = model_number
            item.match_method = match_method
            item.match_confidence = match_confidence
            item.is_active = is_active
            item.last_seen_at = (
                _as_utc_naive(last_seen_at) if last_seen_at is not None else _utc_now()
            )
            item.raw_payload = raw_payload

        self.session.flush()
        return item

    def add_price_snapshot(
        self,
        *,
        supplier_item_id: int,
        item_price_jpy: Decimal,
        domestic_shipping_jpy: Decimal = Decimal(0),
        points_value_jpy: Decimal = Decimal(0),
        coupon_value_jpy: Decimal = Decimal(0),
        available: bool,
        effective_cost_jpy: Decimal,
        captured_at: datetime,
        raw_payload: dict[str, Any] | list[Any] | None = None,
    ) -> SupplierPriceSnapshot:
        """Append a supplier price observation, including its effective cost."""
        snapshot = SupplierPriceSnapshot(
            supplier_item_id=supplier_item_id,
            item_price_jpy=item_price_jpy,
            domestic_shipping_jpy=domestic_shipping_jpy,
            points_value_jpy=points_value_jpy,
            coupon_value_jpy=coupon_value_jpy,
            available=available,
            effective_cost_jpy=effective_cost_jpy,
            captured_at=_as_utc_naive(captured_at),
            raw_payload=raw_payload,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def get_latest_price_snapshot(self, supplier_item_id: int) -> SupplierPriceSnapshot | None:
        """Return the most recently captured price for a supplier item."""
        statement = (
            select(SupplierPriceSnapshot)
            .where(SupplierPriceSnapshot.supplier_item_id == supplier_item_id)
            .order_by(
                SupplierPriceSnapshot.captured_at.desc(),
                SupplierPriceSnapshot.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(statement)


def _initial_seen_at(first_seen_at: datetime | None, last_seen_at: datetime | None) -> datetime:
    if first_seen_at is not None:
        return _as_utc_naive(first_seen_at)
    if last_seen_at is not None:
        return _as_utc_naive(last_seen_at)
    return _utc_now()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
