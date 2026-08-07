"""Integration tests for CSV import CLI commands against MySQL."""

from __future__ import annotations

import csv
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder import cli
from opportunity_finder.cli_commands import import_commands
from opportunity_finder.db.models import (
    ExchangeRate,
    FeeRule,
    ImportBatch,
    MarketQuery,
    MarketResearchMetric,
    Product,
    ShippingRate,
)

runner = CliRunner()

PRODUCT_COLUMNS = [
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
RESEARCH_COLUMNS = [
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
]
SHIPPING_COLUMNS = [
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
FEE_COLUMNS = [
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
EXCHANGE_COLUMNS = ["base_currency", "quote_currency", "rate", "effective_at"]


@pytest.fixture
def cli_db_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """Route CLI-created sessions through the rollback-isolated real DB session."""
    monkeypatch.setattr(
        import_commands,
        "create_session_factory",
        lambda: lambda: nullcontext(db_session),
    )
    return db_session


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _assert_success_summary(output: str, *, already_processed: str = "no") -> None:
    assert "Import complete:" in output
    assert "total=1" in output
    expected_imported = 1 if already_processed == "no" else 0
    assert f"imported={expected_imported}" in output
    assert "quarantined=0" in output
    assert f"already_processed={already_processed}" in output


def test_products_command_saves_product_and_reports_duplicate_skip(
    cli_db_session: Session,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "products.csv",
        PRODUCT_COLUMNS,
        [
            {
                "external_key": "t26-product-001",
                "jan": "4900000000055",
                "title": "T26 CLI Product",
                "brand": "T26 Brand",
                "model_number": "T26-MODEL",
                "condition": "new",
                "source_cost_jpy": "2400",
                "source_shipping_jpy": "300",
                "weight_g": "350",
                "packed_weight_g": "420",
                "origin_country": "JP",
                "supplier_name": "T26 Shop",
                "supplier_url": "https://example.invalid/t26-product",
                "checked_at": "2042-08-08T09:00:00+09:00",
            }
        ],
    )

    first = runner.invoke(cli.app, ["import", "products", str(path)])
    second = runner.invoke(cli.app, ["import", "products", str(path)])

    assert first.exit_code == 0, first.output
    _assert_success_summary(first.output)
    assert second.exit_code == 0, second.output
    _assert_success_summary(second.output, already_processed="yes")
    product = cli_db_session.scalar(
        select(Product).where(Product.internal_sku == "t26-product-001")
    )
    assert product is not None
    assert product.original_name == "T26 CLI Product"
    assert (
        cli_db_session.scalar(
            select(func.count(ImportBatch.id)).where(ImportBatch.import_type == "products")
        )
        == 1
    )


def test_product_research_command_saves_query_and_metric(
    cli_db_session: Session,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "product_research.csv",
        RESEARCH_COLUMNS,
        [
            {
                "external_key": "t26-unlinked-product",
                "search_query": "T26 CLI Research Query",
                "marketplace": "EBAY_US",
                "condition": "new",
                "lookback_days": "90",
                "sold_count": "18",
                "active_count": "42",
                "median_sold_price_usd": "74.99",
                "average_sold_price_usd": "72.50",
                "median_buyer_shipping_usd": "5.99",
                "sell_through_rate": "0.30",
                "checked_at": "2042-08-08T09:30:00+09:00",
                "notes": "T26 CLI integration test",
            }
        ],
    )

    result = runner.invoke(cli.app, ["import", "product-research", str(path)])

    assert result.exit_code == 0, result.output
    _assert_success_summary(result.output)
    query = cli_db_session.scalar(
        select(MarketQuery).where(MarketQuery.query_text == "T26 CLI Research Query")
    )
    assert query is not None
    metric = cli_db_session.scalar(
        select(MarketResearchMetric).where(MarketResearchMetric.query_id == query.id)
    )
    assert metric is not None
    assert metric.sold_count == 18
    assert metric.import_batch_id is not None


def test_shipping_command_saves_rate(cli_db_session: Session, tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "shipping_rates.csv",
        SHIPPING_COLUMNS,
        [
            {
                "profile_code": "T26_US_TRACKED",
                "destination_country": "US",
                "min_weight_g": "0",
                "max_weight_g": "500",
                "service_name": "T26 Tracked",
                "shipping_jpy": "1900",
                "tracking": "true",
                "included_insurance_jpy": "200",
                "effective_from": "2042-08-01",
                "effective_to": "",
            }
        ],
    )

    result = runner.invoke(cli.app, ["import", "shipping", str(path)])

    assert result.exit_code == 0, result.output
    _assert_success_summary(result.output)
    rate = cli_db_session.scalar(
        select(ShippingRate).where(ShippingRate.profile_code == "T26_US_TRACKED")
    )
    assert rate is not None
    assert rate.shipping_jpy == Decimal("1900.0000")
    assert rate.import_batch_id is not None


def test_fees_command_saves_rule(cli_db_session: Session, tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "fee_profiles.csv",
        FEE_COLUMNS,
        [
            {
                "profile_code": "T26_EBAY_US",
                "marketplace": "EBAY_US",
                "category_code": "",
                "variable_fee_rate": "0.136",
                "international_fee_rate": "0.0135",
                "fixed_fee_currency": "USD",
                "fixed_fee_amount": "0.40",
                "ad_rate": "0.03",
                "return_reserve_rate": "0.03",
                "effective_from": "2042-08-01",
                "effective_to": "",
            }
        ],
    )

    result = runner.invoke(cli.app, ["import", "fees", str(path)])

    assert result.exit_code == 0, result.output
    _assert_success_summary(result.output)
    rule = cli_db_session.scalar(select(FeeRule).where(FeeRule.profile_code == "T26_EBAY_US"))
    assert rule is not None
    assert rule.variable_fee_rate == Decimal("0.136000")
    assert rule.import_batch_id is not None


def test_exchange_command_saves_rate(cli_db_session: Session, tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        EXCHANGE_COLUMNS,
        [
            {
                "base_currency": "T26",
                "quote_currency": "JPY",
                "rate": "151.23456789",
                "effective_at": "2042-08-08T10:00:00+09:00",
            }
        ],
    )

    result = runner.invoke(cli.app, ["import", "exchange", str(path)])

    assert result.exit_code == 0, result.output
    _assert_success_summary(result.output)
    rate = cli_db_session.scalar(
        select(ExchangeRate).where(
            ExchangeRate.base_currency == "T26",
            ExchangeRate.quote_currency == "JPY",
        )
    )
    assert rate is not None
    assert rate.rate == Decimal("151.23456789")
    # exchange_rates has no import_batch_id column in the approved schema
    # (design.md §3.2); unlike shipping_rates/fee_rules, it is not
    # batch-tracked at the row level. Idempotency for exchange imports is
    # covered by the import_batches uniqueness checks exercised elsewhere.


def test_import_error_exits_with_code_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        import_commands,
        "create_session_factory",
        lambda: lambda: nullcontext(object()),
    )
    missing_path = tmp_path / "missing.csv"

    result = runner.invoke(cli.app, ["import", "products", str(missing_path)])

    assert result.exit_code == 1
    assert "Import failed (FileNotFoundError)." in result.output
