"""Validate and normalize Yahoo! Shopping item-search responses."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opportunity_finder.domain.models import SupplierOffer


class _YahooModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class _YahooPoint(_YahooModel):
    amount: int = Field(default=0, ge=0)
    bonus_amount: int = Field(default=0, alias="bonusAmount", ge=0)


class _YahooBrand(_YahooModel):
    name: str


class _YahooShipping(_YahooModel):
    code: int
    name: str


class _YahooHit(_YahooModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: int = Field(ge=0)
    in_stock: bool = Field(alias="inStock")
    jan_code: str | None = Field(default=None, alias="janCode")
    brand: _YahooBrand | None = None
    model_number: str | None = Field(default=None, alias="modelNumber")
    point: _YahooPoint | None = None
    shipping: _YahooShipping | None = None


class _YahooResponse(_YahooModel):
    hits: list[_YahooHit]
    total_results_available: int | None = Field(
        default=None,
        alias="totalResultsAvailable",
        ge=0,
    )
    total_results_returned: int | None = Field(
        default=None,
        alias="totalResultsReturned",
        ge=0,
    )
    first_results_position: int | None = Field(
        default=None,
        alias="firstResultsPosition",
        ge=0,
    )


def normalize_yahoo_response(
    raw: dict[str, Any],
    *,
    captured_at: datetime | None = None,
) -> list[SupplierOffer]:
    """Validate a raw Yahoo response and convert each hit to ``SupplierOffer``."""
    response = _YahooResponse.model_validate(raw)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    raw_hits = raw["hits"]
    offers: list[SupplierOffer] = []
    for hit, raw_hit in zip(response.hits, raw_hits, strict=True):
        point_value = 0
        if hit.point is not None:
            point_value = hit.point.amount + hit.point.bonus_amount

        offers.append(
            SupplierOffer(
                source="YAHOO",
                external_item_id=hit.code,
                title=hit.name,
                item_price_jpy=Decimal(hit.price),
                domestic_shipping_jpy=Decimal(0),
                points_value_jpy=Decimal(point_value),
                coupon_value_jpy=Decimal(0),
                available=hit.in_stock,
                jan_code=hit.jan_code or None,
                brand=hit.brand.name if hit.brand is not None else None,
                model_number=hit.model_number,
                captured_at=captured,
                raw_payload=deepcopy(raw_hit),
            )
        )
    return offers


__all__ = ["normalize_yahoo_response"]
