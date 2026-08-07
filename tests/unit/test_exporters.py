from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from decimal import Decimal

from opportunity_finder.exporters.audit_jsonl import export_audit_jsonl
from opportunity_finder.exporters.opportunities_csv import (
    COST_COMPONENT_COLUMNS,
    export_opportunities_csv,
)


def opportunity_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": 7,
        "product_id": 11,
        "query_id": 13,
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
        "opportunity_score": Decimal("82.5000"),
        "data_confidence": Decimal("91.2500"),
        "decision": "BUY_TEST_1",
        "reason_codes": ["PROFIT_TARGET_MET", "DEMAND_CONFIRMED"],
        "input_snapshot": {"formula_like": "=SUM(A1:A2)"},
        "calculated_at": datetime(2026, 8, 8, 2, 3, 4, 567890, tzinfo=UTC),
        "calculator_version": "test-v1",
    }
    record.update(overrides)
    return record


def test_opportunities_csv_sanitizes_every_formula_prefix(tmp_path) -> None:
    output_path = tmp_path / "opportunities.csv"
    records = [
        opportunity_record(scenario="=scenario"),
        opportunity_record(scenario="+scenario"),
        opportunity_record(scenario="-scenario"),
        opportunity_record(scenario="@scenario"),
    ]

    export_opportunities_csv(records, output_path)

    with output_path.open(encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert [row["scenario"] for row in rows] == [
        "'=scenario",
        "'+scenario",
        "'-scenario",
        "'@scenario",
    ]
    assert all(row["input_snapshot"].startswith("{") for row in rows)


def test_opportunities_csv_cost_components_sum_to_total_cost(tmp_path) -> None:
    output_path = tmp_path / "opportunities.csv"

    export_opportunities_csv([opportunity_record()], output_path)

    with output_path.open(encoding="utf-8", newline="") as csv_file:
        row = next(csv.DictReader(csv_file))

    component_total = sum(Decimal(row[column]) for column in COST_COMPONENT_COLUMNS)
    assert component_total == Decimal(row["total_cost_jpy"])


def test_audit_jsonl_writes_one_valid_json_object_per_line(tmp_path) -> None:
    output_path = tmp_path / "audit.jsonl"
    records = [
        {
            "id": 1,
            "run_id": None,
            "entity_type": "product",
            "entity_id": 42,
            "action": "created",
            "actor": "system",
            "before_value": None,
            "after_value": {"cost": Decimal("1234.5000")},
            "reason": None,
            "created_at": datetime(2026, 8, 8, 3, 4, 5, 678901, tzinfo=UTC),
        },
        {
            "id": 2,
            "run_id": "run-2",
            "entity_type": "opportunity",
            "entity_id": 7,
            "action": "calculated",
            "actor": "calculator",
            "before_value": {"decision": "WATCH"},
            "after_value": {"decision": "BUY_TEST_1"},
            "reason": "score increased",
            "created_at": datetime(2026, 8, 8, 3, 5, 6, tzinfo=UTC),
        },
    ]

    export_audit_jsonl(records, output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    decoded = [json.loads(line) for line in lines]
    assert len(lines) == len(records)
    assert [row["id"] for row in decoded] == [1, 2]
    assert decoded[0]["after_value"] == {"cost": "1234.5000"}
    assert decoded[0]["created_at"] == "2026-08-08T03:04:05.678901+00:00"
    assert decoded[1]["after_value"]["decision"] == "BUY_TEST_1"
