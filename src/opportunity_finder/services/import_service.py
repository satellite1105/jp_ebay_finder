"""Application service for validated, idempotent CSV imports."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from opportunity_finder.db.models import (
    ExchangeRate,
    FeeRule,
    MarketResearchMetric,
    ShippingRate,
)
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.run_repository import RunRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository
from opportunity_finder.domain.models import (
    FeeProfile,
    MarketResearchInput,
    ProductInput,
    ShippingQuote,
)
from opportunity_finder.importers.csv_common import QuarantinedRow
from opportunity_finder.importers.exchange_csv import (
    ExchangeRateInput,
    import_exchange_csv,
)
from opportunity_finder.importers.fees_csv import import_fees_csv
from opportunity_finder.importers.product_research_csv import (
    import_product_research_csv,
)
from opportunity_finder.importers.products_csv import import_products_csv
from opportunity_finder.importers.shipping_csv import import_shipping_csv


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """Counters for one requested CSV import."""

    rows_total: int
    rows_imported: int
    rows_quarantined: int
    already_processed: bool = False


class ImportService:
    """Parse CSV files and persist their valid rows in one transaction per file."""

    _MANUAL_SOURCE = "MANUAL_CSV"

    def __init__(self, session: Session) -> None:
        self._session = session
        self._products = ProductRepository(session)
        self._suppliers = SupplierRepository(session)
        self._markets = MarketRepository(session)
        self._runs = RunRepository(session)

    def import_products(self, path: str) -> ImportSummary:
        """Import products and their manual supplier price observations."""
        result = import_products_csv(path)
        duplicate = self._duplicate_summary(
            "products",
            result.file_sha256,
            result.rows_total,
            len(result.quarantined_rows),
        )
        if duplicate is not None:
            return duplicate

        try:
            for row in result.valid_rows:
                self._save_product(row)
            return self._record_completed_import(
                import_type="products",
                path=path,
                file_sha256=result.file_sha256,
                rows_total=result.rows_total,
                rows_imported=len(result.valid_rows),
                quarantined_rows=result.quarantined_rows,
            )
        except Exception:
            self._session.rollback()
            raise

    def import_product_research(self, path: str) -> ImportSummary:
        """Import Product Research query definitions and point-in-time metrics."""
        result = import_product_research_csv(path)
        rows_total = len(result.records) + len(result.errors)
        duplicate = self._duplicate_summary(
            "product_research",
            result.file_sha256,
            rows_total,
            len(result.errors),
        )
        if duplicate is not None:
            return duplicate

        metrics = []
        try:
            for row in result.records:
                metrics.append(self._save_product_research(row))
            return self._record_completed_import(
                import_type="product_research",
                path=path,
                file_sha256=result.file_sha256,
                rows_total=rows_total,
                rows_imported=len(result.records),
                quarantined_rows=result.errors,
                batch_linked_rows=metrics,
            )
        except Exception:
            self._session.rollback()
            raise

    def import_shipping(self, path: str) -> ImportSummary:
        """Import shipping-rate reference data."""
        result = import_shipping_csv(path)
        duplicate = self._duplicate_summary(
            "shipping",
            result.file_sha256,
            result.rows_total,
            len(result.quarantined_rows),
        )
        if duplicate is not None:
            return duplicate

        rates = []
        try:
            for row in result.valid_rows:
                rates.append(self._save_shipping_rate(row))
            self._session.flush()
            return self._record_completed_import(
                import_type="shipping",
                path=path,
                file_sha256=result.file_sha256,
                rows_total=result.rows_total,
                rows_imported=len(result.valid_rows),
                quarantined_rows=result.quarantined_rows,
                batch_linked_rows=rates,
            )
        except Exception:
            self._session.rollback()
            raise

    def import_fees(self, path: str) -> ImportSummary:
        """Import marketplace fee and reserve rules."""
        result = import_fees_csv(path)
        duplicate = self._duplicate_summary(
            "fees",
            result.file_sha256,
            result.rows_total,
            len(result.quarantined_rows),
        )
        if duplicate is not None:
            return duplicate

        rules = []
        try:
            for row in result.valid_rows:
                rules.append(self._save_fee_rule(row))
            self._session.flush()
            return self._record_completed_import(
                import_type="fees",
                path=path,
                file_sha256=result.file_sha256,
                rows_total=result.rows_total,
                rows_imported=len(result.valid_rows),
                quarantined_rows=result.quarantined_rows,
                batch_linked_rows=rules,
            )
        except Exception:
            self._session.rollback()
            raise

    def import_exchange(self, path: str) -> ImportSummary:
        """Import exchange-rate observations."""
        result = import_exchange_csv(path)
        duplicate = self._duplicate_summary(
            "exchange",
            result.file_sha256,
            result.rows_total,
            len(result.quarantined_rows),
        )
        if duplicate is not None:
            return duplicate

        try:
            for row in result.valid_rows:
                self._save_exchange_rate(row)
            self._session.flush()
            return self._record_completed_import(
                import_type="exchange",
                path=path,
                file_sha256=result.file_sha256,
                rows_total=result.rows_total,
                rows_imported=len(result.valid_rows),
                quarantined_rows=result.quarantined_rows,
            )
        except Exception:
            self._session.rollback()
            raise

    def _duplicate_summary(
        self,
        import_type: str,
        file_sha256: str,
        rows_total: int,
        rows_quarantined: int,
    ) -> ImportSummary | None:
        if not self._runs.is_import_batch_processed(import_type, file_sha256):
            return None
        self._session.commit()
        return ImportSummary(
            rows_total=rows_total,
            rows_imported=0,
            rows_quarantined=rows_quarantined,
            already_processed=True,
        )

    def _record_completed_import(
        self,
        *,
        import_type: str,
        path: str,
        file_sha256: str,
        rows_total: int,
        rows_imported: int,
        quarantined_rows: list[QuarantinedRow],
        batch_linked_rows: Iterable[MarketResearchMetric | ShippingRate | FeeRule] = (),
    ) -> ImportSummary:
        rows_quarantined = len(quarantined_rows)
        batch = self._runs.record_import_batch(
            import_type=import_type,
            file_name=Path(path).name,
            file_sha256=file_sha256,
            rows_total=rows_total,
            rows_imported=rows_imported,
            rows_quarantined=rows_quarantined,
            status=("completed_with_quarantine" if rows_quarantined else "completed"),
            quarantine_detail=self._quarantine_detail(quarantined_rows),
        )
        for row in batch_linked_rows:
            row.import_batch_id = batch.id
        self._session.flush()
        self._session.commit()
        return ImportSummary(
            rows_total=rows_total,
            rows_imported=rows_imported,
            rows_quarantined=rows_quarantined,
        )

    def _save_product(self, row: ProductInput) -> None:
        product = self._products.get_or_create(
            row.jan_code,
            internal_sku=row.external_key,
            normalized_name=row.title,
            original_name=row.title,
            brand=row.brand,
            model_number=row.model_number,
            origin_country=row.origin_country,
            weight_g=row.weight_g,
            created_at=row.checked_at,
            updated_at=row.checked_at,
        )
        supplier_item = self._suppliers.upsert_supplier_item(
            product_id=product.id,
            source=self._MANUAL_SOURCE,
            external_item_id=row.external_key,
            shop_name=row.supplier_name,
            title=row.title,
            item_url=row.supplier_url,
            jan_code=row.jan_code,
            brand=row.brand,
            model_number=row.model_number,
            match_method="JAN" if row.jan_code else "EXTERNAL_KEY",
            match_confidence=Decimal(1),
            is_active=True,
            first_seen_at=row.checked_at,
            last_seen_at=row.checked_at,
            raw_payload=row.model_dump(mode="json"),
        )
        effective_cost = row.source_cost_jpy + row.source_shipping_jpy
        self._suppliers.add_price_snapshot(
            supplier_item_id=supplier_item.id,
            item_price_jpy=row.source_cost_jpy,
            domestic_shipping_jpy=row.source_shipping_jpy,
            available=True,
            effective_cost_jpy=effective_cost,
            captured_at=row.checked_at,
            raw_payload=row.model_dump(mode="json"),
        )

    def _save_product_research(self, row: MarketResearchInput) -> MarketResearchMetric:
        product = self._products.get_by_internal_sku(row.external_key)
        query = self._markets.get_or_create_query(
            product_id=product.id if product is not None else None,
            marketplace=row.marketplace,
            query_text=row.search_query,
            condition_filter=row.condition.upper() if row.condition else None,
            query_type="PRODUCT_RESEARCH",
        )
        return self._markets.add_research_metric(
            query_id=query.id,
            period_days=row.lookback_days,
            sold_count=row.sold_count,
            active_count=row.active_count,
            median_sold_price=row.median_sold_price_usd,
            average_sold_price=row.average_sold_price_usd,
            average_shipping=row.median_buyer_shipping_usd,
            currency="USD",
            sell_through_rate=row.sell_through_rate,
            researched_at=_as_utc_naive(row.checked_at),
            notes=row.notes,
        )

    def _save_shipping_rate(self, row: ShippingQuote) -> ShippingRate:
        rate = ShippingRate(
            profile_code=row.profile_code,
            destination_country=row.destination_country,
            min_weight_g=row.min_weight_g,
            max_weight_g=row.max_weight_g,
            service_name=row.service_name,
            shipping_jpy=row.shipping_jpy,
            tracking=row.tracking,
            included_insurance_jpy=row.included_insurance_jpy,
            effective_from=row.effective_from.date(),
            effective_to=row.effective_to.date() if row.effective_to else None,
            created_at=_utc_now(),
        )
        self._session.add(rate)
        return rate

    def _save_fee_rule(self, row: FeeProfile) -> FeeRule:
        rule = FeeRule(
            profile_code=row.profile_code,
            marketplace=row.marketplace,
            category_code=row.category_code,
            variable_fee_rate=row.variable_fee_rate,
            international_fee_rate=row.international_fee_rate,
            fixed_fee_currency=row.fixed_fee_currency,
            fixed_fee_amount=row.fixed_fee_amount,
            ad_rate=row.ad_rate,
            return_reserve_rate=row.return_reserve_rate,
            effective_from=row.effective_from.date(),
            effective_to=row.effective_to.date() if row.effective_to else None,
            created_at=_utc_now(),
        )
        self._session.add(rule)
        return rule

    def _save_exchange_rate(self, row: ExchangeRateInput) -> ExchangeRate:
        rate = ExchangeRate(
            base_currency=row.base_currency.upper(),
            quote_currency=row.quote_currency.upper(),
            rate=row.rate,
            source=self._MANUAL_SOURCE,
            effective_at=_as_utc_naive(row.effective_at),
            raw_payload=row.model_dump(mode="json"),
        )
        self._session.add(rate)
        return rate

    @staticmethod
    def _quarantine_detail(rows: list[QuarantinedRow]) -> list[dict[str, object]] | None:
        if not rows:
            return None
        return [{"row": row.row, "error": row.error} for row in rows]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
