from decimal import Decimal

import pytest

from opportunity_finder.domain.money import JPY_QUANT, USD_QUANT, Money


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("123.4567"), Decimal("123.4567")),
        ("123.4567", Decimal("123.4567")),
        (123, Decimal(123)),
    ],
)
def test_constructs_from_decimal_string_and_int(
    amount: Decimal | str | int, expected: Decimal
) -> None:
    money = Money(amount, "JPY")

    assert money.as_decimal() == expected
    assert money.currency == "JPY"


def test_rejects_float_amount() -> None:
    with pytest.raises(TypeError, match="Money must not be constructed from float"):
        Money(1.5, "JPY")


@pytest.mark.parametrize(
    ("exp", "expected"),
    [
        (JPY_QUANT, Decimal("1.2346")),
        (USD_QUANT, Decimal("1.234550")),
    ],
)
def test_quantize_uses_round_half_up(exp: Decimal, expected: Decimal) -> None:
    money = Money("1.23455", "JPY")

    result = money.quantize(exp)

    assert result == Money(expected, "JPY")
    assert result is not money


def test_adds_money_with_same_currency() -> None:
    result = Money("10.25", "USD") + Money("2.75", "USD")

    assert result == Money("13.00", "USD")


def test_subtracts_money_with_same_currency() -> None:
    result = Money("10.25", "USD") - Money("2.75", "USD")

    assert result == Money("7.50", "USD")


@pytest.mark.parametrize("operator", ["add", "sub"])
def test_rejects_arithmetic_with_different_currencies(operator: str) -> None:
    jpy = Money("100", "JPY")
    usd = Money("1", "USD")

    with pytest.raises(ValueError):
        if operator == "add":
            jpy + usd
        else:
            jpy - usd


def test_multiplies_by_decimal_rate() -> None:
    result = Money("12.50", "USD") * Decimal("1.2")

    assert result == Money("15.000", "USD")


def test_rejects_float_multiplier() -> None:
    with pytest.raises(TypeError):
        Money("12.50", "USD") * 1.2  # type: ignore[arg-type]


def test_money_equality_requires_same_amount_and_currency() -> None:
    assert Money("100", "JPY") == Money(Decimal(100), "JPY")
    assert Money("100", "JPY") != Money("100", "USD")
    assert Money("100", "JPY") != object()
