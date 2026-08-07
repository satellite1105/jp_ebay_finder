"""Seed sample fee and shipping rules.

Revision ID: 0002_seed_default_rules
Revises: 0001_initial_schema
Create Date: 2026-08-08
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0002_seed_default_rules"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EFFECTIVE_FROM = date(2026, 1, 1)
_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_FEE_PROFILE_CODE = "EBAY_US_DEFAULT_SAMPLE"
_SHIPPING_PROFILE_CODE = "JP_TO_US_TRACKED_SAMPLE"

fee_rules = sa.table(
    "fee_rules",
    sa.column("profile_code", sa.String()),
    sa.column("marketplace", sa.String()),
    sa.column("category_code", sa.String()),
    sa.column("variable_fee_rate", sa.Numeric()),
    sa.column("international_fee_rate", sa.Numeric()),
    sa.column("fixed_fee_currency", sa.String()),
    sa.column("fixed_fee_amount", sa.Numeric()),
    sa.column("ad_rate", sa.Numeric()),
    sa.column("return_reserve_rate", sa.Numeric()),
    sa.column("effective_from", sa.Date()),
    sa.column("effective_to", sa.Date()),
    sa.column("import_batch_id", sa.BigInteger()),
    sa.column("created_at", sa.DateTime()),
)

shipping_rates = sa.table(
    "shipping_rates",
    sa.column("profile_code", sa.String()),
    sa.column("destination_country", sa.String()),
    sa.column("min_weight_g", sa.Integer()),
    sa.column("max_weight_g", sa.Integer()),
    sa.column("service_name", sa.String()),
    sa.column("shipping_jpy", sa.Numeric()),
    sa.column("tracking", sa.Boolean()),
    sa.column("included_insurance_jpy", sa.Numeric()),
    sa.column("effective_from", sa.Date()),
    sa.column("effective_to", sa.Date()),
    sa.column("import_batch_id", sa.BigInteger()),
    sa.column("created_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert deterministic sample defaults for local and offline operation."""
    op.bulk_insert(
        fee_rules,
        [
            {
                "profile_code": _FEE_PROFILE_CODE,
                "marketplace": "EBAY_US",
                "category_code": None,
                "variable_fee_rate": Decimal("0.132500"),
                "international_fee_rate": Decimal("0.015500"),
                "fixed_fee_currency": "USD",
                "fixed_fee_amount": Decimal("0.400000"),
                "ad_rate": Decimal("0.020000"),
                "return_reserve_rate": Decimal("0.030000"),
                "effective_from": _EFFECTIVE_FROM,
                "effective_to": None,
                "import_batch_id": None,
                "created_at": _CREATED_AT,
            }
        ],
    )
    op.bulk_insert(
        shipping_rates,
        [
            {
                "profile_code": _SHIPPING_PROFILE_CODE,
                "destination_country": "US",
                "min_weight_g": 1,
                "max_weight_g": 500,
                "service_name": "Tracked Air Sample",
                "shipping_jpy": Decimal("2800.0000"),
                "tracking": True,
                "included_insurance_jpy": Decimal("0.0000"),
                "effective_from": _EFFECTIVE_FROM,
                "effective_to": None,
                "import_batch_id": None,
                "created_at": _CREATED_AT,
            },
            {
                "profile_code": _SHIPPING_PROFILE_CODE,
                "destination_country": "US",
                "min_weight_g": 501,
                "max_weight_g": 1000,
                "service_name": "Tracked Air Sample",
                "shipping_jpy": Decimal("4200.0000"),
                "tracking": True,
                "included_insurance_jpy": Decimal("0.0000"),
                "effective_from": _EFFECTIVE_FROM,
                "effective_to": None,
                "import_batch_id": None,
                "created_at": _CREATED_AT,
            },
        ],
    )


def downgrade() -> None:
    """Remove only the rows owned by this seed revision."""
    op.execute(
        sa.delete(shipping_rates).where(
            sa.and_(
                shipping_rates.c.profile_code == _SHIPPING_PROFILE_CODE,
                shipping_rates.c.effective_from == _EFFECTIVE_FROM,
            )
        )
    )
    op.execute(
        sa.delete(fee_rules).where(
            sa.and_(
                fee_rules.c.profile_code == _FEE_PROFILE_CODE,
                fee_rules.c.effective_from == _EFFECTIVE_FROM,
            )
        )
    )
