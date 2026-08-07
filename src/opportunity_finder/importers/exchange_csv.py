"""Validate and transform exchange-rate CSV files without writing to the database."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opportunity_finder.importers.csv_common import (
    QuarantineCollector,
    QuarantinedRow,
    compute_file_sha256,
    sanitize_formula_cell,
)

CSV_COLUMNS = ("base_currency", "quote_currency", "rate", "effective_at")
STRING_COLUMNS = ("base_currency", "quote_currency")


class ExchangeRateInput(BaseModel):
    """A validated exchange-rate observation read from a CSV row."""

    model_config = ConfigDict(str_strip_whitespace=True)

    base_currency: str = Field(min_length=3, max_length=3)
    quote_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)
    effective_at: datetime


@dataclass(frozen=True, slots=True)
class ImportResult:
    """The validated and quarantined rows produced by an import attempt."""

    valid_rows: list[ExchangeRateInput]
    quarantined_rows: list[QuarantinedRow]
    file_sha256: str
    rows_total: int


def _validate_columns(fieldnames: list[str] | None) -> None:
    actual_columns = fieldnames or []
    missing = [column for column in CSV_COLUMNS if column not in actual_columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    unexpected = [column for column in actual_columns if column not in CSV_COLUMNS]
    if unexpected:
        raise ValueError(f"Unexpected columns: {', '.join(unexpected)}")


def _sanitize_row(
    row: dict[str | None, str | list[str] | None],
) -> dict[str, str | None]:
    if None in row:
        raise ValueError("Row contains more values than the CSV header")

    sanitized: dict[str, str | None] = {
        column: value if isinstance(value, str) or value is None else None
        for column, value in row.items()
        if column is not None
    }
    for column in STRING_COLUMNS:
        value = sanitized.get(column)
        if isinstance(value, str):
            sanitized[column] = sanitize_formula_cell(value)
    return sanitized


def import_exchange_csv(path: str | Path) -> ImportResult:
    """Read an exchange-rate CSV and isolate invalid data rows.

    Header/schema errors remain file-level errors because no row can be interpreted
    reliably when the CSV shape is invalid. Validation errors in individual rows are
    quarantined so subsequent valid rows continue to be transformed.
    """

    csv_path = Path(path)
    file_sha256 = compute_file_sha256(csv_path)
    valid_rows: list[ExchangeRateInput] = []
    quarantine = QuarantineCollector()
    rows_total = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, strict=True)
        _validate_columns(reader.fieldnames)

        for row in reader:
            rows_total += 1
            try:
                sanitized_row = _sanitize_row(row)
                valid_rows.append(ExchangeRateInput.model_validate(sanitized_row))
            except (TypeError, ValueError, ValidationError) as error:
                quarantine.quarantine_row(row, error)

    return ImportResult(
        file_sha256=file_sha256,
        rows_total=rows_total,
        valid_rows=valid_rows,
        quarantined_rows=quarantine.rows,
    )
