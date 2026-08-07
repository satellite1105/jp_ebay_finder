"""Import fee profile CSV files into validated domain models."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from opportunity_finder.domain.models import FeeProfile
from opportunity_finder.importers.csv_common import (
    QuarantineCollector,
    QuarantinedRow,
    compute_file_sha256,
    sanitize_formula_cell,
)

REQUIRED_COLUMNS = frozenset(
    {
        "profile_code",
        "marketplace",
        "variable_fee_rate",
        "fixed_fee_currency",
        "fixed_fee_amount",
        "effective_from",
    }
)
TEXT_COLUMNS = frozenset({"profile_code", "marketplace", "category_code", "fixed_fee_currency"})
OMIT_IF_BLANK_COLUMNS = frozenset(
    {
        "category_code",
        "international_fee_rate",
        "ad_rate",
        "return_reserve_rate",
        "effective_to",
    }
)


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Validated rows and diagnostics from a fee CSV import."""

    valid_rows: list[FeeProfile]
    quarantined_rows: list[QuarantinedRow]
    file_sha256: str
    rows_total: int


def _validate_columns(fieldnames: list[str] | None) -> None:
    missing = sorted(REQUIRED_COLUMNS.difference(fieldnames or []))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def _prepare_row(row: dict[str | None, str | list[str] | None]) -> dict[str, object]:
    if None in row:
        raise ValueError("Row contains more values than the CSV header")

    prepared: dict[str, object] = {}
    for key, value in row.items():
        if key is None:
            continue
        if isinstance(value, list):
            raise TypeError("Row contains more values than the CSV header")
        if key in OMIT_IF_BLANK_COLUMNS and value in (None, ""):
            continue
        elif key in TEXT_COLUMNS and isinstance(value, str):
            prepared[key] = sanitize_formula_cell(value)
        else:
            prepared[key] = value
    return prepared


def import_fees_csv(path: str | Path) -> ImportResult:
    """Read a fee profile CSV, isolating invalid rows from valid results."""
    source_path = Path(path)
    file_sha256 = compute_file_sha256(source_path)
    valid_rows: list[FeeProfile] = []
    quarantine = QuarantineCollector()
    rows_total = 0

    with source_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, strict=True)
        _validate_columns(reader.fieldnames)

        for row in reader:
            rows_total += 1
            try:
                prepared = _prepare_row(row)
                profile = FeeProfile.model_validate(prepared)
            except (TypeError, ValueError, ValidationError) as error:
                quarantine.quarantine_row(row, error)
                continue
            valid_rows.append(profile)

    return ImportResult(
        valid_rows=valid_rows,
        quarantined_rows=quarantine.rows,
        file_sha256=file_sha256,
        rows_total=rows_total,
    )
