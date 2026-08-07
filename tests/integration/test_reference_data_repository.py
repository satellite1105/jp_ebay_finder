"""Integration tests for reference data lookups."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from opportunity_finder.db.models import ExchangeRate, FeeRule, ShippingRate
from opportunity_finder.db.repositories.reference_data_repository import (
    ReferenceDataRepository,
)


def test_get_latest_exchange_rate_returns_latest_record_at_or_before_as_of(
    db_session: Session,
) -> None:
    rates = [
        ExchangeRate(
            base_currency="T19",
            quote_currency="Q19",
            rate=Decimal("145.10000000"),
            source="T19_TEST",
            effective_at=datetime(2041, 1, 1, 0, 0, tzinfo=UTC),
        ),
        ExchangeRate(
            base_currency="T19",
            quote_currency="Q19",
            rate=Decimal("146.20000000"),
            source="T19_TEST",
            effective_at=datetime(2041, 2, 1, 0, 0, tzinfo=UTC),
        ),
        ExchangeRate(
            base_currency="T19",
            quote_currency="Q19",
            rate=Decimal("147.30000000"),
            source="T19_TEST",
            effective_at=datetime(2041, 3, 1, 0, 0, tzinfo=UTC),
        ),
    ]
    db_session.add_all(rates)
    db_session.flush()
    repository = ReferenceDataRepository(db_session)

    result = repository.get_latest_exchange_rate(
        "T19", "Q19", as_of=datetime(2041, 2, 15, 12, 0, tzinfo=UTC)
    )

    assert result is rates[1]
    assert (
        repository.get_latest_exchange_rate(
            "T19", "Q19", as_of=datetime(2040, 12, 31, 23, 59, tzinfo=UTC)
        )
        is None
    )


def test_get_shipping_rate_includes_weight_boundaries_and_excludes_outside(
    db_session: Session,
) -> None:
    profile_code = f"T19_SHIPPING_{uuid4().hex}"
    rate = ShippingRate(
        profile_code=profile_code,
        destination_country="US",
        min_weight_g=100,
        max_weight_g=500,
        service_name="T19 tracked shipping",
        shipping_jpy=Decimal("2500.0000"),
        tracking=True,
        included_insurance_jpy=Decimal("0.0000"),
        effective_from=date(2041, 1, 1),
        effective_to=date(2041, 12, 31),
        created_at=datetime(2041, 1, 1, 0, 0, tzinfo=UTC),
    )
    db_session.add(rate)
    db_session.flush()
    repository = ReferenceDataRepository(db_session)
    as_of = date(2041, 6, 1)

    assert repository.get_shipping_rate(profile_code, "US", 100, as_of) is rate
    assert repository.get_shipping_rate(profile_code, "US", 500, as_of) is rate
    assert repository.get_shipping_rate(profile_code, "US", 99, as_of) is None
    assert repository.get_shipping_rate(profile_code, "US", 501, as_of) is None


def test_get_fee_rule_respects_effective_period_and_open_ended_end_date(
    db_session: Session,
) -> None:
    profile_code = f"T19_FEE_{uuid4().hex}"
    common_values = {
        "profile_code": profile_code,
        "marketplace": "EBAY_US",
        "category_code": None,
        "international_fee_rate": Decimal("0.015000"),
        "fixed_fee_currency": "USD",
        "fixed_fee_amount": Decimal("0.300000"),
        "ad_rate": Decimal("0.020000"),
        "return_reserve_rate": Decimal("0.030000"),
        "created_at": datetime(2041, 1, 1, 0, 0, tzinfo=UTC),
    }
    bounded_rule = FeeRule(
        **common_values,
        variable_fee_rate=Decimal("0.120000"),
        effective_from=date(2041, 1, 1),
        effective_to=date(2041, 6, 30),
    )
    open_ended_rule = FeeRule(
        **common_values,
        variable_fee_rate=Decimal("0.130000"),
        effective_from=date(2041, 7, 1),
        effective_to=None,
    )
    db_session.add_all([bounded_rule, open_ended_rule])
    db_session.flush()
    repository = ReferenceDataRepository(db_session)

    assert repository.get_fee_rule(profile_code, "EBAY_US", as_of=date(2041, 6, 30)) is bounded_rule
    assert (
        repository.get_fee_rule(profile_code, "EBAY_US", as_of=date(2050, 1, 1)) is open_ended_rule
    )
    assert repository.get_fee_rule(profile_code, "EBAY_US", as_of=date(2040, 12, 31)) is None
