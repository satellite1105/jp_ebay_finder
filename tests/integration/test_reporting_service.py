from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from opportunity_finder.db.models import MarketQuery, Product
from opportunity_finder.db.repositories.opportunity_repository import OpportunityRepository
from opportunity_finder.db.repositories.run_repository import RunRepository
from opportunity_finder.services.reporting_service import ReportingService


def create_product_and_query(db_session: Session) -> tuple[Product, MarketQuery]:
    now = datetime(2026, 8, 8, 1, 2, 3, 456789, tzinfo=UTC).replace(tzinfo=None)
    unique_key = uuid4().hex
    product = Product(
        internal_sku=f"report-{unique_key}",
        normalized_name=f"reporting test product {unique_key}",
        original_name=f"Reporting Test Product {unique_key}",
        created_at=now,
        updated_at=now,
    )
    db_session.add(product)
    db_session.flush()

    query = MarketQuery(
        product_id=product.id,
        query_text=f"reporting test query {unique_key}",
        query_type="KEYWORD",
        created_at=now,
        updated_at=now,
    )
    db_session.add(query)
    db_session.flush()
    return product, query


def snapshot_values(
    product: Product,
    query: MarketQuery,
    *,
    score: str,
    decision: str,
) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "query_id": query.id,
        "scenario": "base",
        "source_cost_jpy": Decimal("5000.0000"),
        "buyer_total_market_currency": Decimal("100.0000"),
        "market_currency": "USD",
        "exchange_rate": Decimal("150.12345678"),
        "revenue_jpy": Decimal("15012.3457"),
        "marketplace_fees_jpy": Decimal("1951.6049"),
        "advertising_reserve_jpy": Decimal("450.3704"),
        "return_reserve_jpy": Decimal("450.3704"),
        "duty_processing_jpy": Decimal("300.0000"),
        "international_shipping_jpy": Decimal("2000.0000"),
        "packaging_jpy": Decimal("200.0000"),
        "other_costs_jpy": Decimal("100.0000"),
        "total_cost_jpy": Decimal("10452.3457"),
        "net_profit_jpy": Decimal("4560.0000"),
        "net_margin": Decimal("0.303750"),
        "break_even_buyer_total": Decimal("69.6250"),
        "capital_required_jpy": Decimal("7500.0000"),
        "capital_efficiency": Decimal("0.608000"),
        "opportunity_score": Decimal(score),
        "data_confidence": Decimal("91.2500"),
        "decision": decision,
        "reason_codes": ["PROFIT_TARGET_MET", "DEMAND_CONFIRMED"],
        "input_snapshot": {"fee_profile": "EBAY_US_DEFAULT"},
        "calculated_at": datetime(2026, 8, 8, 2, 3, 4, 567890, tzinfo=UTC).replace(tzinfo=None),
        "calculator_version": "test-v1",
    }


def test_get_top_opportunities_delegates_ranking_and_decision_filter(
    db_session: Session, clean_db: None
) -> None:
    product, query = create_product_and_query(db_session)
    repository = OpportunityRepository(db_session)
    repository.save_snapshot(**snapshot_values(product, query, score="40.0000", decision="WATCH"))
    repository.save_snapshot(
        **snapshot_values(product, query, score="92.0000", decision="BUY_TEST_1")
    )
    repository.save_snapshot(
        **snapshot_values(product, query, score="81.0000", decision="BUY_TEST_1")
    )

    service = ReportingService(db_session)
    top = service.get_top_opportunities(limit=2)
    buy_only = service.get_top_opportunities(limit=10, decision="BUY_TEST_1")

    assert [row.opportunity_score for row in top] == [
        Decimal("92.0000"),
        Decimal("81.0000"),
    ]
    assert [row.decision for row in buy_only] == ["BUY_TEST_1", "BUY_TEST_1"]


def test_export_opportunities_returns_exported_count(
    db_session: Session, clean_db: None, tmp_path
) -> None:
    product, query = create_product_and_query(db_session)
    repository = OpportunityRepository(db_session)
    repository.save_snapshot(**snapshot_values(product, query, score="72.0000", decision="WATCH"))
    repository.save_snapshot(
        **snapshot_values(product, query, score="88.0000", decision="BUY_TEST_1")
    )
    output_path = tmp_path / "opportunities.csv"

    count = ReportingService(db_session).export_opportunities(output_path, decision="BUY_TEST_1")

    with output_path.open(encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert count == 1
    assert len(rows) == count
    assert rows[0]["decision"] == "BUY_TEST_1"
    assert rows[0]["opportunity_score"] == "88.0000"


def test_export_audit_filters_run_and_returns_exported_count(
    db_session: Session, clean_db: None, tmp_path
) -> None:
    selected_run_id = str(uuid4())
    repository = RunRepository(db_session)
    repository.add_audit_log(
        run_id=selected_run_id,
        entity_type="opportunity",
        entity_id=7,
        action="calculated",
        actor="calculator",
        after_value={"decision": "BUY_TEST_1"},
    )
    repository.add_audit_log(
        run_id=str(uuid4()),
        entity_type="opportunity",
        entity_id=8,
        action="calculated",
        actor="calculator",
        after_value={"decision": "WATCH"},
    )
    output_path = tmp_path / "audit.jsonl"

    count = ReportingService(db_session).export_audit(output_path, run_id=selected_run_id)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert count == 1
    assert len(rows) == count
    assert rows[0]["run_id"] == selected_run_id
    assert rows[0]["after_value"] == {"decision": "BUY_TEST_1"}
