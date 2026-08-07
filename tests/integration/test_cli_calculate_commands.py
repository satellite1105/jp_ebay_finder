"""Integration tests for the opportunity calculation CLI commands."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder.cli import app
from opportunity_finder.cli_commands import calculate_commands
from opportunity_finder.db.models import (
    ExchangeRate,
    FeeRule,
    OpportunitySnapshot,
    ShippingRate,
)
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository

runner = CliRunner()


class _TestSessionFactory:
    """Expose the test transaction through the sessionmaker API used by the CLI."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def begin(self) -> Iterator[Session]:
        yield self._session


@pytest.fixture
def calculation_product_id(
    db_session: Session,
    clean_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    product_id = _seed_calculation_inputs(db_session)
    session_factory = _TestSessionFactory(db_session)
    monkeypatch.setattr(
        calculate_commands,
        "create_session_factory",
        lambda: session_factory,
    )
    return product_id


def test_calculate_opportunities_displays_count_summary(
    db_session: Session,
    calculation_product_id: int,
) -> None:
    result = runner.invoke(app, ["calculate", "opportunities"])

    assert result.exit_code == 0, result.output
    assert "Calculated opportunities:" in result.output
    calculated_count = int(result.output.split(":", 1)[1].split()[0])
    assert calculated_count >= 1
    assert _snapshot_count(db_session, calculation_product_id) == 3


def test_calculate_opportunity_displays_three_scenarios_and_decision(
    db_session: Session,
    calculation_product_id: int,
) -> None:
    result = runner.invoke(
        app,
        ["calculate", "opportunity", "--product-id", str(calculation_product_id)],
    )

    assert result.exit_code == 0, result.output
    assert f"Product ID: {calculation_product_id}" in result.output
    assert "Decision:" in result.output
    assert "Opportunity score:" in result.output
    assert "Confidence score:" in result.output
    assert "optimistic:" in result.output
    assert "base:" in result.output
    assert "conservative:" in result.output
    assert result.output.count("Net profit (JPY):") == 3
    assert _snapshot_count(db_session, calculation_product_id) == 3


def test_calculate_break_even_displays_only_base_break_even_price(
    db_session: Session,
    calculation_product_id: int,
) -> None:
    result = runner.invoke(
        app,
        ["calculate", "break-even", "--product-id", str(calculation_product_id)],
    )

    assert result.exit_code == 0, result.output
    assert f"Product ID: {calculation_product_id}" in result.output
    price_line = next(
        line for line in result.output.splitlines() if line.startswith("Break-even price (USD):")
    )
    price = Decimal(price_line.removeprefix("Break-even price (USD): "))
    assert price > 0
    assert "Net profit" not in result.output
    assert "Decision:" not in result.output
    assert _snapshot_count(db_session, calculation_product_id) == 3


def _seed_calculation_inputs(db_session: Session) -> int:
    unique = uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None)
    observed_at = now - timedelta(hours=1)
    category = f"T27-{unique}"
    product = ProductRepository(db_session).get_or_create(
        jan_code=None,
        internal_sku=f"T27-{unique}",
        normalized_name=f"t27 opportunity product {unique}",
        original_name=f"T27 Opportunity Product {unique}",
        brand="T27 Brand",
        model_number=f"MODEL-{unique}",
        category=category,
        origin_country="JP",
        weight_g=400,
        repeatable_supply=True,
        compliance_status="approved",
        compliance_flags=[],
        created_at=observed_at,
        updated_at=observed_at,
    )

    supplier_repository = SupplierRepository(db_session)
    supplier_item = supplier_repository.upsert_supplier_item(
        product_id=product.id,
        source="T27_TEST",
        external_item_id=f"supplier-{unique}",
        title=product.original_name,
        brand=product.brand,
        model_number=product.model_number,
        match_method="MODEL_NUMBER",
        match_confidence=Decimal("95.000000"),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    supplier_repository.add_price_snapshot(
        supplier_item_id=supplier_item.id,
        item_price_jpy=Decimal("3000.0000"),
        domestic_shipping_jpy=Decimal("300.0000"),
        points_value_jpy=Decimal("100.0000"),
        coupon_value_jpy=Decimal("200.0000"),
        available=True,
        effective_cost_jpy=Decimal("3000.0000"),
        captured_at=observed_at,
    )

    market_repository = MarketRepository(db_session)
    query = market_repository.get_or_create_query(
        product_id=product.id,
        marketplace="EBAY_US",
        query_text=f"T27 market query {unique}",
        category_id=category,
        query_type="KEYWORD",
        created_at=observed_at,
        updated_at=observed_at,
    )
    market_repository.add_research_metric(
        query_id=query.id,
        period_days=90,
        sold_count=20,
        active_count=20,
        seller_count=5,
        median_sold_price=Decimal("100.0000"),
        average_sold_price=Decimal("101.0000"),
        average_shipping=Decimal("5.0000"),
        currency="USD",
        sell_through_rate=Decimal("0.500000"),
        researched_at=observed_at,
    )

    db_session.add_all(
        [
            ExchangeRate(
                base_currency="USD",
                quote_currency="JPY",
                rate=Decimal("150.00000000"),
                source="T27_TEST",
                effective_at=observed_at,
            ),
            ShippingRate(
                profile_code=f"T27_SHIPPING_{unique}",
                destination_country="US",
                min_weight_g=0,
                max_weight_g=500,
                service_name="T27 tracked shipping",
                shipping_jpy=Decimal("1500.0000"),
                tracking=True,
                included_insurance_jpy=Decimal("0.0000"),
                effective_from=now.date() - timedelta(days=1),
                effective_to=None,
                created_at=now,
            ),
            FeeRule(
                profile_code=f"T27_FEE_{unique}",
                marketplace="EBAY_US",
                category_code=category,
                variable_fee_rate=Decimal("0.130000"),
                international_fee_rate=Decimal("0.015000"),
                fixed_fee_currency="USD",
                fixed_fee_amount=Decimal("0.300000"),
                ad_rate=Decimal("0.020000"),
                return_reserve_rate=Decimal("0.030000"),
                effective_from=now.date() - timedelta(days=1),
                effective_to=None,
                created_at=now,
            ),
        ]
    )
    db_session.flush()
    return product.id


def _snapshot_count(session: Session, product_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(OpportunitySnapshot)
            .where(OpportunitySnapshot.product_id == product_id)
        )
        or 0
    )
