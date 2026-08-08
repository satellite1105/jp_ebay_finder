"""Export opportunity snapshots to a spreadsheet-safe CSV file."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from opportunity_finder.importers.csv_common import sanitize_formula_cell

OPPORTUNITY_COLUMNS = (
    "id",
    "product_id",
    "query_id",
    "scenario",
    "source_cost_jpy",
    "buyer_total_market_currency",
    "market_currency",
    "exchange_rate",
    "revenue_jpy",
    "marketplace_fees_jpy",
    "advertising_reserve_jpy",
    "return_reserve_jpy",
    "duty_processing_jpy",
    "international_shipping_jpy",
    "packaging_jpy",
    "other_costs_jpy",
    "total_cost_jpy",
    "net_profit_jpy",
    "net_margin",
    "break_even_buyer_total",
    "capital_required_jpy",
    "capital_efficiency",
    "opportunity_score",
    "data_confidence",
    "decision",
    "reason_codes",
    "input_snapshot",
    "calculated_at",
    "calculator_version",
)

# These columns are exhaustive for the cost breakdown represented by the
# opportunity_snapshots schema. Their sum must equal total_cost_jpy (spec S12).
COST_COMPONENT_COLUMNS = (
    "source_cost_jpy",
    "marketplace_fees_jpy",
    "advertising_reserve_jpy",
    "return_reserve_jpy",
    "duty_processing_jpy",
    "international_shipping_jpy",
    "packaging_jpy",
    "other_costs_jpy",
)


def export_opportunities_csv(
    records: Iterable[Mapping[str, Any] | object], path: str | Path
) -> None:
    """Write opportunity records using a stable, complete column order.

    Records may be SQLAlchemy model instances or mapping-like test/application
    values. Every header and data cell is converted to text and passed through
    ``sanitize_formula_cell`` immediately before it reaches the CSV writer.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(_sanitize_cell(column) for column in OPPORTUNITY_COLUMNS)
        for record in records:
            writer.writerow(
                _sanitize_cell(_record_value(record, column)) for column in OPPORTUNITY_COLUMNS
            )


def _record_value(record: Mapping[str, Any] | object, column: str) -> Any:
    if isinstance(record, Mapping):
        return record[column]
    return getattr(record, column)


def _sanitize_cell(value: object) -> str:
    return sanitize_formula_cell(_serialize_cell(value))


def _serialize_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=isinstance(value, dict),
            default=_json_default,
        )
    return str(value)


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
