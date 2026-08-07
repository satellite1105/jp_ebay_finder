"""Parse and validate products.csv without performing persistence."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from opportunity_finder.domain.models import ProductInput
from opportunity_finder.importers.csv_common import (
    QuarantineCollector,
    QuarantinedRow,
    compute_file_sha256,
    sanitize_formula_cell,
)

REQUIRED_COLUMNS = frozenset(
    {
        "external_key",
        "title",
        "condition",
        "source_cost_jpy",
        "weight_g",
        "origin_country",
        "checked_at",
    }
)


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Result of parsing a product CSV file."""

    valid_rows: list[ProductInput]
    quarantined_rows: list[QuarantinedRow]
    file_sha256: str
    rows_total: int


def import_products_csv(path: str | Path) -> ImportResult:
    """Read products.csv and isolate invalid rows from valid products.

    Valid duplicate keys use last-write-wins semantics. This makes a later corrected
    row in the same input file authoritative without requiring database knowledge.
    """
    csv_path = Path(path)
    file_sha256 = compute_file_sha256(csv_path)
    quarantine = QuarantineCollector()
    valid_by_external_key: dict[str, ProductInput] = {}
    rows_total = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, strict=True)
        fieldnames = set(reader.fieldnames or ())
        missing_columns = REQUIRED_COLUMNS - fieldnames
        if missing_columns:
            # A missing required header changes the meaning of every row, so fail the
            # whole file instead of producing one identical quarantine error per row.
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required columns: {missing}")

        for csv_row in reader:
            rows_total += 1
            raw_row = _copy_csv_row(csv_row)
            try:
                values = _product_values(csv_row)
                product = ProductInput.model_validate(values)
            except (TypeError, ValueError, ValidationError) as error:
                quarantine.quarantine_row(raw_row, error)
                continue

            # Reinsert so result order also reflects the winning row's position.
            valid_by_external_key.pop(product.external_key, None)
            valid_by_external_key[product.external_key] = product

    return ImportResult(
        valid_rows=list(valid_by_external_key.values()),
        quarantined_rows=quarantine.rows,
        file_sha256=file_sha256,
        rows_total=rows_total,
    )


def _product_values(csv_row: dict[str | None, str | list[str] | None]) -> dict[str, object]:
    if None in csv_row:
        raise ValueError("Row contains more values than the CSV header")

    sanitized: dict[str, str | None] = {}
    for column, value in csv_row.items():
        if column is None:
            continue
        if value is None:
            sanitized[column] = None
        elif isinstance(value, list):
            raise ValueError("Row contains more values than the CSV header")
        else:
            sanitized[column] = sanitize_formula_cell(value)

    values: dict[str, object] = {
        "external_key": sanitized.get("external_key"),
        "jan_code": _none_if_blank(sanitized.get("jan")),
        "title": sanitized.get("title"),
        "brand": _none_if_blank(sanitized.get("brand")),
        "model_number": _none_if_blank(sanitized.get("model_number")),
        "condition": sanitized.get("condition"),
        "source_cost_jpy": sanitized.get("source_cost_jpy"),
        "weight_g": sanitized.get("weight_g"),
        "packed_weight_g": _none_if_blank(sanitized.get("packed_weight_g")),
        "origin_country": sanitized.get("origin_country"),
        "supplier_name": _none_if_blank(sanitized.get("supplier_name")),
        "supplier_url": _none_if_blank(sanitized.get("supplier_url")),
        "checked_at": sanitized.get("checked_at"),
    }

    source_shipping = sanitized.get("source_shipping_jpy")
    if source_shipping not in (None, ""):
        values["source_shipping_jpy"] = source_shipping
    return values


def _none_if_blank(value: str | None) -> str | None:
    return None if value in (None, "") else value


def _copy_csv_row(
    csv_row: dict[str | None, str | list[str] | None],
) -> dict[str, object]:
    raw_row: dict[str, object] = {}
    for column, value in csv_row.items():
        key = column if column is not None else "__extra_columns__"
        raw_row[key] = value
    return raw_row
