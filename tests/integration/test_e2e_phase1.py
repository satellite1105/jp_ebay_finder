"""Phase 1 offline E2E test using the checked-in sample CSV files."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from opportunity_finder import cli
from opportunity_finder.cli_commands import (
    calculate_commands,
    import_commands,
    report_commands,
)
from opportunity_finder.db.models import OpportunitySnapshot, Product
from opportunity_finder.exporters.opportunities_csv import OPPORTUNITY_COLUMNS
from opportunity_finder.services.opportunity_service import OpportunityService

runner = CliRunner()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
SAMPLE_PRODUCT_KEYS = {
    "sample-high-profit-001",
    "sample-low-profit-002",
    "sample-blocked-003",
}
CALCULATION_AS_OF = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


class _CalculationSessionFactory:
    """Expose the rollback-isolated E2E session to the calculation CLI."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def begin(self) -> Iterator[Session]:
        yield self._session


def _invoke(arguments: list[str]):
    result = runner.invoke(cli.app, arguments)
    assert result.exit_code == 0, f"{' '.join(arguments)} failed:\n{result.output}"
    return result


def _configure_cli_sessions(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    session_context = lambda: nullcontext(session)
    monkeypatch.setattr(import_commands, "create_session_factory", lambda: session_context)
    monkeypatch.setattr(report_commands, "create_session_factory", lambda: session_context)
    monkeypatch.setattr(
        calculate_commands,
        "create_session_factory",
        lambda: _CalculationSessionFactory(session),
    )
    monkeypatch.setattr(
        calculate_commands,
        "OpportunityService",
        lambda current_session: OpportunityService(
            current_session,
            as_of=CALCULATION_AS_OF,
        ),
    )


def _set_sample_compliance_statuses(session: Session) -> dict[str, Product]:
    products = {
        product.internal_sku: product
        for product in session.scalars(
            select(Product).where(Product.internal_sku.in_(SAMPLE_PRODUCT_KEYS))
        )
    }
    assert set(products) == SAMPLE_PRODUCT_KEYS

    products["sample-high-profit-001"].compliance_status = "approved"
    products["sample-low-profit-002"].compliance_status = "approved"
    blocked = products["sample-blocked-003"]
    blocked.compliance_status = "blocked"
    blocked.compliance_flags = ["hazardous_lithium_battery"]
    session.flush()
    return products


def _product_ids_in_buy_test_rows(output: str) -> set[int]:
    product_ids: set[int] = set()
    for line in output.splitlines():
        if "BUY_TEST_" not in line:
            continue
        cells = [cell.strip() for cell in line.split("│")]
        if len(cells) >= 8 and cells[2].isdigit():
            product_ids.add(int(cells[2]))
    return product_ids


def test_phase1_sample_csv_e2e(
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Run Mode C import, calculation, report, and export through Typer."""
    _invoke(["db", "upgrade"])

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        _configure_cli_sessions(monkeypatch, session)
        import_commands_to_run = (
            ("products", "products.csv"),
            ("product-research", "product_research.csv"),
            ("shipping", "shipping_rates.csv"),
            ("fees", "fee_profiles.csv"),
            ("exchange", "exchange_rates.csv"),
        )
        for command_name, file_name in import_commands_to_run:
            result = _invoke(["import", command_name, str(SAMPLES_DIR / file_name)])
            assert "quarantined=0" in result.output

        products = _set_sample_compliance_statuses(session)
        calculation = _invoke(["calculate", "opportunities"])
        assert "Calculated opportunities:" in calculation.output

        sample_ids = {product.id for product in products.values()}
        sample_snapshots = list(
            session.scalars(
                select(OpportunitySnapshot)
                .where(OpportunitySnapshot.product_id.in_(sample_ids))
                .order_by(OpportunitySnapshot.product_id, OpportunitySnapshot.scenario)
            )
        )
        assert len(sample_snapshots) == 9
        assert {snapshot.scenario for snapshot in sample_snapshots} == {
            "optimistic",
            "base",
            "conservative",
        }

        high_profit_id = products["sample-high-profit-001"].id
        high_profit_base = next(
            snapshot
            for snapshot in sample_snapshots
            if snapshot.product_id == high_profit_id and snapshot.scenario == "base"
        )
        assert high_profit_base.net_profit_jpy >= Decimal(3000)
        assert high_profit_base.net_margin >= Decimal("0.25")
        assert high_profit_base.decision == "BUY_TEST_1"

        blocked_id = products["sample-blocked-003"].id
        blocked_snapshots = [
            snapshot for snapshot in sample_snapshots if snapshot.product_id == blocked_id
        ]
        assert {snapshot.decision for snapshot in blocked_snapshots} == {"BLOCKED"}

        _invoke(["report", "top", "--limit", "10"])
        buy_test_report = _invoke(
            [
                "report",
                "top",
                "--limit",
                "10",
                "--decision",
                "BUY_TEST_1",
            ]
        )
        report_product_ids = _product_ids_in_buy_test_rows(buy_test_report.output)
        assert high_profit_id in report_product_ids
        assert blocked_id not in report_product_ids
        assert "BLOCKED" not in buy_test_report.output

        output_path = tmp_path / "output.csv"
        export_result = _invoke(["export", "opportunities", str(output_path)])
        assert output_path.is_file()

        with output_path.open(encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            exported_rows = list(reader)
            assert reader.fieldnames == list(OPPORTUNITY_COLUMNS)

        snapshot_count = session.scalar(select(func.count()).select_from(OpportunitySnapshot))
        assert snapshot_count is not None
        assert len(exported_rows) == snapshot_count
        assert f"Exported {snapshot_count} opportunity records" in export_result.output

        exported_sample_rows = [
            row for row in exported_rows if int(row["product_id"]) in sample_ids
        ]
        assert len(exported_sample_rows) == 9
        assert {row["scenario"] for row in exported_sample_rows} == {
            "optimistic",
            "base",
            "conservative",
        }
        assert {
            row["decision"] for row in exported_sample_rows if int(row["product_id"]) == blocked_id
        } == {"BLOCKED"}
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
