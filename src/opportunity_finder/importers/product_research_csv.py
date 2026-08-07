"""Parse and validate Product Research CSV exports."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from opportunity_finder.domain.models import MarketResearchInput
from opportunity_finder.importers.csv_common import (
    QuarantineCollector,
    QuarantinedRow,
    compute_file_sha256,
    sanitize_formula_cell,
)

CSV_COLUMNS = (
    "external_key",
    "search_query",
    "marketplace",
    "condition",
    "lookback_days",
    "sold_count",
    "active_count",
    "median_sold_price_usd",
    "average_sold_price_usd",
    "median_buyer_shipping_usd",
    "sell_through_rate",
    "checked_at",
    "notes",
)

# These fields have no default in MarketResearchInput. Optional CSV cells may be
# empty, but a file without one of these columns cannot produce a valid record.
REQUIRED_COLUMNS = frozenset(
    {
        "external_key",
        "search_query",
        "lookback_days",
        "checked_at",
    }
)


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Validated records, isolated row errors, and the source file digest."""

    records: list[MarketResearchInput]
    errors: list[QuarantinedRow]
    file_sha256: str

    @property
    def items(self) -> list[MarketResearchInput]:
        """Compatibility alias for callers that refer to imported items."""
        return self.records

    @property
    def imported(self) -> list[MarketResearchInput]:
        """Compatibility alias for callers that refer to imported records."""
        return self.records

    @property
    def quarantined_rows(self) -> list[QuarantinedRow]:
        """Compatibility alias for the rejected rows."""
        return self.errors


def _sanitize_row(raw_row: dict[str | None, str | None]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for column, value in raw_row.items():
        if column is None:
            raise ValueError("row has more values than the CSV header")
        sanitized[column] = sanitize_formula_cell(value) if value is not None else None
    return sanitized


def _record_key(row: dict[str, object]) -> tuple[object, ...]:
    """Return a stable identity for detecting an exact duplicate CSV row."""
    return tuple(row.get(column) for column in CSV_COLUMNS)


def _model_payload(row: dict[str, object]) -> dict[str, object]:
    # Omitting empty optional cells allows the Pydantic model defaults to apply.
    return {column: value for column, value in row.items() if value not in (None, "")}


def import_product_research_csv(path: str | Path) -> ImportResult:
    """Read ``product_research.csv`` without writing to persistent storage.

    Invalid and duplicate rows are quarantined independently so later valid rows
    continue to be parsed. UTF-8 BOMs are accepted via the ``utf-8-sig`` codec.
    """

    csv_path = Path(path)
    file_sha256 = compute_file_sha256(csv_path)
    records: list[MarketResearchInput] = []
    quarantine = QuarantineCollector()
    seen_rows: set[tuple[object, ...]] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        fieldnames = reader.fieldnames or []
        missing_columns = sorted(REQUIRED_COLUMNS.difference(fieldnames))
        if missing_columns:
            quarantine.quarantine_row(
                {},
                f"missing required columns: {', '.join(missing_columns)}",
            )
            return ImportResult(
                records=records,
                errors=quarantine.rows,
                file_sha256=file_sha256,
            )

        for raw_row in reader:
            try:
                row = _sanitize_row(raw_row)
                record_key = _record_key(row)
                if record_key in seen_rows:
                    raise ValueError("duplicate row")
                seen_rows.add(record_key)
                records.append(MarketResearchInput.model_validate(_model_payload(row)))
            except (TypeError, ValueError) as error:
                quarantine.quarantine_row(raw_row, error)

    return ImportResult(
        records=records,
        errors=quarantine.rows,
        file_sha256=file_sha256,
    )
