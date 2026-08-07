from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Scenario = Literal["optimistic", "base", "conservative"]
Decision = Literal[
    "BLOCKED",
    "MISSING_DATA",
    "STALE_DATA",
    "REVIEW_COMPLIANCE",
    "LOW_DEMAND",
    "LOW_PROFIT",
    "WATCH",
    "BUY_TEST_1",
    "BUY_TEST_2",
    "REPLENISH",
]


class ProductInput(BaseModel):
    external_key: str
    jan_code: str | None = Field(default=None, pattern=r"^\d{8}(\d{5})?$")
    title: str
    brand: str | None = None
    model_number: str | None = None
    condition: Literal["new", "used"]
    source_cost_jpy: Decimal = Field(ge=0)
    source_shipping_jpy: Decimal = Field(default=Decimal(0), ge=0)
    weight_g: int = Field(gt=0)
    packed_weight_g: int | None = Field(default=None, gt=0)
    origin_country: str = Field(pattern=r"^[A-Z]{2}$")
    supplier_name: str | None = None
    supplier_url: str | None = None
    checked_at: datetime

    @field_validator("checked_at")
    @classmethod
    def require_timezone_aware_checked_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        return value


class SupplierOffer(BaseModel):
    source: str
    external_item_id: str
    title: str
    item_price_jpy: Decimal = Field(ge=0)
    domestic_shipping_jpy: Decimal = Field(default=Decimal(0), ge=0)
    points_value_jpy: Decimal = Field(default=Decimal(0), ge=0)
    coupon_value_jpy: Decimal = Field(default=Decimal(0), ge=0)
    available: bool
    jan_code: str | None = None
    brand: str | None = None
    model_number: str | None = None
    captured_at: datetime
    raw_payload: dict | None = None

    @property
    def effective_cost_jpy(self) -> Decimal:
        """最安値ではなく送料込み実質価格(F29)。"""
        return (
            self.item_price_jpy
            + self.domestic_shipping_jpy
            - self.points_value_jpy
            - self.coupon_value_jpy
        )


class MarketResearchInput(BaseModel):
    external_key: str
    search_query: str
    marketplace: str = "EBAY_US"
    condition: Literal["new", "used"] | None = None
    lookback_days: int = Field(gt=0)
    sold_count: int | None = Field(default=None, ge=0)
    active_count: int | None = Field(default=None, ge=0)
    median_sold_price_usd: Decimal | None = Field(default=None, ge=0)
    average_sold_price_usd: Decimal | None = Field(default=None, ge=0)
    median_buyer_shipping_usd: Decimal = Field(default=Decimal(0), ge=0)
    sell_through_rate: Decimal | None = Field(default=None, ge=0, le=1)
    checked_at: datetime
    notes: str | None = None


class FeeProfile(BaseModel):
    profile_code: str
    marketplace: str
    category_code: str | None = None
    variable_fee_rate: Decimal = Field(ge=0, le=1)
    international_fee_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)
    fixed_fee_currency: str
    fixed_fee_amount: Decimal = Field(ge=0)
    ad_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)
    return_reserve_rate: Decimal = Field(default=Decimal(0), ge=0, le=1)
    effective_from: datetime
    effective_to: datetime | None = None


class ShippingQuote(BaseModel):
    profile_code: str
    destination_country: str = Field(pattern=r"^[A-Z]{2}$")
    min_weight_g: int = Field(ge=0)
    max_weight_g: int = Field(gt=0)
    service_name: str
    shipping_jpy: Decimal = Field(ge=0)
    tracking: bool
    included_insurance_jpy: Decimal = Field(default=Decimal(0), ge=0)
    effective_from: datetime
    effective_to: datetime | None = None


class ScenarioMultipliers(BaseModel):
    sale_price_multiplier: Decimal
    exchange_rate_multiplier: Decimal
    shipping_multiplier: Decimal
    ad_rate_multiplier: Decimal
    return_rate_multiplier: Decimal


class ProfitInput(BaseModel):
    item_price_usd: Decimal = Field(ge=0)
    buyer_shipping_usd: Decimal = Field(default=Decimal(0), ge=0)
    exchange_rate_jpy_per_usd: Decimal = Field(gt=0)
    source_item_cost_jpy: Decimal = Field(ge=0)
    source_domestic_shipping_jpy: Decimal = Field(default=Decimal(0), ge=0)
    source_transport_jpy: Decimal = Field(default=Decimal(0), ge=0)
    packaging_jpy: Decimal = Field(default=Decimal(0), ge=0)
    international_shipping_jpy: Decimal = Field(default=Decimal(0), ge=0)
    duty_jpy: Decimal = Field(default=Decimal(0), ge=0)
    import_processing_jpy: Decimal = Field(default=Decimal(0), ge=0)
    international_fee_rate: Decimal = Field(default=Decimal(0), ge=0)
    currency_conversion_jpy: Decimal = Field(default=Decimal(0), ge=0)
    payment_fee_jpy: Decimal = Field(default=Decimal(0), ge=0)
    labor_cost_jpy: Decimal = Field(default=Decimal(0), ge=0)
    other_cost_jpy: Decimal = Field(default=Decimal(0), ge=0)
    marketplace_fee_rate: Decimal = Field(ge=0)
    marketplace_fixed_fee_jpy: Decimal = Field(default=Decimal(0), ge=0)
    fee_base_is_item_price_only: bool = True
    ad_rate: Decimal = Field(default=Decimal(0), ge=0)
    return_reserve_rate: Decimal = Field(default=Decimal(0), ge=0)
    cash_required_before_sale_jpy: Decimal = Field(gt=0)
    target_profit_jpy: Decimal = Field(default=Decimal(3000), ge=0)


class ProfitScenarioResult(BaseModel):
    scenario: Scenario
    buyer_total_usd: Decimal
    recognized_revenue_jpy: Decimal
    marketplace_fee_jpy: Decimal
    promoted_listing_jpy: Decimal
    return_reserve_jpy: Decimal
    total_cost_jpy: Decimal
    net_profit_jpy: Decimal
    net_margin: Decimal
    capital_efficiency: Decimal
    break_even_buyer_total_usd: Decimal
    target_price_usd: Decimal


class ComplianceDecision(BaseModel):
    compliance_status: Literal["approved", "review", "blocked", "needs_review"]
    flags: list[str] = Field(default_factory=list)


class OpportunityResult(BaseModel):
    product_id: int
    query_id: int
    scenarios: dict[Scenario, ProfitScenarioResult]
    opportunity_score: Decimal
    score_breakdown: dict[str, Decimal]
    confidence_score: Decimal
    confidence_breakdown: dict[str, Decimal]
    decision: Decision
    reason_codes: list[str]
    input_snapshot: dict
