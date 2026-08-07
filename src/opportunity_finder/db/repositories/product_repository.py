"""Persistence operations for the product catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import Product


class ProductRepository:
    """Store and retrieve :class:`Product` rows in a caller-owned session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, id: int) -> Product | None:
        """Return a product by primary key."""
        return self.session.get(Product, id)

    def get_by_jan(self, jan_code: str) -> Product | None:
        """Return the product identified by a JAN code."""
        statement = select(Product).where(Product.jan_code == jan_code)
        return self.session.scalar(statement)

    def get_by_internal_sku(self, internal_sku: str) -> Product | None:
        """Return the product identified by an internal SKU."""
        statement = select(Product).where(Product.internal_sku == internal_sku)
        return self.session.scalar(statement)

    def find_by_brand_and_model(self, brand: str, model_number: str) -> list[Product]:
        """Return products matching both brand and model number."""
        statement = (
            select(Product)
            .where(Product.brand == brand, Product.model_number == model_number)
            .order_by(Product.id)
        )
        return list(self.session.scalars(statement))

    def get_or_create(
        self,
        jan_code: str | None,
        *,
        normalized_name: str,
        original_name: str,
        internal_sku: str | None = None,
        brand: str | None = None,
        model_number: str | None = None,
        category: str | None = None,
        origin_country: str | None = None,
        unit_count: int = 1,
        weight_g: int | None = None,
        package_length_mm: int | None = None,
        package_width_mm: int | None = None,
        package_height_mm: int | None = None,
        repeatable_supply: bool = False,
        compliance_status: str = "NEEDS_REVIEW",
        compliance_flags: dict[str, Any] | list[Any] | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> Product:
        """Return the product for ``jan_code``, creating it when absent.

        When JAN is null, ``internal_sku`` is used as the fallback identity because
        MySQL permits multiple null values in the JAN unique index.
        """
        if jan_code is not None:
            existing = self.get_by_jan(jan_code)
            if existing is not None:
                return existing
        elif internal_sku is not None:
            existing = self.get_by_internal_sku(internal_sku)
            if existing is not None:
                return existing

        created = _as_utc_naive(created_at) if created_at is not None else _utc_now()
        updated = _as_utc_naive(updated_at) if updated_at is not None else created
        product = Product(
            jan_code=jan_code,
            internal_sku=internal_sku,
            normalized_name=normalized_name,
            original_name=original_name,
            brand=brand,
            model_number=model_number,
            category=category,
            origin_country=origin_country,
            unit_count=unit_count,
            weight_g=weight_g,
            package_length_mm=package_length_mm,
            package_width_mm=package_width_mm,
            package_height_mm=package_height_mm,
            repeatable_supply=repeatable_supply,
            compliance_status=compliance_status,
            compliance_flags=compliance_flags,
            notes=notes,
            created_at=created,
            updated_at=updated,
        )
        self.session.add(product)
        self.session.flush()
        return product


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
