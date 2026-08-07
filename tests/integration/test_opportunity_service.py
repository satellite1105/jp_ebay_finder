"""Integration tests for the opportunity calculation application service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import (
    ExchangeRate,
    FeeRule,
    OpportunitySnapshot,
    ShippingRate,
)
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository
from opportunity_finder.services.opportunity_service import OpportunityService

AS_OF = datetime(2040, 6, 15, 12, 0, tzinfo=UTC)


def test_calculate_opportunities_persists_scenarios_scores_and_decision(
    db_session: Session, clean_db: None
) -> None:
    product_id, profiles = _seed_calculation_inputs(db_session)
    service = _service(db_session, profiles)

    result = _result_for_product(service.calculate_opportunities(), product_id)
    db_session.expire_all()
    snapshots = _snapshots_for_product(db_session, product_id)

    assert set(result.scenarios) == {"optimistic", "base", "conservative"}
    assert {row.scenario for row in snapshots} == {
        "optimistic",
        "base",
        "conservative",
    }
    assert len(snapshots) == 3
    assert result.opportunity_score > 0
    assert result.confidence_score >= Decimal(60)
    assert result.decision == "BUY_TEST_1"

    for snapshot in snapshots:
        scenario = result.scenarios[snapshot.scenario]
        assert snapshot.net_profit_jpy == scenario.net_profit_jpy.quantize(Decimal("0.0001"))
        assert snapshot.total_cost_jpy == scenario.total_cost_jpy.quantize(Decimal("0.0001"))
        assert snapshot.opportunity_score == result.opportunity_score.quantize(Decimal("0.0001"))
        assert snapshot.data_confidence == result.confidence_score.quantize(Decimal("0.0001"))
        assert snapshot.decision == result.decision
        assert snapshot.reason_codes == result.reason_codes
        assert snapshot.input_snapshot["exchange_rate"]["rate"] == "150.00000000"
        assert snapshot.input_snapshot["fee_rule"]["variable_fee_rate"] == "0.130000"
        assert snapshot.input_snapshot["shipping_rate"]["shipping_jpy"] == "1500.0000"


def test_same_inputs_produce_identical_calculation_results_on_two_runs(
    db_session: Session, clean_db: None
) -> None:
    product_id, profiles = _seed_calculation_inputs(db_session)
    service = _service(db_session, profiles)

    first = _result_for_product(service.calculate_opportunities(), product_id)
    second = _result_for_product(service.calculate_opportunities(), product_id)

    assert _calculation_signature(first) == _calculation_signature(second)

    db_session.expire_all()
    snapshots = _snapshots_for_product(db_session, product_id)
    assert len(snapshots) == 6
    first_run = sorted(snapshots[:3], key=lambda row: row.scenario)
    second_run = sorted(snapshots[3:], key=lambda row: row.scenario)
    assert [_snapshot_signature(row) for row in first_run] == [
        _snapshot_signature(row) for row in second_run
    ]


def test_blocked_compliance_overrides_missing_and_stale_data(
    db_session: Session, clean_db: None
) -> None:
    product_id, profiles = _seed_calculation_inputs(
        db_session,
        compliance_status="blocked",
        missing_demand=True,
        stale=True,
    )
    service = _service(db_session, profiles)

    result = _result_for_product(service.calculate_opportunities(), product_id)
    db_session.expire_all()
    snapshots = _snapshots_for_product(db_session, product_id)

    assert result.decision == "BLOCKED"
    assert result.reason_codes == ["COMPLIANCE_BLOCKED"]
    assert len(snapshots) == 3
    assert {row.decision for row in snapshots} == {"BLOCKED"}
    assert {tuple(row.reason_codes) for row in snapshots} == {("COMPLIANCE_BLOCKED",)}


def _seed_calculation_inputs(
    db_session: Session,
    *,
    compliance_status: str = "approved",
    missing_demand: bool = False,
    stale: bool = False,
) -> tuple[int, tuple[str, str]]:
    unique = uuid4().hex
    observed_at = AS_OF - (timedelta(days=120) if stale else timedelta(days=1))
    researched_at = AS_OF - (timedelta(days=120) if stale else timedelta(days=2))
    product = ProductRepository(db_session).get_or_create(
        jan_code=None,
        internal_sku=f"T22-{unique}",
        normalized_name=f"t22 opportunity product {unique}",
        original_name=f"T22 Opportunity Product {unique}",
        brand="T22 Brand",
        model_number=f"MODEL-{unique}",
        origin_country="JP",
        weight_g=400,
        repeatable_supply=True,
        compliance_status=compliance_status,
        compliance_flags=[],
        created_at=observed_at,
        updated_at=observed_at,
    )

    supplier_repository = SupplierRepository(db_session)
    supplier_item = supplier_repository.upsert_supplier_item(
        product_id=product.id,
        source="T22_TEST",
        external_item_id=f"supplier-{unique}",
        title=product.original_name,
        jan_code=product.jan_code,
        brand=product.brand,
        model_number=product.model_number,
        match_method="JAN",
        match_confidence=Decimal("100.000000"),
        is_active=True,
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
        query_text=f"T22 market query {unique}",
        query_type="KEYWORD",
        enabled=True,
        created_at=researched_at,
        updated_at=researched_at,
    )
    market_repository.add_research_metric(
        query_id=query.id,
        period_days=90,
        sold_count=None if missing_demand else 20,
        active_count=20,
        seller_count=5,
        median_sold_price=Decimal("100.0000"),
        average_sold_price=Decimal("101.0000"),
        average_shipping=Decimal("5.0000"),
        currency="USD",
        sell_through_rate=None if missing_demand else Decimal("0.500000"),
        researched_at=researched_at,
    )

    shipping_profile = f"T22_SHIPPING_{unique}"
    fee_profile = f"T22_FEE_{unique}"
    db_session.add_all(
        [
            ExchangeRate(
                base_currency="USD",
                quote_currency="JPY",
                rate=Decimal("150.00000000"),
                source="T22_TEST",
                effective_at=AS_OF - timedelta(days=3),
            ),
            ShippingRate(
                profile_code=shipping_profile,
                destination_country="US",
                min_weight_g=0,
                max_weight_g=500,
                service_name="T22 tracked shipping",
                shipping_jpy=Decimal("1500.0000"),
                tracking=True,
                included_insurance_jpy=Decimal("0.0000"),
                effective_from=date(2040, 1, 1),
                effective_to=None,
                created_at=AS_OF,
            ),
            FeeRule(
                profile_code=fee_profile,
                marketplace="EBAY_US",
                category_code=None,
                variable_fee_rate=Decimal("0.130000"),
                international_fee_rate=Decimal("0.015000"),
                fixed_fee_currency="USD",
                fixed_fee_amount=Decimal("0.300000"),
                ad_rate=Decimal("0.020000"),
                return_reserve_rate=Decimal("0.030000"),
                effective_from=date(2040, 1, 1),
                effective_to=None,
                created_at=AS_OF,
            ),
        ]
    )
    db_session.flush()
    return product.id, (shipping_profile, fee_profile)


def _service(session: Session, profiles: tuple[str, str]) -> OpportunityService:
    shipping_profile, fee_profile = profiles
    return OpportunityService(
        session,
        shipping_profile_code=shipping_profile,
        fee_profile_code=fee_profile,
        as_of=AS_OF,
    )


def _result_for_product(results: list, product_id: int):
    return next(result for result in results if result.product_id == product_id)


def _snapshots_for_product(session: Session, product_id: int) -> list[OpportunitySnapshot]:
    return list(
        session.scalars(
            select(OpportunitySnapshot)
            .where(OpportunitySnapshot.product_id == product_id)
            .order_by(OpportunitySnapshot.id)
        )
    )


def _calculation_signature(result) -> tuple:
    return (
        result.product_id,
        result.query_id,
        tuple(
            (
                scenario,
                result.scenarios[scenario].model_dump(),
            )
            for scenario in ("optimistic", "base", "conservative")
        ),
        result.opportunity_score,
        result.score_breakdown,
        result.confidence_score,
        result.confidence_breakdown,
        result.decision,
        result.reason_codes,
        result.input_snapshot,
    )


def _snapshot_signature(snapshot: OpportunitySnapshot) -> tuple:
    return (
        snapshot.scenario,
        snapshot.source_cost_jpy,
        snapshot.buyer_total_market_currency,
        snapshot.exchange_rate,
        snapshot.revenue_jpy,
        snapshot.marketplace_fees_jpy,
        snapshot.advertising_reserve_jpy,
        snapshot.return_reserve_jpy,
        snapshot.international_shipping_jpy,
        snapshot.total_cost_jpy,
        snapshot.net_profit_jpy,
        snapshot.net_margin,
        snapshot.break_even_buyer_total,
        snapshot.capital_efficiency,
        snapshot.opportunity_score,
        snapshot.data_confidence,
        snapshot.decision,
        tuple(snapshot.reason_codes),
        snapshot.input_snapshot,
    )
