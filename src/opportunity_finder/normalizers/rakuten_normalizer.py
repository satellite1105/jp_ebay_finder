"""Validated conversion of Rakuten API responses into supplier offers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opportunity_finder.domain.models import SupplierOffer

_JAN_PATTERN = re.compile(r"^\d{8}(?:\d{5})?$")


class _RakutenModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RakutenIchibaItem(_RakutenModel):
    item_code: str = Field(alias="itemCode", min_length=1)
    item_name: str = Field(alias="itemName", min_length=1)
    item_price: Decimal = Field(alias="itemPrice", ge=0)
    availability: int | bool
    postage_flag: int | None = Field(default=None, alias="postageFlag")
    shipping_price: Decimal = Field(default=Decimal(0), alias="shippingPrice", ge=0)
    point_rate: Decimal = Field(default=Decimal(0), alias="pointRate", ge=0)
    jan_code: str | None = Field(default=None, alias="janCode")
    brand_name: str | None = Field(default=None, alias="brandName")
    model_number: str | None = Field(default=None, alias="modelNumber")


class RakutenIchibaItemEnvelope(_RakutenModel):
    item: RakutenIchibaItem = Field(alias="Item")


class RakutenIchibaResponse(_RakutenModel):
    items: list[RakutenIchibaItemEnvelope] = Field(alias="Items")
    page: int | None = Field(default=None, ge=1)
    page_count: int | None = Field(default=None, alias="pageCount", ge=0)


class RakutenProduct(_RakutenModel):
    product_id: str = Field(alias="productId", min_length=1)
    product_name: str = Field(alias="productName", min_length=1)
    sales_min_price: Decimal = Field(alias="salesMinPrice", ge=0)
    brand_name: str | None = Field(default=None, alias="brandName")
    product_number: str | None = Field(default=None, alias="productNo")
    model_number: str | None = Field(default=None, alias="modelNumber")
    jan_code: str | None = Field(default=None, alias="janCode")


class RakutenProductEnvelope(_RakutenModel):
    product: RakutenProduct = Field(alias="Product")


class RakutenProductResponse(_RakutenModel):
    products: list[RakutenProductEnvelope] = Field(alias="Products")
    page: int | None = Field(default=None, ge=1)
    page_count: int | None = Field(default=None, alias="pageCount", ge=0)


def normalize_ichiba_response(
    raw_response: Mapping[str, Any],
    *,
    captured_at: datetime | None = None,
) -> list[SupplierOffer]:
    """Validate an Ichiba response and convert every item to an offer."""
    response = RakutenIchibaResponse.model_validate(raw_response)
    observed_at = captured_at or datetime.now(UTC)
    raw_items = raw_response["Items"]

    offers: list[SupplierOffer] = []
    for index, envelope in enumerate(response.items):
        item = envelope.item
        points_value = (item.item_price * item.point_rate / Decimal(100)).quantize(
            Decimal(1), rounding=ROUND_FLOOR
        )
        offers.append(
            SupplierOffer(
                source="RAKUTEN",
                external_item_id=item.item_code,
                title=item.item_name,
                item_price_jpy=item.item_price,
                domestic_shipping_jpy=item.shipping_price,
                points_value_jpy=points_value,
                available=bool(item.availability),
                jan_code=_valid_jan_or_none(item.jan_code),
                brand=item.brand_name,
                model_number=item.model_number,
                captured_at=observed_at,
                raw_payload=_raw_nested_payload(raw_items, index, "Item"),
            )
        )
    return offers


def normalize_product_response(
    raw_response: Mapping[str, Any],
    *,
    jan_code: str | None = None,
    captured_at: datetime | None = None,
) -> list[SupplierOffer]:
    """Validate a Product Search response and convert every product to an offer."""
    response = RakutenProductResponse.model_validate(raw_response)
    observed_at = captured_at or datetime.now(UTC)
    requested_jan = _valid_jan_or_none(jan_code)
    raw_products = raw_response["Products"]

    offers: list[SupplierOffer] = []
    for index, envelope in enumerate(response.products):
        product = envelope.product
        product_jan = _valid_jan_or_none(product.jan_code) or requested_jan
        offers.append(
            SupplierOffer(
                source="RAKUTEN",
                external_item_id=product.product_id,
                title=product.product_name,
                item_price_jpy=product.sales_min_price,
                available=product.sales_min_price > 0,
                jan_code=product_jan,
                brand=product.brand_name,
                model_number=product.model_number or product.product_number,
                captured_at=observed_at,
                raw_payload=_raw_nested_payload(raw_products, index, "Product"),
            )
        )
    return offers


def _valid_jan_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if _JAN_PATTERN.fullmatch(normalized) else None


def _raw_nested_payload(raw_entries: Any, index: int, wrapper_key: str) -> dict[str, Any]:
    """Copy a validated entry without replacing its original JSON scalar types."""
    entry = raw_entries[index]
    return dict(entry[wrapper_key])


__all__ = [
    "RakutenIchibaResponse",
    "RakutenProductResponse",
    "normalize_ichiba_response",
    "normalize_product_response",
]
