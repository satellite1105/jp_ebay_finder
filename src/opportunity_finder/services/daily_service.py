"""Orchestration service for the daily opportunity-finder workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from opportunity_finder.clients.ebay_browse import EbayBrowseClient
from opportunity_finder.clients.rakuten_ichiba import RakutenIchibaClient
from opportunity_finder.clients.rakuten_product import RakutenProductClient
from opportunity_finder.clients.yahoo_shopping import YahooShoppingClient
from opportunity_finder.config import Settings
from opportunity_finder.db.models import MarketQuery, Product, SupplierItem, SupplierPriceSnapshot
from opportunity_finder.db.repositories.run_repository import RunRepository
from opportunity_finder.services.ebay_service import EbayRefreshSummary, EbayService
from opportunity_finder.services.import_service import ImportService, ImportSummary
from opportunity_finder.services.market_service import MarketRefreshSummary, MarketService
from opportunity_finder.services.opportunity_service import OpportunityService
from opportunity_finder.services.reporting_service import ReportingService

_SOURCE_DATA_MAX_AGE_DAYS = 7
_DEFAULT_FAILURE_THRESHOLD = 0
_EXPORT_FILE_NAME = "opportunities.csv"


@dataclass(frozen=True, slots=True)
class DailyStepResult:
    """Serializable outcome for one ordered daily-workflow step."""

    number: int
    name: str
    status: Literal["completed", "skipped", "failed"]
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DailyRunSummary:
    """Final counters and step outcomes for one daily run."""

    run_id: str
    status: Literal["completed", "failed"]
    rows_read: int
    rows_written: int
    failure_count: int
    failure_threshold: int
    export_path: str
    steps: tuple[DailyStepResult, ...]

    @property
    def exceeded_failure_threshold(self) -> bool:
        """Return whether the CLI must use a non-zero exit status."""
        return self.failure_count > self.failure_threshold


class _EmptyYahooClient:
    def search(self, jan_code: str | None = None, query: str | None = None) -> dict[str, Any]:
        return {"hits": []}


class _EmptyRakutenIchibaClient:
    def search_by_keyword(self, keyword: str, *, page: int = 1) -> dict[str, Any]:
        return {"Items": []}


class _EmptyRakutenProductClient:
    def search_by_jan(self, jan_code: str, *, page: int = 1) -> dict[str, Any]:
        return {"Products": []}


class DailyService:
    """Run and audit the ten daily workflow steps in their specified order."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
    ) -> None:
        if failure_threshold < 0:
            raise ValueError("failure_threshold must not be negative")
        self._session = session
        self._settings = settings or Settings()
        self._failure_threshold = failure_threshold
        self._runs = RunRepository(session)

    def run(self, stale_only: bool, export_dir: str) -> DailyRunSummary:
        """Execute the daily workflow, returning a summary used by the CLI."""
        run_id = str(uuid4())
        steps: list[DailyStepResult] = []
        rows_read = 0
        rows_written = 0
        failure_count = 0
        output_path = Path(export_dir) / _EXPORT_FILE_NAME

        # Step 1 must succeed before a scan row can be persisted in that database.
        self._session.execute(text("SELECT 1")).scalar_one()
        self._runs.start_scan_run(run_id, "daily")
        self._record_step(
            run_id,
            steps,
            1,
            "database_connection",
            "completed",
            {"connected": True},
        )
        self._session.commit()

        failure_count += self._run_guarded_step(
            run_id,
            steps,
            2,
            "settings_validation",
            self._validate_settings,
        )[1]

        self._record_step(
            run_id,
            steps,
            3,
            "exchange_rate_refresh",
            "skipped",
            {"reason": "no exchange-rate refresh service configured"},
        )
        self._session.commit()

        domestic_result, failed = self._run_guarded_step(
            run_id,
            steps,
            4,
            "domestic_price_refresh",
            lambda: self._refresh_domestic(stale_only),
        )
        failure_count += failed
        if isinstance(domestic_result, MarketRefreshSummary):
            rows_read += domestic_result.products_checked
            rows_written += domestic_result.offers_matched

        ebay_result, failed = self._run_guarded_step(
            run_id,
            steps,
            5,
            "ebay_listing_refresh",
            self._refresh_ebay,
        )
        failure_count += failed
        if isinstance(ebay_result, EbayRefreshSummary):
            rows_read += ebay_result.queries_checked
            rows_written += ebay_result.listings_saved

        import_result, failed = self._run_guarded_step(
            run_id,
            steps,
            6,
            "product_research_import",
            self._import_product_research,
        )
        failure_count += failed
        if isinstance(import_result, list):
            rows_read += sum(summary.rows_total for summary in import_result)
            rows_written += sum(summary.rows_imported for summary in import_result)

        opportunity_result, failed = self._run_guarded_step(
            run_id,
            steps,
            7,
            "opportunity_calculation",
            self._calculate_opportunities,
        )
        failure_count += failed
        if isinstance(opportunity_result, int):
            rows_read += opportunity_result
            rows_written += opportunity_result * 3

        export_result, failed = self._run_guarded_step(
            run_id,
            steps,
            8,
            "opportunity_export",
            lambda: self._export_opportunities(output_path),
        )
        failure_count += failed
        if isinstance(export_result, int):
            rows_written += export_result

        draft_status: Literal["completed", "failed"] = (
            "failed" if failure_count > self._failure_threshold else "completed"
        )
        self._record_step(
            run_id,
            steps,
            9,
            "run_summary",
            "completed",
            {
                "status": draft_status,
                "rows_read": rows_read,
                "rows_written": rows_written,
                "failure_count": failure_count,
                "export_path": str(output_path),
            },
        )
        self._record_step(
            run_id,
            steps,
            10,
            "failure_threshold_check",
            "completed",
            {
                "failure_count": failure_count,
                "failure_threshold": self._failure_threshold,
                "threshold_exceeded": failure_count > self._failure_threshold,
            },
        )

        summary = DailyRunSummary(
            run_id=run_id,
            status=draft_status,
            rows_read=rows_read,
            rows_written=rows_written,
            failure_count=failure_count,
            failure_threshold=self._failure_threshold,
            export_path=str(output_path),
            steps=tuple(steps),
        )
        self._runs.finish_scan_run(
            run_id=run_id,
            status=summary.status,
            rows_read=summary.rows_read,
            rows_written=summary.rows_written,
            failure_count=summary.failure_count,
            summary=self._summary_document(summary),
        )
        self._session.commit()
        return summary

    def _run_guarded_step(
        self,
        run_id: str,
        steps: list[DailyStepResult],
        number: int,
        name: str,
        operation: Any,
    ) -> tuple[Any, int]:
        try:
            result = operation()
        except Exception as exc:  # noqa: BLE001 - daily steps are failure-isolated
            self._session.rollback()
            self._record_step(
                run_id,
                steps,
                number,
                name,
                "failed",
                {"error_type": type(exc).__name__},
            )
            self._session.commit()
            return None, 1

        status: Literal["completed", "skipped", "failed"] = "completed"
        details = self._step_details(result)
        if details.pop("skipped", False):
            status = "skipped"
        self._record_step(run_id, steps, number, name, status, details)
        self._session.commit()
        return result, 0

    def _record_step(
        self,
        run_id: str,
        steps: list[DailyStepResult],
        number: int,
        name: str,
        status: Literal["completed", "skipped", "failed"],
        details: dict[str, Any],
    ) -> None:
        result = DailyStepResult(number=number, name=name, status=status, details=details)
        steps.append(result)
        self._runs.add_audit_log(
            run_id=run_id,
            entity_type="daily_step",
            entity_id=None,
            action=f"daily_step_{status}",
            actor="DailyService",
            after_value={"step": number, "name": name, **details},
        )

    def _validate_settings(self) -> dict[str, Any]:
        type(self._settings).model_validate(self._settings.model_dump())
        return {"validated": True}

    def _refresh_domestic(self, stale_only: bool) -> MarketRefreshSummary:
        clients = self._build_domestic_clients()
        try:
            product_ids = self._domestic_product_ids() if stale_only else None
            return MarketService(
                self._session,
                yahoo_client=clients[0],  # type: ignore[arg-type]
                rakuten_ichiba_client=clients[1],  # type: ignore[arg-type]
                rakuten_product_client=clients[2],  # type: ignore[arg-type]
            ).refresh_domestic_prices(product_ids)
        finally:
            self._close_clients(clients)

    def _build_domestic_clients(self) -> tuple[object, object, object]:
        yahoo: object = (
            YahooShoppingClient(settings=self._settings)
            if self._settings.yahoo_shopping_enabled
            else _EmptyYahooClient()
        )
        if self._settings.rakuten_enabled and self._settings.rakuten_application_id.strip():
            affiliate_id = self._settings.rakuten_affiliate_id or None
            return (
                yahoo,
                RakutenIchibaClient(
                    self._settings.rakuten_application_id,
                    affiliate_id=affiliate_id,
                ),
                RakutenProductClient(
                    self._settings.rakuten_application_id,
                    affiliate_id=affiliate_id,
                ),
            )
        return yahoo, _EmptyRakutenIchibaClient(), _EmptyRakutenProductClient()

    def _domestic_product_ids(self) -> list[int]:
        fresh_after = (datetime.now(UTC) - timedelta(days=_SOURCE_DATA_MAX_AGE_DAYS)).replace(
            tzinfo=None
        )
        has_matching_identifier = or_(
            func.length(func.trim(Product.jan_code)) > 0,
            func.length(func.trim(Product.brand)) > 0,
            func.length(func.trim(Product.model_number)) > 0,
        )
        has_fresh_domestic_price = (
            select(SupplierPriceSnapshot.id)
            .join(SupplierItem, SupplierItem.id == SupplierPriceSnapshot.supplier_item_id)
            .where(
                SupplierItem.product_id == Product.id,
                SupplierPriceSnapshot.captured_at >= fresh_after,
            )
            .exists()
        )
        statement = (
            select(Product.id)
            .where(has_matching_identifier, ~has_fresh_domestic_price)
            .order_by(Product.id)
        )
        return list(self._session.scalars(statement).all())

    def _refresh_ebay(self) -> EbayRefreshSummary:
        client: EbayBrowseClient | None = None
        try:
            if (
                self._settings.ebay_enabled
                and self._settings.ebay_client_id.strip()
                and self._settings.ebay_client_secret.strip()
            ):
                client = EbayBrowseClient(settings=self._settings)
            query_ids = list(
                self._session.scalars(
                    select(MarketQuery.id)
                    .where(MarketQuery.enabled.is_(True))
                    .order_by(MarketQuery.id)
                ).all()
            )
            return EbayService(
                self._session,
                client,
                settings=self._settings,
            ).refresh_listings(query_ids)
        finally:
            if client is not None:
                client.close()

    def _import_product_research(self) -> list[ImportSummary]:
        import_dir = self._settings.import_dir
        if not import_dir.is_dir():
            return []
        paths = sorted(path for path in import_dir.glob("product_research*.csv") if path.is_file())
        service = ImportService(self._session)
        return [service.import_product_research(str(path)) for path in paths]

    def _calculate_opportunities(self) -> int:
        return len(OpportunityService(self._session).calculate_opportunities())

    def _export_opportunities(self, output_path: Path) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return ReportingService(self._session).export_opportunities(output_path, limit=30)

    @staticmethod
    def _close_clients(clients: tuple[object, object, object]) -> None:
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _step_details(result: Any) -> dict[str, Any]:
        if isinstance(result, MarketRefreshSummary):
            return asdict(result)
        if isinstance(result, EbayRefreshSummary):
            return asdict(result)
        if isinstance(result, list) and all(isinstance(item, ImportSummary) for item in result):
            return {
                "files_checked": len(result),
                "rows_total": sum(item.rows_total for item in result),
                "rows_imported": sum(item.rows_imported for item in result),
                "rows_quarantined": sum(item.rows_quarantined for item in result),
                "skipped": not result,
            }
        if isinstance(result, int):
            return {"count": result}
        if isinstance(result, dict):
            return dict(result)
        return {}

    @staticmethod
    def _summary_document(summary: DailyRunSummary) -> dict[str, Any]:
        return {
            "status": summary.status,
            "rows_read": summary.rows_read,
            "rows_written": summary.rows_written,
            "failure_count": summary.failure_count,
            "failure_threshold": summary.failure_threshold,
            "export_path": summary.export_path,
            "steps": [asdict(step) for step in summary.steps],
        }


__all__ = ["DailyRunSummary", "DailyService", "DailyStepResult"]
