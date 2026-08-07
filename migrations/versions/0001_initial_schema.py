"""Create the initial application schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    """Create all tables defined by the canonical SQLAlchemy models."""
    op.create_table(
        "products",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("jan_code", mysql.VARCHAR(length=14), nullable=True),
        sa.Column("internal_sku", mysql.VARCHAR(length=64), nullable=True),
        sa.Column("normalized_name", mysql.VARCHAR(length=512), nullable=False),
        sa.Column("original_name", mysql.VARCHAR(length=512), nullable=False),
        sa.Column("brand", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("model_number", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("category", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("origin_country", mysql.CHAR(length=2), nullable=True),
        sa.Column(
            "unit_count",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("weight_g", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("package_length_mm", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("package_width_mm", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("package_height_mm", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column(
            "repeatable_supply", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "compliance_status",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'NEEDS_REVIEW'"),
            nullable=False,
        ),
        sa.Column("compliance_flags", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_sku", name="uq_products_internal_sku"),
        sa.UniqueConstraint("jan_code", name="uq_products_jan"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_products_brand_model", "products", ["brand", "model_number"])
    op.create_index("ix_products_status", "products", ["compliance_status"])

    op.create_table(
        "supplier_items",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("source", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("external_item_id", mysql.VARCHAR(length=255), nullable=False),
        sa.Column("shop_name", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("title", mysql.VARCHAR(length=512), nullable=False),
        sa.Column("item_url", sa.Text(), nullable=True),
        sa.Column("jan_code", mysql.VARCHAR(length=14), nullable=True),
        sa.Column("brand", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("model_number", mysql.VARCHAR(length=255), nullable=True),
        sa.Column("match_method", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("match_confidence", mysql.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("first_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_supplier_items_product"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_item_id", name="uq_supplier_external"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_supplier_product_source", "supplier_items", ["product_id", "source"])

    op.create_table(
        "supplier_price_snapshots",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("supplier_item_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("item_price_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column(
            "domestic_shipping_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "points_value_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "coupon_value_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("effective_cost_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("captured_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_item_id"],
            ["supplier_items.id"],
            name="fk_supplier_price_item",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_item_id", "captured_at", name="uq_supplier_price_capture"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_supplier_price_latest",
        "supplier_price_snapshots",
        ["supplier_item_id", "captured_at"],
    )
    op.create_index(
        "ix_supplier_effective_cost", "supplier_price_snapshots", ["effective_cost_jpy"]
    )

    op.create_table(
        "market_queries",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column(
            "marketplace",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'EBAY_US'"),
            nullable=False,
        ),
        sa.Column("query_text", mysql.VARCHAR(length=512), nullable=False),
        sa.Column("category_id", mysql.VARCHAR(length=64), nullable=True),
        sa.Column("condition_filter", mysql.VARCHAR(length=64), nullable=True),
        sa.Column("query_type", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_market_query_product"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_market_query_product", "market_queries", ["product_id"])
    op.create_index("ix_market_query_enabled", "market_queries", ["enabled"])

    op.create_table(
        "market_research_metrics",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("query_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "source",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'PRODUCT_RESEARCH'"),
            nullable=False,
        ),
        sa.Column("period_days", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("sold_count", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("active_count", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("seller_count", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("median_sold_price", mysql.DECIMAL(precision=18, scale=4), nullable=True),
        sa.Column("average_sold_price", mysql.DECIMAL(precision=18, scale=4), nullable=True),
        sa.Column("minimum_sold_price", mysql.DECIMAL(precision=18, scale=4), nullable=True),
        sa.Column("maximum_sold_price", mysql.DECIMAL(precision=18, scale=4), nullable=True),
        sa.Column("average_shipping", mysql.DECIMAL(precision=18, scale=4), nullable=True),
        sa.Column("currency", mysql.CHAR(length=3), nullable=False),
        sa.Column("sell_through_rate", mysql.DECIMAL(precision=10, scale=6), nullable=True),
        sa.Column("researched_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("valid_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("import_batch_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.ForeignKeyConstraint(["query_id"], ["market_queries.id"], name="fk_research_query"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_research_latest", "market_research_metrics", ["query_id", "researched_at"])
    op.create_index("ix_research_sellthrough", "market_research_metrics", ["sell_through_rate"])

    op.create_table(
        "ebay_listings",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("query_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column(
            "source",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'EBAY_BROWSE'"),
            nullable=False,
        ),
        sa.Column("external_item_id", mysql.VARCHAR(length=255), nullable=False),
        sa.Column("title", mysql.VARCHAR(length=512), nullable=False),
        sa.Column("item_url", sa.Text(), nullable=True),
        sa.Column("condition_raw", mysql.VARCHAR(length=64), nullable=True),
        sa.Column("condition_normalized", mysql.VARCHAR(length=32), nullable=True),
        sa.Column("seller_country", mysql.CHAR(length=2), nullable=True),
        sa.Column("match_method", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("match_confidence", mysql.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("first_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_ebay_listings_product"),
        sa.ForeignKeyConstraint(["query_id"], ["market_queries.id"], name="fk_ebay_listings_query"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_item_id", name="uq_ebay_listing_external"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_ebay_listing_query", "ebay_listings", ["query_id", "is_active"])

    op.create_table(
        "ebay_listing_snapshots",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("ebay_listing_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("price_usd", mysql.DECIMAL(precision=18, scale=6), nullable=False),
        sa.Column(
            "shipping_usd",
            mysql.DECIMAL(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "currency",
            mysql.CHAR(length=3),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("quantity_available", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("captured_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ebay_listing_id"],
            ["ebay_listings.id"],
            name="fk_ebay_snapshot_listing",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ebay_listing_id", "captured_at", name="uq_ebay_snapshot_capture"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_ebay_snapshot_latest",
        "ebay_listing_snapshots",
        ["ebay_listing_id", "captured_at"],
    )

    op.create_table(
        "exchange_rates",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("base_currency", mysql.CHAR(length=3), nullable=False),
        sa.Column("quote_currency", mysql.CHAR(length=3), nullable=False),
        sa.Column("rate", mysql.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column(
            "source",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("effective_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_currency",
            "quote_currency",
            "effective_at",
            name="uq_exchange_rate_point",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_exchange_rate_latest",
        "exchange_rates",
        ["base_currency", "quote_currency", "effective_at"],
    )

    op.create_table(
        "shipping_rates",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("profile_code", mysql.VARCHAR(length=64), nullable=False),
        sa.Column("destination_country", mysql.CHAR(length=2), nullable=False),
        sa.Column("min_weight_g", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("max_weight_g", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("service_name", mysql.VARCHAR(length=128), nullable=False),
        sa.Column("shipping_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("tracking", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "included_insurance_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("effective_from", mysql.DATE(), nullable=False),
        sa.Column("effective_to", mysql.DATE(), nullable=True),
        sa.Column("import_batch_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_shipping_lookup",
        "shipping_rates",
        ["profile_code", "destination_country", "min_weight_g", "max_weight_g"],
    )
    op.create_index("ix_shipping_effective", "shipping_rates", ["effective_from", "effective_to"])

    op.create_table(
        "fee_rules",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("profile_code", mysql.VARCHAR(length=64), nullable=False),
        sa.Column("marketplace", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("category_code", mysql.VARCHAR(length=64), nullable=True),
        sa.Column("variable_fee_rate", mysql.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column(
            "international_fee_rate",
            mysql.DECIMAL(precision=10, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("fixed_fee_currency", mysql.CHAR(length=3), nullable=False),
        sa.Column(
            "fixed_fee_amount",
            mysql.DECIMAL(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "ad_rate",
            mysql.DECIMAL(precision=10, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "return_reserve_rate",
            mysql.DECIMAL(precision=10, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("effective_from", mysql.DATE(), nullable=False),
        sa.Column("effective_to", mysql.DATE(), nullable=True),
        sa.Column("import_batch_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_code", "effective_from", name="uq_fee_rule_profile"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_fee_rule_lookup",
        "fee_rules",
        ["marketplace", "category_code", "effective_from"],
    )

    op.create_table(
        "opportunity_snapshots",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("query_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("scenario", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("source_cost_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column(
            "buyer_total_market_currency",
            mysql.DECIMAL(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column("market_currency", mysql.CHAR(length=3), nullable=False),
        sa.Column("exchange_rate", mysql.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column("revenue_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("marketplace_fees_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column(
            "advertising_reserve_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column("return_reserve_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("duty_processing_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column(
            "international_shipping_jpy",
            mysql.DECIMAL(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column("packaging_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("other_costs_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("total_cost_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("net_profit_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("net_margin", mysql.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("break_even_buyer_total", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("capital_required_jpy", mysql.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column("capital_efficiency", mysql.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("opportunity_score", mysql.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("data_confidence", mysql.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("decision", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("calculated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("calculator_version", mysql.VARCHAR(length=64), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_opportunity_product"),
        sa.ForeignKeyConstraint(["query_id"], ["market_queries.id"], name="fk_opportunity_query"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_opportunity_rank",
        "opportunity_snapshots",
        ["scenario", "decision", "opportunity_score"],
    )
    op.create_index("ix_opportunity_profit", "opportunity_snapshots", ["net_profit_jpy"])
    op.create_index(
        "ix_opportunity_product_time",
        "opportunity_snapshots",
        ["product_id", "calculated_at"],
    )

    op.create_table(
        "scan_runs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("run_id", mysql.CHAR(length=36), nullable=False),
        sa.Column("command", mysql.VARCHAR(length=64), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "status",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "rows_read",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "rows_written",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failure_count",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_scan_run_id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_scan_run_command_time", "scan_runs", ["command", "started_at"])

    op.create_table(
        "import_batches",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("import_type", mysql.VARCHAR(length=32), nullable=False),
        sa.Column("file_name", mysql.VARCHAR(length=255), nullable=False),
        sa.Column("file_sha256", mysql.CHAR(length=64), nullable=False),
        sa.Column(
            "rows_total",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "rows_imported",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "rows_quarantined",
            mysql.INTEGER(unsigned=True),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "status",
            mysql.VARCHAR(length=32),
            server_default=sa.text("'completed'"),
            nullable=False,
        ),
        sa.Column("quarantine_detail", sa.JSON(), nullable=True),
        sa.Column("imported_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_type", "file_sha256", name="uq_import_batch_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_import_batch_time", "import_batches", ["import_type", "imported_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("run_id", mysql.CHAR(length=36), nullable=True),
        sa.Column("entity_type", mysql.VARCHAR(length=64), nullable=False),
        sa.Column("entity_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("action", mysql.VARCHAR(length=64), nullable=False),
        sa.Column(
            "actor",
            mysql.VARCHAR(length=64),
            server_default=sa.text("'system'"),
            nullable=False,
        ),
        sa.Column("before_value", sa.JSON(), nullable=True),
        sa.Column("after_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_run", "audit_logs", ["run_id"])


def downgrade() -> None:
    """Drop all application tables in reverse dependency order."""
    op.drop_table("audit_logs")
    op.drop_table("import_batches")
    op.drop_table("scan_runs")
    op.drop_table("opportunity_snapshots")
    op.drop_table("fee_rules")
    op.drop_table("shipping_rates")
    op.drop_table("exchange_rates")
    op.drop_table("ebay_listing_snapshots")
    op.drop_table("ebay_listings")
    op.drop_table("market_research_metrics")
    op.drop_table("market_queries")
    op.drop_table("supplier_price_snapshots")
    op.drop_table("supplier_items")
    op.drop_table("products")
