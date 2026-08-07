"""Integration tests for execution and audit persistence."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import AuditLog, ImportBatch, ScanRun
from opportunity_finder.db.repositories.run_repository import RunRepository


def test_scan_run_start_and_finish_are_recorded(
    db_session: Session,
    clean_db: None,
) -> None:
    repository = RunRepository(db_session)
    run_id = str(uuid4())

    started = repository.start_scan_run(run_id, "daily")

    assert started.id is not None
    assert started.run_id == run_id
    assert started.command == "daily"
    assert started.status == "running"
    assert started.started_at is not None
    assert started.finished_at is None
    assert started.rows_read == 0
    assert started.rows_written == 0
    assert started.failure_count == 0
    assert started.summary is None

    summary = {"steps": ["import", "scan"], "result": "completed"}
    finished = repository.finish_scan_run(
        run_id,
        status="completed",
        rows_read=25,
        rows_written=8,
        failure_count=1,
        summary=summary,
    )

    assert finished.id == started.id
    assert finished.finished_at is not None
    assert finished.finished_at >= finished.started_at
    assert finished.status == "completed"
    assert finished.rows_read == 25
    assert finished.rows_written == 8
    assert finished.failure_count == 1
    assert finished.summary == summary

    db_session.expire_all()
    persisted = db_session.scalar(select(ScanRun).where(ScanRun.run_id == run_id))
    assert persisted is finished
    assert persisted.summary == summary


def test_import_batch_is_idempotent_for_same_type_and_hash(
    db_session: Session,
    clean_db: None,
) -> None:
    repository = RunRepository(db_session)
    file_sha256 = "a" * 64

    assert repository.is_import_batch_processed("products", file_sha256) is False
    assert repository.is_import_batch_processed("exchange_rates", file_sha256) is False

    first = repository.record_import_batch(
        import_type="products",
        file_name="products.csv",
        file_sha256=file_sha256,
        rows_total=10,
        rows_imported=9,
        rows_quarantined=1,
        status="completed_with_quarantine",
        quarantine_detail={"rows": [4], "reason": "invalid JAN"},
    )

    assert first.id is not None
    assert repository.is_import_batch_processed("products", file_sha256) is True
    assert repository.is_import_batch_processed("exchange_rates", file_sha256) is False

    duplicate = repository.record_import_batch(
        import_type="products",
        file_name="renamed-products.csv",
        file_sha256=file_sha256,
        rows_total=99,
        rows_imported=99,
        rows_quarantined=0,
        status="completed",
    )

    assert duplicate.id == first.id
    assert duplicate.file_name == "products.csv"
    assert duplicate.rows_total == 10
    assert duplicate.quarantine_detail == {"rows": [4], "reason": "invalid JAN"}
    batch_count = db_session.scalar(
        select(func.count(ImportBatch.id)).where(
            ImportBatch.import_type == "products",
            ImportBatch.file_sha256 == file_sha256,
        )
    )
    assert batch_count == 1


def test_audit_log_records_json_values(
    db_session: Session,
    clean_db: None,
) -> None:
    repository = RunRepository(db_session)
    run_id = str(uuid4())
    before_value = {"status": "NEEDS_REVIEW", "flags": ["unknown_brand"]}
    after_value = {"status": "APPROVED", "flags": []}

    audit_log = repository.add_audit_log(
        entity_type="product",
        entity_id=42,
        action="compliance_status_changed",
        actor="reviewer@example.com",
        before_value=before_value,
        after_value=after_value,
        reason="Manual catalog review completed",
        run_id=run_id,
    )

    assert audit_log.id is not None
    assert audit_log.created_at is not None
    audit_log_id = audit_log.id
    db_session.expire_all()
    persisted = db_session.get(AuditLog, audit_log_id)
    assert persisted is not None
    assert persisted is audit_log
    assert persisted.run_id == run_id
    assert persisted.entity_type == "product"
    assert persisted.entity_id == 42
    assert persisted.action == "compliance_status_changed"
    assert persisted.actor == "reviewer@example.com"
    assert persisted.before_value == before_value
    assert persisted.after_value == after_value
    assert persisted.reason == "Manual catalog review completed"
