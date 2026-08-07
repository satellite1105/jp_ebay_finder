from decimal import Decimal

import pytest

from opportunity_finder.domain.compliance import is_blocked, needs_review
from opportunity_finder.domain.decisions import determine_decision
from opportunity_finder.domain.models import ComplianceDecision, Decision

DEFAULT_THRESHOLDS = {
    "minimum_base_profit_jpy": 3000,
    "minimum_base_margin": "0.25",
    "minimum_conservative_profit_jpy": 1000,
    "minimum_sold_90d": 5,
    "minimum_sell_through_rate": "0.15",
    "maximum_source_data_age_days": 7,
    "maximum_market_data_age_days": 90,
    "minimum_confidence_score": 60,
}


def decision_for(**overrides: object) -> tuple[Decision, list[str]]:
    arguments = {
        "compliance": ComplianceDecision(compliance_status="approved"),
        "has_required_data": True,
        "source_data_age_days": 7,
        "market_data_age_days": 90,
        "sold_90d": 5,
        "sell_through_rate": Decimal("0.15"),
        "base_profit_jpy": Decimal(3000),
        "base_margin": Decimal("0.25"),
        "conservative_profit_jpy": Decimal(1000),
        "confidence_score": Decimal(60),
        "is_first_purchase": True,
        "has_test_purchase_history": False,
        "has_replenish_history": False,
        "thresholds": DEFAULT_THRESHOLDS,
    }
    arguments.update(overrides)
    return determine_decision(**arguments)  # type: ignore[arg-type]


def test_blocked_is_absolute_priority_even_when_all_business_conditions_are_good() -> None:
    decision, reasons = decision_for(
        compliance=ComplianceDecision(compliance_status="blocked"),
        sold_90d=10_000,
        sell_through_rate=Decimal(1),
        base_profit_jpy=Decimal(1000000),
        base_margin=Decimal("0.99"),
        conservative_profit_jpy=Decimal(900000),
        confidence_score=Decimal(100),
        has_replenish_history=True,
    )

    assert decision == "BLOCKED"
    assert reasons == ["COMPLIANCE_BLOCKED"]


def test_missing_required_data_returns_missing_data() -> None:
    decision, reasons = decision_for(has_required_data=False)

    assert decision == "MISSING_DATA"
    assert reasons == ["REQUIRED_DATA_MISSING"]


@pytest.mark.parametrize(
    "missing_value",
    [
        {"source_data_age_days": None},
        {"market_data_age_days": None},
        {"sold_90d": None},
        {"sell_through_rate": None},
    ],
)
def test_none_in_required_metrics_returns_missing_data(missing_value: dict[str, None]) -> None:
    decision, _ = decision_for(**missing_value)

    assert decision == "MISSING_DATA"


@pytest.mark.parametrize(
    ("ages", "expected_reason"),
    [
        ({"source_data_age_days": 8}, "SOURCE_DATA_STALE"),
        ({"market_data_age_days": 91}, "MARKET_DATA_STALE"),
    ],
)
def test_data_age_over_maximum_returns_stale_data(
    ages: dict[str, int], expected_reason: str
) -> None:
    decision, reasons = decision_for(**ages)

    assert decision == "STALE_DATA"
    assert reasons == [expected_reason]


@pytest.mark.parametrize("status", ["review", "needs_review"])
def test_review_compliance_status_returns_review_compliance(status: str) -> None:
    compliance = ComplianceDecision(compliance_status=status)  # type: ignore[arg-type]

    decision, reasons = decision_for(compliance=compliance)

    assert decision == "REVIEW_COMPLIANCE"
    assert reasons == ["COMPLIANCE_REVIEW_REQUIRED"]


@pytest.mark.parametrize(
    ("demand", "expected_reason"),
    [
        ({"sold_90d": 4}, "SOLD_90D_BELOW_MINIMUM"),
        ({"sell_through_rate": Decimal("0.14")}, "SELL_THROUGH_RATE_BELOW_MINIMUM"),
    ],
)
def test_demand_below_minimum_returns_low_demand(
    demand: dict[str, object], expected_reason: str
) -> None:
    decision, reasons = decision_for(**demand)

    assert decision == "LOW_DEMAND"
    assert reasons == [expected_reason]


@pytest.mark.parametrize(
    ("profitability", "expected_reason"),
    [
        ({"base_profit_jpy": Decimal(2999)}, "BASE_PROFIT_BELOW_MINIMUM"),
        ({"base_margin": Decimal("0.24")}, "BASE_MARGIN_BELOW_MINIMUM"),
        (
            {"conservative_profit_jpy": Decimal(999)},
            "CONSERVATIVE_PROFIT_BELOW_MINIMUM",
        ),
    ],
)
def test_profitability_below_minimum_returns_low_profit(
    profitability: dict[str, Decimal], expected_reason: str
) -> None:
    decision, reasons = decision_for(**profitability)

    assert decision == "LOW_PROFIT"
    assert reasons == [expected_reason]


def test_confidence_below_minimum_returns_watch() -> None:
    decision, reasons = decision_for(confidence_score=Decimal(59))

    assert decision == "WATCH"
    assert reasons == ["CONFIDENCE_BELOW_MINIMUM"]


def test_first_purchase_that_meets_all_conditions_returns_buy_test_1() -> None:
    decision, reasons = decision_for()

    assert decision == "BUY_TEST_1"
    assert reasons == ["FIRST_PURCHASE"]


def test_test_purchase_history_that_meets_all_conditions_returns_buy_test_2() -> None:
    decision, reasons = decision_for(
        is_first_purchase=False,
        has_test_purchase_history=True,
    )

    assert decision == "BUY_TEST_2"
    assert reasons == ["TEST_PURCHASE_SUCCESSFUL"]


def test_replenish_history_that_meets_all_conditions_returns_replenish() -> None:
    decision, reasons = decision_for(
        is_first_purchase=False,
        has_test_purchase_history=True,
        has_replenish_history=True,
    )

    assert decision == "REPLENISH"
    assert reasons == ["REPLENISH_HISTORY"]


def test_no_purchase_stage_returns_watch() -> None:
    decision, reasons = decision_for(is_first_purchase=False)

    assert decision == "WATCH"
    assert reasons == ["PURCHASE_STAGE_UNDETERMINED"]


def test_higher_priority_condition_wins_when_multiple_conditions_match() -> None:
    decision, _ = decision_for(
        compliance=ComplianceDecision(compliance_status="blocked"),
        has_required_data=False,
        source_data_age_days=999,
        sold_90d=0,
        base_profit_jpy=Decimal(-1),
        confidence_score=Decimal(0),
    )

    assert decision == "BLOCKED"


def test_compliance_helpers_classify_statuses() -> None:
    assert is_blocked(ComplianceDecision(compliance_status="blocked")) is True
    assert is_blocked(ComplianceDecision(compliance_status="approved")) is False
    assert needs_review(ComplianceDecision(compliance_status="review")) is True
    assert needs_review(ComplianceDecision(compliance_status="needs_review")) is True
    assert needs_review(ComplianceDecision(compliance_status="approved")) is False
