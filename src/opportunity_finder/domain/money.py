from decimal import ROUND_HALF_UP, Decimal

JPY_QUANT = Decimal("0.0001")
USD_QUANT = Decimal("0.000001")
RATE_QUANT = Decimal("0.000001")


class Money:
    """Decimal-only monetary value object that rejects float inputs."""

    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal | str | int, currency: str) -> None:
        if isinstance(amount, float):
            raise TypeError("Money must not be constructed from float")
        self.amount: Decimal = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        self.currency = currency

    def quantize(self, exp: Decimal = JPY_QUANT, rounding=ROUND_HALF_UP) -> "Money":
        return Money(self.amount.quantize(exp, rounding=rounding), self.currency)

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, rate: Decimal) -> "Money":
        if not isinstance(rate, Decimal):
            raise TypeError("Money can only be multiplied by Decimal")
        return Money(self.amount * rate, self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.amount == other.amount and self.currency == other.currency

    def as_decimal(self) -> Decimal:
        return self.amount

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("Money currencies must match")
