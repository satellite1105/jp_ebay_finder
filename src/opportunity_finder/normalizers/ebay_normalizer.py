"""Validate and normalize eBay Browse item-summary responses."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _EbayModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class _EbayMoney(_EbayModel):
    value: Decimal = Field(ge=0)
    currency: str

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter code")
        return normalized


class _EbayShippingOption(_EbayModel):
    shipping_cost: _EbayMoney | None = Field(default=None, alias="shippingCost")


class _EbayItemLocation(_EbayModel):
    country: str | None = None


class _EbaySeller(_EbayModel):
    username: str | None = None
    country: str | None = None


class _EbayAvailability(_EbayModel):
    estimated_available_quantity: int | None = Field(
        default=None,
        alias="estimatedAvailableQuantity",
        ge=0,
    )


class _EbayAspect(_EbayModel):
    name: str
    value: str


class _EbayItemSummary(_EbayModel):
    item_id: str = Field(alias="itemId", min_length=1)
    title: str = Field(min_length=1)
    price: _EbayMoney
    item_web_url: str | None = Field(default=None, alias="itemWebUrl")
    condition: str | None = None
    item_location: _EbayItemLocation | None = Field(default=None, alias="itemLocation")
    seller: _EbaySeller | None = None
    shipping_options: list[_EbayShippingOption] = Field(
        default_factory=list,
        alias="shippingOptions",
    )
    estimated_availabilities: list[_EbayAvailability] = Field(
        default_factory=list,
        alias="estimatedAvailabilities",
    )
    localized_aspects: list[_EbayAspect] = Field(
        default_factory=list,
        alias="localizedAspects",
    )
    gtin: str | None = None


class _EbaySearchResponse(_EbayModel):
    item_summaries: list[_EbayItemSummary] = Field(
        default_factory=list,
        alias="itemSummaries",
    )
    total: int | None = Field(default=None, ge=0)


class NormalizedEbayListing(BaseModel):
    """Fields from one Browse result that can be persisted deterministically."""

    model_config = ConfigDict(frozen=True)

    external_item_id: str
    title: str
    item_url: str | None
    price_usd: Decimal = Field(ge=0)
    shipping_usd: Decimal = Field(ge=0)
    currency: str
    condition_raw: str | None
    condition_normalized: str | None
    seller_country: str | None
    seller_username: str | None
    quantity_available: int | None = Field(default=None, ge=0)
    gtin: str | None = None
    brand: str | None = None
    model_number: str | None = None
    captured_at: datetime
    raw_payload: dict[str, Any]

    @property
    def price(self) -> Decimal:
        """Compatibility-friendly shorthand for the normalized item price."""
        return self.price_usd

    @property
    def shipping(self) -> Decimal:
        """Compatibility-friendly shorthand for the normalized buyer shipping."""
        return self.shipping_usd


def normalize_ebay_response(
    raw_response: dict[str, Any],
    *,
    captured_at: datetime | None = None,
) -> list[NormalizedEbayListing]:
    """Validate raw Browse JSON before extracting listing and price fields."""
    response = _EbaySearchResponse.model_validate(raw_response)
    observed_at = captured_at or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    raw_items = raw_response.get("itemSummaries", [])
    listings: list[NormalizedEbayListing] = []
    for index, item in enumerate(response.item_summaries):
        aspects = {
            aspect.name.strip().casefold(): aspect.value.strip()
            for aspect in item.localized_aspects
        }
        listings.append(
            NormalizedEbayListing(
                external_item_id=item.item_id.strip(),
                title=item.title.strip(),
                item_url=_nonempty(item.item_web_url),
                price_usd=item.price.value,
                shipping_usd=_shipping_cost(item),
                currency=item.price.currency,
                condition_raw=_nonempty(item.condition),
                condition_normalized=normalize_ebay_condition(item.condition),
                seller_country=_seller_country(item),
                seller_username=(
                    _nonempty(item.seller.username) if item.seller is not None else None
                ),
                quantity_available=_available_quantity(item),
                gtin=_nonempty(item.gtin),
                brand=_aspect_value(aspects, "brand"),
                model_number=_aspect_value(
                    aspects,
                    "mpn",
                    "model",
                    "model number",
                ),
                captured_at=observed_at,
                raw_payload=deepcopy(raw_items[index]),
            )
        )
    return listings


def normalize_ebay_condition(value: str | None) -> str | None:
    """Map eBay's display condition to a compact comparison category."""
    normalized = _nonempty(value)
    if normalized is None:
        return None
    folded = normalized.casefold().replace("_", " ").replace("-", " ")
    if "refurbish" in folded:
        return "refurbished"
    if "parts" in folded or "not working" in folded:
        return "parts"
    if folded.startswith("new"):
        return "new"
    if "used" in folded or "pre owned" in folded:
        return "used"
    return "other"


def _shipping_cost(item: _EbayItemSummary) -> Decimal:
    matching_costs = [
        option.shipping_cost.value
        for option in item.shipping_options
        if option.shipping_cost is not None and option.shipping_cost.currency == item.price.currency
    ]
    return min(matching_costs, default=Decimal(0))


def _seller_country(item: _EbayItemSummary) -> str | None:
    seller_country = item.seller.country if item.seller is not None else None
    location_country = item.item_location.country if item.item_location is not None else None
    country = _nonempty(seller_country) or _nonempty(location_country)
    if country is None:
        return None
    normalized = country.upper()
    return normalized if len(normalized) == 2 and normalized.isalpha() else None


def _available_quantity(item: _EbayItemSummary) -> int | None:
    return next(
        (
            availability.estimated_available_quantity
            for availability in item.estimated_availabilities
            if availability.estimated_available_quantity is not None
        ),
        None,
    )


def _aspect_value(aspects: dict[str, str], *names: str) -> str | None:
    return next((_nonempty(aspects.get(name)) for name in names if aspects.get(name)), None)


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


__all__ = [
    "NormalizedEbayListing",
    "normalize_ebay_condition",
    "normalize_ebay_response",
]
