import csv
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from opportunity_finder.importers.fees_csv import import_fees_csv
from opportunity_finder.importers.shipping_csv import import_shipping_csv

SHIPPING_FIELDNAMES = [
    "profile_code",
    "destination_country",
    "min_weight_g",
    "max_weight_g",
    "service_name",
    "shipping_jpy",
    "tracking",
    "included_insurance_jpy",
    "effective_from",
    "effective_to",
]
FEE_FIELDNAMES = [
    "profile_code",
    "marketplace",
    "category_code",
    "variable_fee_rate",
    "international_fee_rate",
    "fixed_fee_currency",
    "fixed_fee_amount",
    "ad_rate",
    "return_reserve_rate",
    "effective_from",
    "effective_to",
]


def shipping_row(**overrides: str) -> dict[str, str]:
    row = {
        "profile_code": "US_DDP_001",
        "destination_country": "US",
        "min_weight_g": "0",
        "max_weight_g": "500",
        "service_name": "SpeedPAK Economy",
        "shipping_jpy": "1800",
        "tracking": "true",
        "included_insurance_jpy": "0",
        "effective_from": "2026-08-01",
        "effective_to": "",
    }
    row.update(overrides)
    return row


def fee_row(**overrides: str) -> dict[str, str]:
    row = {
        "profile_code": "EBAY_US_DEFAULT",
        "marketplace": "EBAY_US",
        "category_code": "",
        "variable_fee_rate": "0.136",
        "international_fee_rate": "0.0135",
        "fixed_fee_currency": "USD",
        "fixed_fee_amount": "0.40",
        "ad_rate": "0.03",
        "return_reserve_rate": "0.03",
        "effective_from": "2026-08-01",
        "effective_to": "",
    }
    row.update(overrides)
    return row


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    *,
    encoding: str = "utf-8",
) -> bytes:
    with path.open("w", encoding=encoding, newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def test_imports_valid_shipping_rates(tmp_path: Path) -> None:
    path = tmp_path / "shipping_rates.csv"
    write_csv(path, SHIPPING_FIELDNAMES, [shipping_row()])

    result = import_shipping_csv(path)

    assert result.rows_total == 1
    assert result.quarantined_rows == []
    assert len(result.valid_rows) == 1
    quote = result.valid_rows[0]
    assert quote.profile_code == "US_DDP_001"
    assert quote.shipping_jpy == Decimal(1800)
    assert quote.tracking is True
    assert quote.effective_to is None


def test_shipping_invalid_weight_range_is_quarantined_and_processing_continues(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shipping_rates.csv"
    write_csv(
        path,
        SHIPPING_FIELDNAMES,
        [
            shipping_row(profile_code="bad", min_weight_g="500", max_weight_g="500"),
            shipping_row(profile_code="valid", min_weight_g="500", max_weight_g="1000"),
        ],
    )

    result = import_shipping_csv(path)

    assert result.rows_total == 2
    assert [quote.profile_code for quote in result.valid_rows] == ["valid"]
    assert len(result.quarantined_rows) == 1
    assert result.quarantined_rows[0].row["profile_code"] == "bad"
    assert "min_weight_g must be less than max_weight_g" in result.quarantined_rows[0].error


def test_shipping_missing_required_column_rejects_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "shipping_rates.csv"
    fieldnames = [name for name in SHIPPING_FIELDNAMES if name != "service_name"]
    row = shipping_row()
    row.pop("service_name")
    write_csv(path, fieldnames, [row])

    with pytest.raises(ValueError, match=r"Missing required columns: service_name"):
        import_shipping_csv(path)


def test_imports_valid_fee_profiles(tmp_path: Path) -> None:
    path = tmp_path / "fee_profiles.csv"
    write_csv(path, FEE_FIELDNAMES, [fee_row()])

    result = import_fees_csv(path)

    assert result.rows_total == 1
    assert result.quarantined_rows == []
    assert len(result.valid_rows) == 1
    profile = result.valid_rows[0]
    assert profile.profile_code == "EBAY_US_DEFAULT"
    assert profile.category_code is None
    assert profile.variable_fee_rate == Decimal("0.136")
    assert profile.fixed_fee_amount == Decimal("0.40")
    assert profile.effective_to is None


@pytest.mark.parametrize(
    ("field", "invalid_rate"),
    [
        ("variable_fee_rate", "1.01"),
        ("international_fee_rate", "-0.01"),
        ("ad_rate", "1.01"),
        ("return_reserve_rate", "-0.01"),
    ],
)
def test_fee_rate_outside_zero_to_one_is_quarantined(
    tmp_path: Path, field: str, invalid_rate: str
) -> None:
    path = tmp_path / "fee_profiles.csv"
    write_csv(
        path,
        FEE_FIELDNAMES,
        [fee_row(profile_code="bad", **{field: invalid_rate}), fee_row(profile_code="valid")],
    )

    result = import_fees_csv(path)

    assert [profile.profile_code for profile in result.valid_rows] == ["valid"]
    assert len(result.quarantined_rows) == 1
    assert result.quarantined_rows[0].row[field] == invalid_rate
    assert result.quarantined_rows[0].error


def test_fees_missing_required_column_rejects_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "fee_profiles.csv"
    fieldnames = [name for name in FEE_FIELDNAMES if name != "fixed_fee_currency"]
    row = fee_row()
    row.pop("fixed_fee_currency")
    write_csv(path, fieldnames, [row])

    with pytest.raises(ValueError, match=r"Missing required columns: fixed_fee_currency"):
        import_fees_csv(path)


@pytest.mark.parametrize(
    ("filename", "fieldnames", "row_factory", "importer"),
    [
        ("shipping_rates.csv", SHIPPING_FIELDNAMES, shipping_row, import_shipping_csv),
        ("fee_profiles.csv", FEE_FIELDNAMES, fee_row, import_fees_csv),
    ],
)
def test_reads_utf8_bom_and_calculates_file_sha256(
    tmp_path: Path,
    filename: str,
    fieldnames: list[str],
    row_factory: object,
    importer: object,
) -> None:
    path = tmp_path / filename
    contents = write_csv(path, fieldnames, [row_factory()], encoding="utf-8-sig")  # type: ignore[operator]

    result = importer(path)  # type: ignore[operator]

    assert len(result.valid_rows) == 1
    assert result.quarantined_rows == []
    assert result.file_sha256 == hashlib.sha256(contents).hexdigest()


def test_formula_prefixes_are_neutralized_in_text_columns(tmp_path: Path) -> None:
    shipping_path = tmp_path / "shipping_rates.csv"
    fees_path = tmp_path / "fee_profiles.csv"
    write_csv(shipping_path, SHIPPING_FIELDNAMES, [shipping_row(service_name="=1+1")])
    write_csv(fees_path, FEE_FIELDNAMES, [fee_row(category_code="@danger")])

    shipping_result = import_shipping_csv(shipping_path)
    fees_result = import_fees_csv(fees_path)

    assert shipping_result.valid_rows[0].service_name == "'=1+1"
    assert fees_result.valid_rows[0].category_code == "'@danger"
