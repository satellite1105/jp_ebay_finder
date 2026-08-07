from __future__ import annotations

from decimal import Decimal

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def _clamp(value: Decimal, lower: Decimal = ZERO, upper: Decimal = ONE) -> Decimal:
    return min(max(value, lower), upper)


def calculate_opportunity_score(
    base_profit_jpy: Decimal,
    base_margin: Decimal,
    sold_90d: int,
    sell_through_rate: Decimal,
    capital_efficiency: Decimal,
    conservative_profit_jpy: Decimal,
    confidence_score: Decimal,
    is_replenishable: bool,
    risk_flags: list[str],
) -> tuple[Decimal, dict[str, Decimal]]:
    """Calculate the 0-100 opportunity score and its point breakdown."""
    profit_points = _clamp((base_profit_jpy - Decimal(1000)) / Decimal(5000)) * Decimal(25)
    margin_points = _clamp((base_margin - Decimal("0.10")) / Decimal("0.40")) * Decimal(15)

    non_negative_sales = max(sold_90d, 0)
    sales_ratio = (Decimal(non_negative_sales) + ONE).ln() / Decimal(101).ln()
    sales_points = _clamp(sales_ratio) * Decimal(15)

    sell_through_points = _clamp(sell_through_rate / Decimal("0.60")) * Decimal(10)
    capital_points = _clamp(capital_efficiency / ONE) * Decimal(10)
    conservative_points = _clamp(conservative_profit_jpy / Decimal(3000)) * Decimal(10)
    confidence_points = _clamp(confidence_score / HUNDRED) * Decimal(10)
    replenishable_points = Decimal(5) if is_replenishable else ZERO

    distinct_risk_count = len(set(risk_flags))
    risk_deduction = -min(Decimal(distinct_risk_count) * Decimal(10), Decimal(30))

    breakdown = {
        "base_profit": profit_points,
        "base_margin": margin_points,
        "sold_90d": sales_points,
        "sell_through_rate": sell_through_points,
        "capital_efficiency": capital_points,
        "conservative_resilience": conservative_points,
        "data_confidence": confidence_points,
        "replenishable": replenishable_points,
        "risk_deduction": risk_deduction,
    }
    total = _clamp(sum(breakdown.values(), ZERO), ZERO, HUNDRED)
    return total, breakdown


def calculate_confidence_score(
    match_method: str,
    title_similarity: Decimal | None,
    market_data_count: int,
    source_data_age_days: int,
    weight_is_measured: bool,
    origin_confirmed: bool,
    condition_mismatch: bool,
    unit_count_mismatch: bool,
    model_number_ambiguous: bool,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Calculate the 0-100 data-confidence score and its point breakdown."""
    normalized_match_method = match_method.strip().casefold()

    jan_methods = {"jan", "jan_exact", "jan_exact_match"}
    manufacturer_model_methods = {
        "manufacturer_model",
        "manufacturer_model_exact",
        "model_number",
        "model_number_exact",
    }
    brand_model_methods = {"brand_model", "brand_and_model"}

    title_matches = False
    if title_similarity is not None and title_similarity >= ZERO:
        threshold = Decimal("0.90") if title_similarity <= ONE else Decimal(90)
        title_matches = title_similarity >= threshold

    breakdown = {
        "jan_exact_match": Decimal(35) if normalized_match_method in jan_methods else ZERO,
        "manufacturer_model_exact_match": Decimal(30)
        if normalized_match_method in manufacturer_model_methods
        else ZERO,
        "brand_model_match": Decimal(20)
        if normalized_match_method in brand_model_methods
        else ZERO,
        "title_similarity_90": Decimal(15) if title_matches else ZERO,
        "market_data_10_plus": Decimal(10) if market_data_count >= 10 else ZERO,
        "source_data_within_7_days": Decimal(5) if 0 <= source_data_age_days <= 7 else ZERO,
        "weight_measured": Decimal(5) if weight_is_measured else ZERO,
        "origin_confirmed": Decimal(5) if origin_confirmed else ZERO,
        "condition_mismatch": Decimal(-25) if condition_mismatch else ZERO,
        "unit_count_mismatch": Decimal(-30) if unit_count_mismatch else ZERO,
        "model_number_ambiguous": Decimal(-20) if model_number_ambiguous else ZERO,
    }
    total = _clamp(sum(breakdown.values(), ZERO), ZERO, HUNDRED)
    return total, breakdown
