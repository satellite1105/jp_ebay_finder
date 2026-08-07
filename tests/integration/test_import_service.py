"""Integration tests for CSV import orchestration against MySQL."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import (
    ExchangeRate,
    FeeRule,
    ImportBatch,
    MarketQuery,
    MarketResearchMetric,
    Product,
    ShippingRate,
    SupplierItem,
    SupplierPriceSnapshot,
)
from opportunity_finder.services.import_service import ImportService

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


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _product_row(**overrides: str) -> dict[str, str]:
    row = {
        "external_key": "t21-product-001",
        "jan": "4900000000024",
        "title": "T21 Test Product",
        "brand": "T21 Brand",
        "model_number": "T21-MODEL",
        "condition": "new",
        "source_cost_jpy": "1980",
        "source_shipping_jpy": "320",
        "weight_g": "300",
        "packed_weight_g": "380",
        "origin_country": "JP",
        "supplier_name": "T21 Shop",
        "supplier_url": "https://example.invalid/t21",
        "checked_at": "2042-08-06T09:00:00+09:00",
    }
    row.update(overrides)
    return row


def _research_row(**overrides: str) -> dict[str, str]:
    row = {
        "external_key": "t21-research-product",
        "search_query": "T21 Brand MODEL",
        "marketplace": "EBAY_US",
        "condition": "new",
        "lookback_days": "90",
        "sold_count": "12",
        "active_count": "30",
        "median_sold_price_usd": "69.99",
        "average_sold_price_usd": "68.50",
        "median_buyer_shipping_usd": "4.99",
        "sell_through_rate": "0.2857",
        "checked_at": "2042-08-06T09:30:00+09:00",
        "notes": "T21 manual research",
    }
    row.update(overrides)
    return row


def test_products_import_is_idempotent_for_batch_and_price_snapshot(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path / "products.csv", PRODUCT_COLUMNS, [_product_row()])
    service = ImportService(db_session)

    first = service.import_products(str(path))
    second = service.import_products(str(path))

    assert first.rows_total == 1
    assert first.rows_imported == 1
    assert first.rows_quarantined == 0
    assert first.already_processed is False
    assert second.rows_total == 1
    assert second.rows_imported == 0
    assert second.already_processed is True

    batch_count = db_session.scalar(
        select(func.count(ImportBatch.id)).where(
            ImportBatch.import_type == "products",
            ImportBatch.file_name == "products.csv",
        )
    )
    snapshot_count = db_session.scalar(
        select(func.count(SupplierPriceSnapshot.id))
        .join(SupplierItem)
        .where(
            SupplierItem.source == "MANUAL_CSV",
            SupplierItem.external_item_id == "t21-product-001",
        )
    )
    assert batch_count == 1
    assert snapshot_count == 1

    product = db_session.scalar(select(Product).where(Product.internal_sku == "t21-product-001"))
    supplier_item = db_session.scalar(
        select(SupplierItem).where(
            SupplierItem.source == "MANUAL_CSV",
            SupplierItem.external_item_id == "t21-product-001",
        )
    )
    assert product is not None
    assert product.original_name == "T21 Test Product"
    assert supplier_item is not None
    assert supplier_item.product_id == product.id
    assert supplier_item.shop_name == "T21 Shop"
    snapshot = db_session.scalar(
        select(SupplierPriceSnapshot).where(
            SupplierPriceSnapshot.supplier_item_id == supplier_item.id
        )
    )
    assert snapshot is not None
    assert snapshot.item_price_jpy == Decimal("1980.0000")
    assert snapshot.domestic_shipping_jpy == Decimal("320.0000")
    assert snapshot.effective_cost_jpy == Decimal("2300.0000")


def test_product_research_import_saves_query_and_metric(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    service = ImportService(db_session)
    products_path = _write_csv(
        tmp_path / "products.csv",
        PRODUCT_COLUMNS,
        [_product_row(external_key="t21-research-product", jan="4900000000031")],
    )
    service.import_products(str(products_path))
    research_path = _write_csv(
        tmp_path / "product_research.csv", RESEARCH_COLUMNS, [_research_row()]
    )

    summary = service.import_product_research(str(research_path))

    assert summary.rows_total == 1
    assert summary.rows_imported == 1
    assert summary.rows_quarantined == 0
    query = db_session.scalar(
        select(MarketQuery).where(MarketQuery.query_text == "T21 Brand MODEL")
    )
    assert query is not None
    assert query.product_id is not None
    assert query.condition_filter == "NEW"
    metric = db_session.scalar(
        select(MarketResearchMetric).where(MarketResearchMetric.query_id == query.id)
    )
    assert metric is not None
    assert metric.sold_count == 12
    assert metric.currency == "USD"
    assert metric.import_batch_id is not None


def test_shipping_import_saves_rate(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "shipping_rates.csv",
        SHIPPING_COLUMNS,
        [
            {
                "profile_code": "T21_US_DDP",
                "destination_country": "US",
                "min_weight_g": "0",
                "max_weight_g": "500",
                "service_name": "T21 Tracked",
                "shipping_jpy": "1800",
                "tracking": "true",
                "included_insurance_jpy": "100",
                "effective_from": "2042-08-01",
                "effective_to": "",
            }
        ],
    )

    summary = ImportService(db_session).import_shipping(str(path))

    assert summary.rows_imported == 1
    rate = db_session.scalar(select(ShippingRate).where(ShippingRate.profile_code == "T21_US_DDP"))
    assert rate is not None
    assert rate.shipping_jpy == Decimal("1800.0000")
    assert rate.included_insurance_jpy == Decimal("100.0000")
    assert rate.import_batch_id is not None


def test_fees_import_saves_rule(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "fee_profiles.csv",
        FEE_COLUMNS,
        [
            {
                "profile_code": "T21_EBAY_US",
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

    summary = ImportService(db_session).import_fees(str(path))

    assert summary.rows_imported == 1
    rule = db_session.scalar(select(FeeRule).where(FeeRule.profile_code == "T21_EBAY_US"))
    assert rule is not None
    assert rule.variable_fee_rate == Decimal("0.136000")
    assert rule.import_batch_id is not None


def test_exchange_import_saves_rate(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        ["base_currency", "quote_currency", "rate", "effective_at"],
        [
            {
                "base_currency": "T21",
                "quote_currency": "JPY",
                "rate": "150.12345678",
                "effective_at": "2042-08-07T12:30:45+09:00",
            }
        ],
    )

    summary = ImportService(db_session).import_exchange(str(path))

    assert summary.rows_imported == 1
    rate = db_session.scalar(
        select(ExchangeRate).where(
            ExchangeRate.base_currency == "T21",
            ExchangeRate.quote_currency == "JPY",
        )
    )
    assert rate is not None
    assert rate.rate == Decimal("150.12345678")
    assert rate.source == "MANUAL_CSV"
    batch = db_session.scalar(
        select(ImportBatch).where(
            ImportBatch.import_type == "exchange",
            ImportBatch.file_name == "exchange_rates.csv",
        )
    )
    assert batch is not None
    assert batch.rows_imported == 1


def test_invalid_product_row_is_quarantined_while_valid_row_is_saved(
    db_session: Session,
    clean_db: None,
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path / "mixed-products.csv",
        PRODUCT_COLUMNS,
        [
            _product_row(external_key="t21-mixed-valid", jan="4900000000048"),
            _product_row(external_key="t21-mixed-invalid", jan="invalid-jan"),
        ],
    )

    summary = ImportService(db_session).import_products(str(path))

    assert summary.rows_total == 2
    assert summary.rows_imported == 1
    assert summary.rows_quarantined == 1
    assert summary.already_processed is False
    assert (
        db_session.scalar(
            select(func.count(Product.id)).where(
                Product.internal_sku.in_(["t21-mixed-valid", "t21-mixed-invalid"])
            )
        )
        == 1
    )
    batch = db_session.scalar(
        select(ImportBatch).where(
            ImportBatch.import_type == "products",
            ImportBatch.file_name == "mixed-products.csv",
        )
    )
    assert batch is not None
    assert batch.status == "completed_with_quarantine"
    assert batch.rows_quarantined == 1
    assert batch.quarantine_detail is not None
