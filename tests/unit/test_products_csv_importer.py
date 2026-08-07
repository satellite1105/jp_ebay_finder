import csv
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from opportunity_finder.importers.products_csv import import_products_csv

FIELDNAMES = [
    "external_key",
    "jan",
    "title",
    "brand",
    "model_number",
    "condition",
    "source_cost_jpy",
    "source_shipping_jpy",
    "weight_g",
    "packed_weight_g",
    "origin_country",
    "supplier_name",
    "supplier_url",
    "checked_at",
]


def product_row(**overrides: str) -> dict[str, str]:
    row = {
        "external_key": "local-001",
        "jan": "4900000000000",
        "title": "Test product",
        "brand": "Brand",
        "model_number": "MODEL-1",
        "condition": "new",
        "source_cost_jpy": "1980",
        "source_shipping_jpy": "0",
        "weight_g": "300",
        "packed_weight_g": "380",
        "origin_country": "JP",
        "supplier_name": "Shop",
        "supplier_url": "https://example.invalid",
        "checked_at": "2026-08-06T09:00:00+09:00",
    }
    row.update(overrides)
    return row


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    fieldnames: list[str] | None = None,
    encoding: str = "utf-8",
) -> bytes:
    with path.open("w", encoding=encoding, newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames or FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def test_imports_all_valid_rows_as_product_inputs(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_csv(
        path,
        [
            product_row(),
            product_row(
                external_key="local-002",
                jan="",
                brand="",
                packed_weight_g="",
                supplier_name="",
                supplier_url="",
            ),
        ],
    )

    result = import_products_csv(path)

    assert result.rows_total == 2
    assert result.quarantined_rows == []
    assert [product.external_key for product in result.valid_rows] == ["local-001", "local-002"]
    assert result.valid_rows[0].jan_code == "4900000000000"
    assert result.valid_rows[0].source_cost_jpy == Decimal(1980)
    assert result.valid_rows[1].jan_code is None
    assert result.valid_rows[1].packed_weight_g is None


def test_missing_required_column_rejects_the_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    fieldnames = [name for name in FIELDNAMES if name != "title"]
    row = product_row()
    row.pop("title")
    write_csv(path, [row], fieldnames=fieldnames)

    with pytest.raises(ValueError, match=r"Missing required columns: title"):
        import_products_csv(path)


def test_duplicate_external_key_uses_the_last_valid_row(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_csv(
        path,
        [
            product_row(title="First version", source_cost_jpy="1000"),
            product_row(external_key="local-002", title="Other product"),
            product_row(title="Final version", source_cost_jpy="1500"),
        ],
    )

    result = import_products_csv(path)

    assert result.rows_total == 3
    assert len(result.valid_rows) == 2
    adopted = next(row for row in result.valid_rows if row.external_key == "local-001")
    assert adopted.title == "Final version"
    assert adopted.source_cost_jpy == Decimal(1500)


def test_reads_utf8_csv_with_bom(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_csv(path, [product_row(title="日本語の商品名")], encoding="utf-8-sig")

    result = import_products_csv(path)

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].external_key == "local-001"
    assert result.valid_rows[0].title == "日本語の商品名"


def test_quarantines_invalid_date_and_number_but_continues(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_csv(
        path,
        [
            product_row(external_key="valid-1"),
            product_row(external_key="bad-date", checked_at="not-a-date"),
            product_row(external_key="bad-number", source_cost_jpy="not-a-number"),
            product_row(external_key="valid-2", source_cost_jpy="2500"),
        ],
    )

    result = import_products_csv(path)

    assert result.rows_total == 4
    assert [row.external_key for row in result.valid_rows] == ["valid-1", "valid-2"]
    assert [row.row["external_key"] for row in result.quarantined_rows] == [
        "bad-date",
        "bad-number",
    ]
    assert all(row.error for row in result.quarantined_rows)


def test_file_sha256_matches_source_file(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    contents = write_csv(path, [product_row()])

    result = import_products_csv(path)

    assert result.file_sha256 == hashlib.sha256(contents).hexdigest()


def test_formula_prefixes_are_neutralized_before_validation(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_csv(path, [product_row(title="=1+1", supplier_name="@danger")])

    result = import_products_csv(path)

    assert result.valid_rows[0].title == "'=1+1"
    assert result.valid_rows[0].supplier_name == "'@danger"
