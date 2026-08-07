from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from opportunity_finder.domain.models import MarketResearchInput
from opportunity_finder.importers.product_research_csv import (
    CSV_COLUMNS,
    import_product_research_csv,
)


def _valid_row(**overrides: str) -> dict[str, str]:
    row = {
        "external_key": "local-001",
        "search_query": "Brand MODEL-1",
        "marketplace": "EBAY_US",
        "condition": "new",
        "lookback_days": "90",
        "sold_count": "12",
        "active_count": "30",
        "median_sold_price_usd": "69.99",
        "average_sold_price_usd": "68.50",
        "median_buyer_shipping_usd": "0",
        "sell_through_rate": "0.2857",
        "checked_at": "2026-08-06T09:30:00+09:00",
        "notes": "Product Research manual export",
    }
    row.update(overrides)
    return row


def _write_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    fieldnames: tuple[str, ...] | list[str] = CSV_COLUMNS,
    encoding: str = "utf-8",
) -> None:
    with path.open("w", encoding=encoding, newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_imports_every_valid_row_as_market_research_input(tmp_path: Path) -> None:
    path = tmp_path / "product_research.csv"
    _write_csv(
        path,
        [
            _valid_row(),
            _valid_row(
                external_key="local-002",
                search_query="Used model",
                condition="used",
                sold_count="",
                notes="",
            ),
        ],
    )

    result = import_product_research_csv(path)

    assert len(result.records) == 2
    assert result.errors == []
    assert all(isinstance(record, MarketResearchInput) for record in result.records)
    assert result.records[0].median_sold_price_usd == Decimal("69.99")
    assert result.records[0].checked_at == datetime.fromisoformat("2026-08-06T09:30:00+09:00")
    assert result.records[1].sold_count is None
    assert result.records[1].notes is None


def test_missing_required_column_returns_file_error(tmp_path: Path) -> None:
    path = tmp_path / "missing-column.csv"
    fieldnames = [column for column in CSV_COLUMNS if column != "external_key"]
    _write_csv(path, [_valid_row()], fieldnames=fieldnames)

    result = import_product_research_csv(path)

    assert result.records == []
    assert len(result.errors) == 1
    assert "missing required columns: external_key" in result.errors[0].error


def test_duplicate_row_is_quarantined(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.csv"
    duplicate = _valid_row()
    _write_csv(path, [duplicate, duplicate])

    result = import_product_research_csv(path)

    assert len(result.records) == 1
    assert len(result.errors) == 1
    assert result.errors[0].error == "duplicate row"


def test_reads_utf8_bom_encoded_file(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    _write_csv(path, [_valid_row(notes="日本語メモ")], encoding="utf-8-sig")

    result = import_product_research_csv(path)

    assert len(result.records) == 1
    assert result.records[0].external_key == "local-001"
    assert result.records[0].notes == "日本語メモ"
    assert result.errors == []


def test_invalid_date_and_number_are_isolated_from_valid_rows(tmp_path: Path) -> None:
    path = tmp_path / "mixed.csv"
    _write_csv(
        path,
        [
            _valid_row(external_key="bad-date", checked_at="not-a-date"),
            _valid_row(external_key="valid"),
            _valid_row(external_key="bad-number", sold_count="twelve"),
        ],
    )

    result = import_product_research_csv(path)

    assert [record.external_key for record in result.records] == ["valid"]
    assert len(result.errors) == 2
    assert {error.row["external_key"] for error in result.errors} == {
        "bad-date",
        "bad-number",
    }


def test_sell_through_rates_outside_zero_to_one_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid-rates.csv"
    _write_csv(
        path,
        [
            _valid_row(external_key="below", sell_through_rate="-0.01"),
            _valid_row(external_key="valid", sell_through_rate="1"),
            _valid_row(external_key="above", sell_through_rate="1.01"),
        ],
    )

    result = import_product_research_csv(path)

    assert [record.external_key for record in result.records] == ["valid"]
    assert len(result.errors) == 2


def test_file_sha256_matches_digest_of_original_bytes(tmp_path: Path) -> None:
    path = tmp_path / "hash.csv"
    _write_csv(path, [_valid_row()])
    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    result = import_product_research_csv(path)

    assert result.file_sha256 == expected_hash


def test_formula_like_text_cells_are_neutralized(tmp_path: Path) -> None:
    path = tmp_path / "formula.csv"
    _write_csv(path, [_valid_row(search_query='=HYPERLINK("https://invalid")', notes="@cmd")])

    result = import_product_research_csv(path)

    assert result.errors == []
    assert result.records[0].search_query.startswith("'=")
    assert result.records[0].notes == "'@cmd"
