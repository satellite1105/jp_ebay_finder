from decimal import Decimal

from opportunity_finder.domain.scoring import (
    calculate_confidence_score,
    calculate_opportunity_score,
)


def opportunity_score(**overrides: object) -> tuple[Decimal, dict[str, Decimal]]:
    values: dict[str, object] = {
        "base_profit_jpy": Decimal(6000),
        "base_margin": Decimal("0.50"),
        "sold_90d": 100,
        "sell_through_rate": Decimal("0.60"),
        "capital_efficiency": Decimal("1.00"),
        "conservative_profit_jpy": Decimal(3000),
        "confidence_score": Decimal(100),
        "is_replenishable": True,
        "risk_flags": [],
    }
    values.update(overrides)
    return calculate_opportunity_score(**values)  # type: ignore[arg-type]


def confidence_score(**overrides: object) -> tuple[Decimal, dict[str, Decimal]]:
    values: dict[str, object] = {
        "match_method": "none",
        "title_similarity": None,
        "market_data_count": 0,
        "source_data_age_days": 8,
        "weight_is_measured": False,
        "origin_confirmed": False,
        "condition_mismatch": False,
        "unit_count_mismatch": False,
        "model_number_ambiguous": False,
    }
    values.update(overrides)
    return calculate_confidence_score(**values)  # type: ignore[arg-type]


def test_opportunity_score_clamps_upper_bound_to_100() -> None:
    score, breakdown = opportunity_score(
        base_profit_jpy=Decimal(100000),
        base_margin=Decimal(5),
        sold_90d=10000,
        sell_through_rate=Decimal(5),
        capital_efficiency=Decimal(10),
        conservative_profit_jpy=Decimal(100000),
        confidence_score=Decimal(1000),
    )

    assert score == Decimal(100)
    assert sum(breakdown.values()) == Decimal(100)


def test_opportunity_score_clamps_lower_bound_to_zero() -> None:
    score, breakdown = opportunity_score(
        base_profit_jpy=Decimal(-5000),
        base_margin=Decimal(-1),
        sold_90d=-1,
        sell_through_rate=Decimal(-1),
        capital_efficiency=Decimal(-1),
        conservative_profit_jpy=Decimal(-5000),
        confidence_score=Decimal(-10),
        is_replenishable=False,
        risk_flags=["compliance", "authenticity", "returns"],
    )

    assert score == Decimal(0)
    assert breakdown["risk_deduction"] == Decimal(-30)


def test_opportunity_score_with_zero_sales_has_no_sales_points() -> None:
    score, breakdown = opportunity_score(sold_90d=0)

    assert breakdown["sold_90d"] == Decimal(0)
    assert score == Decimal(85)


def test_opportunity_score_for_high_profit_and_low_demand() -> None:
    score, breakdown = opportunity_score(
        sold_90d=0,
        sell_through_rate=Decimal(0),
    )

    assert breakdown["base_profit"] == Decimal(25)
    assert breakdown["base_margin"] == Decimal(15)
    assert breakdown["sold_90d"] == Decimal(0)
    assert breakdown["sell_through_rate"] == Decimal(0)
    assert score == Decimal(75)


def test_opportunity_score_for_low_profit_and_high_demand() -> None:
    score, breakdown = opportunity_score(
        base_profit_jpy=Decimal(1000),
        base_margin=Decimal("0.10"),
    )

    assert breakdown["base_profit"] == Decimal(0)
    assert breakdown["base_margin"] == Decimal(0)
    assert breakdown["sold_90d"] == Decimal(15)
    assert breakdown["sell_through_rate"] == Decimal(10)
    assert score == Decimal(60)


def test_opportunity_score_applies_risk_deduction() -> None:
    score, breakdown = opportunity_score(
        risk_flags=["fragile", "returns", "fragile"],
    )

    assert breakdown["risk_deduction"] == Decimal(-20)
    assert score == Decimal(80)


def test_confidence_score_for_jan_match_only() -> None:
    score, breakdown = confidence_score(match_method="jan")

    assert score == Decimal(35)
    assert breakdown["jan_exact_match"] == Decimal(35)
    assert sum(breakdown.values()) == Decimal(35)


def test_confidence_score_accumulates_multiple_factors() -> None:
    score, breakdown = confidence_score(
        match_method="manufacturer_model",
        title_similarity=Decimal("0.90"),
        market_data_count=10,
        source_data_age_days=7,
        weight_is_measured=True,
        origin_confirmed=True,
    )

    assert score == Decimal(70)
    assert breakdown == {
        "jan_exact_match": Decimal(0),
        "manufacturer_model_exact_match": Decimal(30),
        "brand_model_match": Decimal(0),
        "title_similarity_90": Decimal(15),
        "market_data_10_plus": Decimal(10),
        "source_data_within_7_days": Decimal(5),
        "weight_measured": Decimal(5),
        "origin_confirmed": Decimal(5),
        "condition_mismatch": Decimal(0),
        "unit_count_mismatch": Decimal(0),
        "model_number_ambiguous": Decimal(0),
    }


def test_confidence_score_applies_mismatch_deductions() -> None:
    score, breakdown = confidence_score(
        match_method="jan",
        title_similarity=Decimal(90),
        market_data_count=10,
        condition_mismatch=True,
    )

    assert breakdown["condition_mismatch"] == Decimal(-25)
    assert score == Decimal(35)


def test_confidence_score_clamps_to_zero_and_100_range() -> None:
    low_score, breakdown = confidence_score(
        condition_mismatch=True,
        unit_count_mismatch=True,
        model_number_ambiguous=True,
    )
    high_score, _ = confidence_score(
        match_method="jan",
        title_similarity=Decimal(1),
        market_data_count=100,
        source_data_age_days=0,
        weight_is_measured=True,
        origin_confirmed=True,
    )

    assert low_score == Decimal(0)
    assert sum(breakdown.values()) == Decimal(-75)
    assert Decimal(0) <= high_score <= Decimal(100)
