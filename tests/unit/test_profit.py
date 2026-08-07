from decimal import Decimal

from opportunity_finder.domain.models import ProfitInput, ScenarioMultipliers
from opportunity_finder.domain.profit import calculate_scenario


def base_input(**overrides: Decimal | bool) -> ProfitInput:
    values: dict[str, Decimal | bool] = {
        "item_price_usd": Decimal(100),
        "buyer_shipping_usd": Decimal(20),
        "exchange_rate_jpy_per_usd": Decimal(150),
        "source_item_cost_jpy": Decimal(6000),
        "source_domestic_shipping_jpy": Decimal(500),
        "source_transport_jpy": Decimal(300),
        "packaging_jpy": Decimal(200),
        "international_shipping_jpy": Decimal(2000),
        "duty_jpy": Decimal(500),
        "import_processing_jpy": Decimal(100),
        "international_fee_rate": Decimal("0.015"),
        "currency_conversion_jpy": Decimal(100),
        "payment_fee_jpy": Decimal(50),
        "labor_cost_jpy": Decimal(500),
        "other_cost_jpy": Decimal(250),
        "marketplace_fee_rate": Decimal("0.13"),
        "marketplace_fixed_fee_jpy": Decimal(0),
        "fee_base_is_item_price_only": True,
        "ad_rate": Decimal("0.02"),
        "return_reserve_rate": Decimal("0.03"),
        "cash_required_before_sale_jpy": Decimal(9500),
        "target_profit_jpy": Decimal(3000),
    }
    values.update(overrides)
    return ProfitInput(**values)  # type: ignore[arg-type]


def base_multipliers() -> ScenarioMultipliers:
    return ScenarioMultipliers(
        sale_price_multiplier=Decimal(1),
        exchange_rate_multiplier=Decimal(1),
        shipping_multiplier=Decimal(1),
        ad_rate_multiplier=Decimal(1),
        return_rate_multiplier=Decimal(1),
    )


def assert_within_one_yen(actual: Decimal, expected: Decimal) -> None:
    assert abs(actual - expected) <= Decimal(1)


def test_normal_case_produces_expected_profit() -> None:
    result = calculate_scenario(base_input(), base_multipliers(), "base")

    assert result.scenario == "base"
    assert result.buyer_total_usd == Decimal(120)
    assert result.recognized_revenue_jpy == Decimal(18000)
    assert result.marketplace_fee_jpy == Decimal(1950)
    assert result.promoted_listing_jpy == Decimal(300)
    assert result.return_reserve_jpy == Decimal(540)
    assert result.total_cost_jpy == Decimal(13560)
    assert result.net_profit_jpy == Decimal(4440)
    assert result.net_margin == Decimal("0.2466666666666666666666666667")
    assert result.capital_efficiency == Decimal("0.4673684210526315789473684211")
    assert_within_one_yen(
        result.break_even_buyer_total_usd,
        Decimal("84.33734939759036144578313253"),
    )
    assert result.target_price_usd == Decimal("108.4337349397590361445783133")


def test_nonzero_marketplace_fixed_fee_is_included() -> None:
    result = calculate_scenario(
        base_input(marketplace_fixed_fee_jpy=Decimal(45)),
        base_multipliers(),
        "base",
    )

    assert result.marketplace_fee_jpy == Decimal(1995)
    assert result.total_cost_jpy == Decimal(13605)
    assert result.net_profit_jpy == Decimal(4395)


def test_zero_ad_rate_has_no_promoted_listing_cost() -> None:
    result = calculate_scenario(base_input(ad_rate=Decimal(0)), base_multipliers(), "base")

    assert result.promoted_listing_jpy == Decimal(0)
    assert result.total_cost_jpy == Decimal(13260)
    assert result.net_profit_jpy == Decimal(4740)


def test_zero_duty_is_supported() -> None:
    result = calculate_scenario(base_input(duty_jpy=Decimal(0)), base_multipliers(), "base")

    assert result.total_cost_jpy == Decimal(13060)
    assert result.net_profit_jpy == Decimal(4940)


def test_net_loss_is_returned_as_negative_profit() -> None:
    result = calculate_scenario(
        base_input(source_item_cost_jpy=Decimal(15000)),
        base_multipliers(),
        "base",
    )

    assert result.total_cost_jpy == Decimal(22560)
    assert result.net_profit_jpy == Decimal(-4560)
    assert result.net_margin == Decimal("-0.2533333333333333333333333333")


def test_zero_recognized_revenue_returns_zero_margin() -> None:
    result = calculate_scenario(
        base_input(
            item_price_usd=Decimal(0),
            buyer_shipping_usd=Decimal(0),
        ),
        base_multipliers(),
        "base",
    )

    assert result.recognized_revenue_jpy == Decimal(0)
    assert result.net_profit_jpy == Decimal(-10500)
    assert result.net_margin == Decimal(0)
    assert result.break_even_buyer_total_usd == Decimal(70)


def test_conservative_multipliers_are_applied_before_calculation() -> None:
    multipliers = ScenarioMultipliers(
        sale_price_multiplier=Decimal("0.92"),
        exchange_rate_multiplier=Decimal("0.97"),
        shipping_multiplier=Decimal("1.10"),
        ad_rate_multiplier=Decimal("1.30"),
        return_rate_multiplier=Decimal("1.50"),
    )

    result = calculate_scenario(base_input(), multipliers, "conservative")

    # 100*0.92 + 20*1.10 = 114 USD; exchange rate is 150*0.97 = 145.5.
    assert result.buyer_total_usd == Decimal("114.00")
    assert result.recognized_revenue_jpy == Decimal("16587.000")
    assert result.marketplace_fee_jpy == Decimal("1740.18000")
    assert result.promoted_listing_jpy == Decimal("348.0360000")
    assert result.return_reserve_jpy == Decimal("746.4150000")
    # International shipping is also increased from 2,000 to 2,200 yen.
    assert result.total_cost_jpy == Decimal("13783.4360000")
    assert result.net_profit_jpy == Decimal("2803.5640000")


def test_break_even_buyer_total_usd_matches_hand_calculation() -> None:
    profit_input = ProfitInput(
        item_price_usd=Decimal(100),
        buyer_shipping_usd=Decimal(0),
        exchange_rate_jpy_per_usd=Decimal(100),
        source_item_cost_jpy=Decimal(5000),
        marketplace_fee_rate=Decimal("0.10"),
        international_fee_rate=Decimal("0.03"),
        ad_rate=Decimal("0.05"),
        return_reserve_rate=Decimal("0.02"),
        cash_required_before_sale_jpy=Decimal(5000),
        target_profit_jpy=Decimal(3000),
    )

    result = calculate_scenario(profit_input, base_multipliers(), "base")

    # Variable costs are 20% of revenue, so 5,000 / (1 - 0.20) / 100.
    assert result.break_even_buyer_total_usd == Decimal("62.5")
    assert result.target_price_usd == Decimal(100)
