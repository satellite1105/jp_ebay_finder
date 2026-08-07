"""Integration tests for the daily CLI workflow and eBay fallback."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder import cli
from opportunity_finder.cli_commands import daily_command
from opportunity_finder.clients.ebay_browse import EbayAccessDeniedError
from opportunity_finder.config import Settings
from opportunity_finder.db.models import AuditLog, ScanRun
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.services import daily_service

runner = CliRunner()


class _TestSessionFactory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> Any:
        return nullcontext(self._session)


class _AccessDeniedEbayClient:
    enabled = True

    def search(self, keyword: str | None = None, gtin: str | None = None) -> dict[str, Any]:
        request = httpx.Request("GET", "https://api.ebay.test/search")
        response = httpx.Response(
            403,
            request=request,
            json={"errors": [{"message": "Access denied"}]},
        )
        raise EbayAccessDeniedError(response, "daily-test-request")

    def close(self) -> None:
        return None


def _configure_cli(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    settings: Settings,
) -> None:
    monkeypatch.setattr(daily_command, "Settings", lambda: settings)
    monkeypatch.setattr(
        daily_command,
        "create_session_factory",
        lambda selected_settings=None: _TestSessionFactory(db_session),
    )


def _latest_daily_run(session: Session) -> ScanRun:
    scan_run = session.scalar(
        select(ScanRun).where(ScanRun.command == "daily").order_by(ScanRun.id.desc()).limit(1)
    )
    assert scan_run is not None
    return scan_run


def _assert_run_linked_fallback_audit(session: Session, run_id: str) -> None:
    audit = session.scalar(
        select(AuditLog)
        .where(
            AuditLog.run_id == run_id,
            AuditLog.entity_type == "daily_step",
            AuditLog.action == "daily_step_completed",
        )
        .order_by(AuditLog.id.desc())
    )
    audits = list(
        session.scalars(
            select(AuditLog).where(
                AuditLog.run_id == run_id,
                AuditLog.entity_type == "daily_step",
            )
        )
    )
    assert audit is not None
    ebay_audit = next(
        row
        for row in audits
        if row.after_value is not None and row.after_value.get("name") == "ebay_listing_refresh"
    )
    assert ebay_audit.after_value is not None
    assert ebay_audit.after_value["fallback_to_csv"] is True


def test_daily_stale_only_completes_and_exports_with_missing_ebay_keys(
    db_session: Session,
    clean_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import_dir = tmp_path / "imports"
    settings = Settings(
        _env_file=None,
        ebay_enabled=True,
        ebay_client_id="",
        ebay_client_secret="",
        yahoo_shopping_enabled=False,
        rakuten_enabled=False,
        import_dir=import_dir,
    )
    MarketRepository(db_session).get_or_create_query(
        query_text="daily missing-key fallback",
        query_type="KEYWORD",
    )
    _configure_cli(monkeypatch, db_session, settings)
    export_dir = tmp_path / "daily-output"

    result = runner.invoke(
        cli.app,
        ["daily", "--stale-only", "--export-dir", str(export_dir)],
    )

    assert result.exit_code == 0, result.output
    assert (export_dir / "opportunities.csv").is_file()
    assert "status=completed" in result.output
    assert "falling back to csv" in caplog.text.lower()
    scan_run = _latest_daily_run(db_session)
    assert scan_run.status == "completed"
    assert scan_run.failure_count == 0
    _assert_run_linked_fallback_audit(db_session, scan_run.run_id)


def test_daily_access_denied_falls_back_without_nonzero_exit(
    db_session: Session,
    clean_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        _env_file=None,
        ebay_enabled=True,
        ebay_client_id="test-client-id",
        ebay_client_secret="test-client-secret",
        yahoo_shopping_enabled=False,
        rakuten_enabled=False,
        import_dir=tmp_path / "imports",
    )
    MarketRepository(db_session).get_or_create_query(
        query_text="daily access-denied fallback",
        query_type="KEYWORD",
    )
    _configure_cli(monkeypatch, db_session, settings)
    monkeypatch.setattr(
        daily_service,
        "EbayBrowseClient",
        lambda settings=None: _AccessDeniedEbayClient(),
    )
    export_dir = tmp_path / "daily-output"

    result = runner.invoke(
        cli.app,
        ["daily", "--stale-only", "--export-dir", str(export_dir)],
    )

    assert result.exit_code == 0, result.output
    assert (export_dir / "opportunities.csv").is_file()
    assert "falling back to csv" in caplog.text.lower()
    scan_run = _latest_daily_run(db_session)
    assert scan_run.status == "completed"
    assert scan_run.failure_count == 0
    _assert_run_linked_fallback_audit(db_session, scan_run.run_id)
