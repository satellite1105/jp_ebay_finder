"""SQLAlchemy mappings for the canonical MySQL schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from opportunity_finder.db.base import Base

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("jan_code", name="uq_products_jan"),
        UniqueConstraint("internal_sku", name="uq_products_internal_sku"),
        Index("ix_products_brand_model", "brand", "model_number"),
        Index("ix_products_status", "compliance_status"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    jan_code: Mapped[str | None] = mapped_column(mysql.VARCHAR(14), nullable=True)
    internal_sku: Mapped[str | None] = mapped_column(mysql.VARCHAR(64), nullable=True)
    normalized_name: Mapped[str] = mapped_column(mysql.VARCHAR(512), nullable=False)
    original_name: Mapped[str] = mapped_column(mysql.VARCHAR(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    model_number: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    category: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    origin_country: Mapped[str | None] = mapped_column(mysql.CHAR(2), nullable=True)
    unit_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("1")
    )
    weight_g: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True), nullable=True)
    package_length_mm: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=True
    )
    package_width_mm: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=True
    )
    package_height_mm: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=True
    )
    repeatable_supply: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    compliance_status: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'NEEDS_REVIEW'")
    )
    compliance_flags: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class SupplierItem(Base):
    __tablename__ = "supplier_items"
    __table_args__ = (
        UniqueConstraint("source", "external_item_id", name="uq_supplier_external"),
        Index("ix_supplier_product_source", "product_id", "source"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("products.id", name="fk_supplier_items_product"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    external_item_id: Mapped[str] = mapped_column(mysql.VARCHAR(255), nullable=False)
    shop_name: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    title: Mapped[str] = mapped_column(mysql.VARCHAR(512), nullable=False)
    item_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jan_code: Mapped[str | None] = mapped_column(mysql.VARCHAR(14), nullable=True)
    brand: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    model_number: Mapped[str | None] = mapped_column(mysql.VARCHAR(255), nullable=True)
    match_method: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    match_confidence: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    first_seen_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)


class SupplierPriceSnapshot(Base):
    __tablename__ = "supplier_price_snapshots"
    __table_args__ = (
        UniqueConstraint("supplier_item_id", "captured_at", name="uq_supplier_price_capture"),
        Index("ix_supplier_price_latest", "supplier_item_id", "captured_at"),
        Index("ix_supplier_effective_cost", "effective_cost_jpy"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    supplier_item_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("supplier_items.id", name="fk_supplier_price_item"),
        nullable=False,
    )
    item_price_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    domestic_shipping_jpy: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False, server_default=text("0")
    )
    points_value_jpy: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False, server_default=text("0")
    )
    coupon_value_jpy: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False, server_default=text("0")
    )
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_cost_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)


class MarketQuery(Base):
    __tablename__ = "market_queries"
    __table_args__ = (
        Index("ix_market_query_product", "product_id"),
        Index("ix_market_query_enabled", "enabled"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("products.id", name="fk_market_query_product"),
        nullable=True,
    )
    marketplace: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'EBAY_US'")
    )
    query_text: Mapped[str] = mapped_column(mysql.VARCHAR(512), nullable=False)
    category_id: Mapped[str | None] = mapped_column(mysql.VARCHAR(64), nullable=True)
    condition_filter: Mapped[str | None] = mapped_column(mysql.VARCHAR(64), nullable=True)
    query_type: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class MarketResearchMetric(Base):
    __tablename__ = "market_research_metrics"
    __table_args__ = (
        Index("ix_research_latest", "query_id", "researched_at"),
        Index("ix_research_sellthrough", "sell_through_rate"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    query_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("market_queries.id", name="fk_research_query"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'PRODUCT_RESEARCH'")
    )
    period_days: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    sold_count: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True), nullable=True)
    active_count: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True), nullable=True)
    seller_count: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True), nullable=True)
    median_sold_price: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(18, 4), nullable=True)
    average_sold_price: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(18, 4), nullable=True)
    minimum_sold_price: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(18, 4), nullable=True)
    maximum_sold_price: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(18, 4), nullable=True)
    average_shipping: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    sell_through_rate: Mapped[Decimal | None] = mapped_column(mysql.DECIMAL(10, 6), nullable=True)
    researched_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)


class OpportunitySnapshot(Base):
    __tablename__ = "opportunity_snapshots"
    __table_args__ = (
        Index("ix_opportunity_rank", "scenario", "decision", "opportunity_score"),
        Index("ix_opportunity_profit", "net_profit_jpy"),
        Index("ix_opportunity_product_time", "product_id", "calculated_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("products.id", name="fk_opportunity_product"),
        nullable=False,
    )
    query_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("market_queries.id", name="fk_opportunity_query"),
        nullable=False,
    )
    scenario: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    source_cost_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    buyer_total_market_currency: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False
    )
    market_currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 8), nullable=False)
    revenue_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    marketplace_fees_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    advertising_reserve_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    return_reserve_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    duty_processing_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    international_shipping_jpy: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False
    )
    packaging_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    other_costs_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    total_cost_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    net_profit_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    net_margin: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 6), nullable=False)
    break_even_buyer_total: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    capital_required_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    capital_efficiency: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 6), nullable=False)
    opportunity_score: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 4), nullable=False)
    data_confidence: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 4), nullable=False)
    decision: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    calculator_version: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)


class EbayListing(Base):
    __tablename__ = "ebay_listings"
    __table_args__ = (
        UniqueConstraint("source", "external_item_id", name="uq_ebay_listing_external"),
        Index("ix_ebay_listing_query", "query_id", "is_active"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    query_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("market_queries.id", name="fk_ebay_listings_query"),
        nullable=False,
    )
    product_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("products.id", name="fk_ebay_listings_product"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'EBAY_BROWSE'")
    )
    external_item_id: Mapped[str] = mapped_column(mysql.VARCHAR(255), nullable=False)
    title: Mapped[str] = mapped_column(mysql.VARCHAR(512), nullable=False)
    item_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_raw: Mapped[str | None] = mapped_column(mysql.VARCHAR(64), nullable=True)
    condition_normalized: Mapped[str | None] = mapped_column(mysql.VARCHAR(32), nullable=True)
    seller_country: Mapped[str | None] = mapped_column(mysql.CHAR(2), nullable=True)
    match_method: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    match_confidence: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    first_seen_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class EbayListingSnapshot(Base):
    __tablename__ = "ebay_listing_snapshots"
    __table_args__ = (
        UniqueConstraint("ebay_listing_id", "captured_at", name="uq_ebay_snapshot_capture"),
        Index("ix_ebay_snapshot_latest", "ebay_listing_id", "captured_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    ebay_listing_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("ebay_listings.id", name="fk_ebay_snapshot_listing"),
        nullable=False,
    )
    price_usd: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 6), nullable=False)
    shipping_usd: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 6), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        mysql.CHAR(3), nullable=False, server_default=text("'USD'")
    )
    quantity_available: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency", "effective_at", name="uq_exchange_rate_point"
        ),
        Index("ix_exchange_rate_latest", "base_currency", "quote_currency", "effective_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    base_currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'manual'")
    )
    effective_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)


class ShippingRate(Base):
    __tablename__ = "shipping_rates"
    __table_args__ = (
        Index(
            "ix_shipping_lookup",
            "profile_code",
            "destination_country",
            "min_weight_g",
            "max_weight_g",
        ),
        Index("ix_shipping_effective", "effective_from", "effective_to"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    profile_code: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)
    destination_country: Mapped[str] = mapped_column(mysql.CHAR(2), nullable=False)
    min_weight_g: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    max_weight_g: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    service_name: Mapped[str] = mapped_column(mysql.VARCHAR(128), nullable=False)
    shipping_jpy: Mapped[Decimal] = mapped_column(mysql.DECIMAL(18, 4), nullable=False)
    tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    included_insurance_jpy: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 4), nullable=False, server_default=text("0")
    )
    effective_from: Mapped[date] = mapped_column(mysql.DATE, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(mysql.DATE, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class FeeRule(Base):
    __tablename__ = "fee_rules"
    __table_args__ = (
        UniqueConstraint("profile_code", "effective_from", name="uq_fee_rule_profile"),
        Index("ix_fee_rule_lookup", "marketplace", "category_code", "effective_from"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    profile_code: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)
    marketplace: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    category_code: Mapped[str | None] = mapped_column(mysql.VARCHAR(64), nullable=True)
    variable_fee_rate: Mapped[Decimal] = mapped_column(mysql.DECIMAL(10, 6), nullable=False)
    international_fee_rate: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(10, 6), nullable=False, server_default=text("0")
    )
    fixed_fee_currency: Mapped[str] = mapped_column(mysql.CHAR(3), nullable=False)
    fixed_fee_amount: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(18, 6), nullable=False, server_default=text("0")
    )
    ad_rate: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(10, 6), nullable=False, server_default=text("0")
    )
    return_reserve_rate: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(10, 6), nullable=False, server_default=text("0")
    )
    effective_from: Mapped[date] = mapped_column(mysql.DATE, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(mysql.DATE, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class ScanRun(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_scan_run_id"),
        Index("ix_scan_run_command_time", "command", "started_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(mysql.CHAR(36), nullable=False)
    command: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'running'")
    )
    rows_read: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    rows_written: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    failure_count: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    summary: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("import_type", "file_sha256", name="uq_import_batch_hash"),
        Index("ix_import_batch_time", "import_type", "imported_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    import_type: Mapped[str] = mapped_column(mysql.VARCHAR(32), nullable=False)
    file_name: Mapped[str] = mapped_column(mysql.VARCHAR(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(mysql.CHAR(64), nullable=False)
    rows_total: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    rows_imported: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    rows_quarantined: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(32), nullable=False, server_default=text("'completed'")
    )
    quarantine_detail: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON, nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_run", "run_id"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    run_id: Mapped[str | None] = mapped_column(mysql.CHAR(36), nullable=True)
    entity_type: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)
    action: Mapped[str] = mapped_column(mysql.VARCHAR(64), nullable=False)
    actor: Mapped[str] = mapped_column(
        mysql.VARCHAR(64), nullable=False, server_default=text("'system'")
    )
    before_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
