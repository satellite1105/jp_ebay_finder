"""Persistence operations for scan runs, import batches, and audit logs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_finder.db.models import AuditLog, ImportBatch, ScanRun


def _utc_now() -> datetime:
    """Return a UTC timestamp suitable for the schema's timezone-naive DATETIME columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class RunRepository:
    """Store execution metadata and audit history in the current transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_scan_run(self, run_id: str, command: str) -> ScanRun:
        """Create and flush a running scan record."""
        scan_run = ScanRun(
            run_id=run_id,
            command=command,
            started_at=_utc_now(),
            status="running",
            rows_read=0,
            rows_written=0,
            failure_count=0,
        )
        self._session.add(scan_run)
        self._session.flush()
        return scan_run

    def finish_scan_run(
        self,
        run_id: str,
        status: str,
        rows_read: int,
        rows_written: int,
        failure_count: int,
        summary: dict[str, Any] | list[Any] | None = None,
    ) -> ScanRun:
        """Mark an existing scan record as finished and flush its final counters."""
        scan_run = self._session.scalar(select(ScanRun).where(ScanRun.run_id == run_id))
        if scan_run is None:
            raise ValueError(f"Scan run not found: {run_id}")

        scan_run.finished_at = _utc_now()
        scan_run.status = status
        scan_run.rows_read = rows_read
        scan_run.rows_written = rows_written
        scan_run.failure_count = failure_count
        scan_run.summary = summary
        self._session.flush()
        return scan_run

    def is_import_batch_processed(self, import_type: str, file_sha256: str) -> bool:
        """Return whether an import batch already exists for the composite hash key."""
        statement = select(ImportBatch.id).where(
            ImportBatch.import_type == import_type,
            ImportBatch.file_sha256 == file_sha256,
        )
        return self._session.scalar(statement) is not None

    def record_import_batch(
        self,
        import_type: str,
        file_name: str,
        file_sha256: str,
        rows_total: int,
        rows_imported: int,
        rows_quarantined: int,
        status: str,
        quarantine_detail: dict[str, Any] | list[Any] | None = None,
    ) -> ImportBatch:
        """Create an import batch, or return the row already stored for the same hash."""
        statement = select(ImportBatch).where(
            ImportBatch.import_type == import_type,
            ImportBatch.file_sha256 == file_sha256,
        )
        existing = self._session.scalar(statement)
        if existing is not None:
            return existing

        import_batch = ImportBatch(
            import_type=import_type,
            file_name=file_name,
            file_sha256=file_sha256,
            rows_total=rows_total,
            rows_imported=rows_imported,
            rows_quarantined=rows_quarantined,
            status=status,
            quarantine_detail=quarantine_detail,
            imported_at=_utc_now(),
        )

        try:
            with self._session.begin_nested():
                self._session.add(import_batch)
                self._session.flush()
        except IntegrityError:
            # A concurrent importer can win after the initial lookup. The unique
            # constraint rolls back only this SAVEPOINT, leaving the caller's
            # surrounding transaction usable so the winning row can be returned.
            existing = self._session.scalar(statement)
            if existing is None:
                raise
            return existing

        return import_batch

    def add_audit_log(
        self,
        entity_type: str,
        entity_id: int | None,
        action: str,
        actor: str,
        before_value: dict[str, Any] | list[Any] | None = None,
        after_value: dict[str, Any] | list[Any] | None = None,
        reason: str | None = None,
        run_id: str | None = None,
    ) -> AuditLog:
        """Create and flush an audit-log entry."""
        audit_log = AuditLog(
            run_id=run_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            before_value=before_value,
            after_value=after_value,
            reason=reason,
            created_at=_utc_now(),
        )
        self._session.add(audit_log)
        self._session.flush()
        return audit_log
