"""Candidate decision rules, evaluated in strict priority order."""

from decimal import Decimal

from opportunity_finder.domain.compliance import (
    is_blocked,
)
from opportunity_finder.domain.compliance import (
    needs_review as compliance_needs_review,
)
from opportunity_finder.domain.models import ComplianceDecision, Decision


def _decimal_threshold(thresholds: dict, name: str) -> Decimal:
    """Read a numeric threshold without introducing binary floating-point arithmetic."""
    return Decimal(str(thresholds[name]))


def determine_decision(
    compliance: ComplianceDecision,
    has_required_data: bool,
    source_data_age_days: int | None,
    market_data_age_days: int | None,
    sold_90d: int | None,
    sell_through_rate: Decimal | None,
    base_profit_jpy: Decimal,
    base_margin: Decimal,
    conservative_profit_jpy: Decimal,
    confidence_score: Decimal,
    is_first_purchase: bool,
    has_test_purchase_history: bool,
    has_replenish_history: bool,
    thresholds: dict,
) -> tuple[Decision, list[str]]:
    """Return the highest-priority candidate decision and its reason codes."""
    if is_blocked(compliance):
        return "BLOCKED", ["COMPLIANCE_BLOCKED"]

    if not has_required_data or any(
        value is None
        for value in (
            source_data_age_days,
            market_data_age_days,
            sold_90d,
            sell_through_rate,
        )
    ):
        return "MISSING_DATA", ["REQUIRED_DATA_MISSING"]

    stale_reasons: list[str] = []
    if source_data_age_days > thresholds["maximum_source_data_age_days"]:
        stale_reasons.append("SOURCE_DATA_STALE")
    if market_data_age_days > thresholds["maximum_market_data_age_days"]:
        stale_reasons.append("MARKET_DATA_STALE")
    if stale_reasons:
        return "STALE_DATA", stale_reasons

    if compliance_needs_review(compliance):
        return "REVIEW_COMPLIANCE", ["COMPLIANCE_REVIEW_REQUIRED"]

    demand_reasons: list[str] = []
    if sold_90d < thresholds["minimum_sold_90d"]:
        demand_reasons.append("SOLD_90D_BELOW_MINIMUM")
    if sell_through_rate < _decimal_threshold(thresholds, "minimum_sell_through_rate"):
        demand_reasons.append("SELL_THROUGH_RATE_BELOW_MINIMUM")
    if demand_reasons:
        return "LOW_DEMAND", demand_reasons

    profit_reasons: list[str] = []
    if base_profit_jpy < _decimal_threshold(thresholds, "minimum_base_profit_jpy"):
        profit_reasons.append("BASE_PROFIT_BELOW_MINIMUM")
    if base_margin < _decimal_threshold(thresholds, "minimum_base_margin"):
        profit_reasons.append("BASE_MARGIN_BELOW_MINIMUM")
    if conservative_profit_jpy < _decimal_threshold(thresholds, "minimum_conservative_profit_jpy"):
        profit_reasons.append("CONSERVATIVE_PROFIT_BELOW_MINIMUM")
    if profit_reasons:
        return "LOW_PROFIT", profit_reasons

    if confidence_score < _decimal_threshold(thresholds, "minimum_confidence_score"):
        return "WATCH", ["CONFIDENCE_BELOW_MINIMUM"]

    if has_replenish_history:
        return "REPLENISH", ["REPLENISH_HISTORY"]
    if has_test_purchase_history:
        return "BUY_TEST_2", ["TEST_PURCHASE_SUCCESSFUL"]
    if is_first_purchase:
        return "BUY_TEST_1", ["FIRST_PURCHASE"]
    return "WATCH", ["PURCHASE_STAGE_UNDETERMINED"]
