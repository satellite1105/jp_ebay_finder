"""Integration tests for the report and export CLI commands against MySQL."""

from __future__ import annotations

import csv
import json
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from pytest import MonkeyPatch
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder import cli
from opportunity_finder.cli_commands import report_commands
from opportunity_finder.db.models import MarketQuery, Product
from opportunity_finder.db.repositories.opportunity_repository import OpportunityRepository
from opportunity_finder.db.repositories.run_repository import RunRepository

runner = CliRunner()


def _use_test_session(monkeypatch: MonkeyPatch, db_session: Session) -> None:
    """Make the CLI use the transaction-managed integration-test session."""
    monkeypatch.setattr(
        report_commands,
        "create_session_factory",
        lambda: lambda: nullcontext(db_session),
    )


def _create_product_and_query(db_session: Session) -> tuple[Product, MarketQuery]:
    now = datetime(2026, 8, 8, 1, 2, 3, 456789, tzinfo=UTC).replace(tzinfo=None)
    unique_key = uuid4().hex
    product = Product(
        internal_sku=f"cli-report-{unique_key}",
        normalized_name=f"cli report product {unique_key}",
        original_name=f"CLI Report Product {unique_key}",
        created_at=now,
        updated_at=now,
    )
    db_session.add(product)
    db_session.flush()

    query = MarketQuery(
        product_id=product.id,
        query_text=f"cli report query {unique_key}",
        query_type="KEYWORD",
        created_at=now,
        updated_at=now,
    )
    db_session.add(query)
    db_session.flush()
    return product, query


def _snapshot_values(
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


def _save_snapshot(
    db_session: Session,
    product: Product,
    query: MarketQuery,
    *,
    score: str,
    decision: str,
) -> None:
    OpportunityRepository(db_session).save_snapshot(
        **_snapshot_values(product, query, score=score, decision=decision)
    )


def test_report_top_displays_ranked_decision_filtered_table(
    db_session: Session,
    clean_db: None,
    monkeypatch: MonkeyPatch,
) -> None:
    product, query = _create_product_and_query(db_session)
    _save_snapshot(
        db_session,
        product,
        query,
        score="99.0000",
        decision="WATCH",
    )
    _save_snapshot(
        db_session,
        product,
        query,
        score="92.0000",
        decision="BUY_TEST_1",
    )
    _use_test_session(monkeypatch, db_session)

    result = runner.invoke(
        cli.app,
        ["report", "top", "--limit", "1", "--decision", "BUY_TEST_1"],
    )

    assert result.exit_code == 0, result.output
    assert "Top Opportunities" in result.output
    assert "92.0000" in result.output
    assert "BUY_TEST_1" in result.output
    assert "99.0000" not in result.output


def test_export_opportunities_writes_csv_and_displays_count(
    db_session: Session,
    clean_db: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    product, query = _create_product_and_query(db_session)
    _save_snapshot(
        db_session,
        product,
        query,
        score="72.0000",
        decision="WATCH",
    )
    _save_snapshot(
        db_session,
        product,
        query,
        score="88.0000",
        decision="BUY_TEST_1",
    )
    _use_test_session(monkeypatch, db_session)
    output_path = tmp_path / "opportunities.csv"

    result = runner.invoke(
        cli.app,
        [
            "export",
            "opportunities",
            str(output_path),
            "--limit",
            "1",
            "--decision",
            "BUY_TEST_1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Exported 1 opportunity records" in result.output
    with output_path.open(encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert len(rows) == 1
    assert rows[0]["decision"] == "BUY_TEST_1"
    assert rows[0]["opportunity_score"] == "88.0000"


def test_export_audit_writes_jsonl_and_displays_count(
    db_session: Session,
    clean_db: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
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
    _use_test_session(monkeypatch, db_session)
    output_path = tmp_path / "audit.jsonl"

    result = runner.invoke(
        cli.app,
        ["export", "audit", str(output_path), "--run-id", selected_run_id],
    )

    assert result.exit_code == 0, result.output
    assert "Exported 1 audit records" in result.output
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == selected_run_id
    assert rows[0]["after_value"] == {"decision": "BUY_TEST_1"}
