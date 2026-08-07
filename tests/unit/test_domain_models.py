from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from opportunity_finder.domain.models import (
    MarketResearchInput,
    ProductInput,
    ProfitInput,
    ShippingQuote,
    SupplierOffer,
)


def valid_product_input(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "external_key": "product-1",
        "jan_code": "4901234567890",
        "title": "Test product",
        "condition": "new",
        "source_cost_jpy": Decimal(1000),
        "weight_g": 100,
        "origin_country": "JP",
        "checked_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("field", ["source_cost_jpy", "source_shipping_jpy"])
def test_product_input_rejects_negative_money(field: str) -> None:
    with pytest.raises(ValidationError):
        ProductInput(**valid_product_input(**{field: Decimal("-0.0001")}))


@pytest.mark.parametrize("jan_code", ["1234567", "123456789", "490123456789A"])
def test_product_input_rejects_invalid_jan_pattern(jan_code: str) -> None:
    with pytest.raises(ValidationError):
        ProductInput(**valid_product_input(jan_code=jan_code))


@pytest.mark.parametrize("jan_code", ["12345678", "4901234567890", None])
def test_product_input_accepts_supported_jan_lengths(jan_code: str | None) -> None:
    product = ProductInput(**valid_product_input(jan_code=jan_code))

    assert product.jan_code == jan_code


@pytest.mark.parametrize("origin_country", ["J", "JPN", "jp", "J1"])
def test_product_input_rejects_invalid_origin_country(origin_country: str) -> None:
    with pytest.raises(ValidationError):
        ProductInput(**valid_product_input(origin_country=origin_country))


def test_product_input_requires_timezone_aware_checked_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ProductInput(**valid_product_input(checked_at=datetime(2026, 1, 1)))  # noqa: DTZ001


def test_supplier_offer_calculates_effective_cost() -> None:
    offer = SupplierOffer(
        source="YAHOO",
        external_item_id="item-1",
        title="Test offer",
        item_price_jpy=Decimal(1000),
        domestic_shipping_jpy=Decimal(500),
        points_value_jpy=Decimal(100),
        coupon_value_jpy=Decimal(200),
        available=True,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert offer.effective_cost_jpy == Decimal(1200)


@pytest.mark.parametrize("sell_through_rate", [Decimal("-0.01"), Decimal("1.01")])
def test_market_research_rejects_rate_outside_zero_to_one(
    sell_through_rate: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        MarketResearchInput(
            external_key="product-1",
            search_query="Test product",
            lookback_days=30,
            sell_through_rate=sell_through_rate,
            checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_shipping_quote_rejects_non_two_letter_destination_country() -> None:
    with pytest.raises(ValidationError):
        ShippingQuote(
            profile_code="standard",
            destination_country="USA",
            min_weight_g=0,
            max_weight_g=1000,
            service_name="Tracked",
            shipping_jpy=Decimal(2000),
            tracking=True,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_profit_input_rejects_zero_exchange_rate_and_cash_required() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProfitInput(
            item_price_usd=Decimal(10),
            exchange_rate_jpy_per_usd=Decimal(0),
            source_item_cost_jpy=Decimal(1000),
            marketplace_fee_rate=Decimal("0.1"),
            cash_required_before_sale_jpy=Decimal(0),
        )

    assert exc_info.value.error_count() == 2
