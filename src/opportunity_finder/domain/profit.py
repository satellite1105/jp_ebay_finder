from decimal import Decimal

from opportunity_finder.domain.models import (
    ProfitInput,
    ProfitScenarioResult,
    Scenario,
    ScenarioMultipliers,
)

ZERO = Decimal(0)
ONE = Decimal(1)


def calculate_scenario(
    input: ProfitInput,
    multipliers: ScenarioMultipliers,
    scenario: Scenario,
) -> ProfitScenarioResult:
    """Calculate one profitability scenario using Decimal arithmetic only."""
    item_price_usd = input.item_price_usd * multipliers.sale_price_multiplier
    buyer_shipping_usd = input.buyer_shipping_usd * multipliers.shipping_multiplier
    exchange_rate_jpy_per_usd = (
        input.exchange_rate_jpy_per_usd * multipliers.exchange_rate_multiplier
    )
    international_shipping_jpy = input.international_shipping_jpy * multipliers.shipping_multiplier
    ad_rate = input.ad_rate * multipliers.ad_rate_multiplier
    return_reserve_rate = input.return_reserve_rate * multipliers.return_rate_multiplier

    buyer_total_usd = item_price_usd + buyer_shipping_usd
    recognized_revenue_jpy = buyer_total_usd * exchange_rate_jpy_per_usd

    if input.fee_base_is_item_price_only:
        fee_base_jpy = item_price_usd * exchange_rate_jpy_per_usd
    else:
        fee_base_jpy = buyer_total_usd * exchange_rate_jpy_per_usd

    variable_marketplace_fee_jpy = fee_base_jpy * input.marketplace_fee_rate
    marketplace_fee_jpy = variable_marketplace_fee_jpy + input.marketplace_fixed_fee_jpy
    promoted_listing_jpy = fee_base_jpy * ad_rate
    return_reserve_jpy = recognized_revenue_jpy * return_reserve_rate
    international_fee_jpy = input.international_fee_rate * recognized_revenue_jpy

    fixed_cost_jpy = (
        input.source_item_cost_jpy
        + input.source_domestic_shipping_jpy
        + input.source_transport_jpy
        + input.packaging_jpy
        + international_shipping_jpy
        + input.duty_jpy
        + input.import_processing_jpy
        + input.currency_conversion_jpy
        + input.payment_fee_jpy
        + input.labor_cost_jpy
        + input.other_cost_jpy
    )
    variable_cost_jpy = (
        marketplace_fee_jpy + promoted_listing_jpy + return_reserve_jpy + international_fee_jpy
    )
    total_cost_jpy = fixed_cost_jpy + variable_cost_jpy
    net_profit_jpy = recognized_revenue_jpy - total_cost_jpy

    if recognized_revenue_jpy == ZERO:
        net_margin = ZERO
        # No revenue basis exists for converting the designated variable yen
        # terms into a rate. Treating their rate contribution as zero both
        # avoids division by zero and leaves break-even driven by fixed costs.
        total_variable_rate = ZERO
    else:
        net_margin = net_profit_jpy / recognized_revenue_jpy
        total_variable_rate = variable_cost_jpy / recognized_revenue_jpy

    capital_efficiency = net_profit_jpy / input.cash_required_before_sale_jpy
    contribution_margin_rate = ONE - total_variable_rate
    break_even_revenue_jpy = fixed_cost_jpy / contribution_margin_rate
    break_even_buyer_total_usd = break_even_revenue_jpy / exchange_rate_jpy_per_usd
    target_revenue_jpy = (fixed_cost_jpy + input.target_profit_jpy) / contribution_margin_rate
    target_price_usd = target_revenue_jpy / exchange_rate_jpy_per_usd

    return ProfitScenarioResult(
        scenario=scenario,
        buyer_total_usd=buyer_total_usd,
        recognized_revenue_jpy=recognized_revenue_jpy,
        marketplace_fee_jpy=marketplace_fee_jpy,
        promoted_listing_jpy=promoted_listing_jpy,
        return_reserve_jpy=return_reserve_jpy,
        total_cost_jpy=total_cost_jpy,
        net_profit_jpy=net_profit_jpy,
        net_margin=net_margin,
        capital_efficiency=capital_efficiency,
        break_even_buyer_total_usd=break_even_buyer_total_usd,
        target_price_usd=target_price_usd,
    )
