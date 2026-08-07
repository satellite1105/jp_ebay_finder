"""Query and export opportunity reports and audit history."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import AuditLog, OpportunitySnapshot
from opportunity_finder.db.repositories.opportunity_repository import OpportunityRepository
from opportunity_finder.exporters.audit_jsonl import export_audit_jsonl
from opportunity_finder.exporters.opportunities_csv import export_opportunities_csv


class ReportingService:
    """Provide ranked reporting and file exports for one database session."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._opportunities = OpportunityRepository(session)

    def get_top_opportunities(
        self, limit: int, decision: str | None = None
    ) -> list[OpportunitySnapshot]:
        """Return top-ranked opportunities through the opportunity repository."""
        return self._opportunities.get_top_opportunities(limit=limit, decision=decision)

    def export_opportunities(
        self,
        path: str | Path,
        limit: int | None = None,
        decision: str | None = None,
    ) -> int:
        """Export ranked opportunity snapshots and return the number written."""
        if limit is not None:
            records = self.get_top_opportunities(limit=limit, decision=decision)
        else:
            statement = select(OpportunitySnapshot)
            if decision is not None:
                statement = statement.where(OpportunitySnapshot.decision == decision)
            statement = statement.order_by(
                OpportunitySnapshot.opportunity_score.desc(),
                OpportunitySnapshot.id.desc(),
            )
            records = list(self._session.scalars(statement).all())

        export_opportunities_csv(records, path)
        return len(records)

    def export_audit(self, path: str | Path, run_id: str | None = None) -> int:
        """Export audit records, optionally for one run, and return the count."""
        statement = select(AuditLog)
        if run_id is not None:
            statement = statement.where(AuditLog.run_id == run_id)
        statement = statement.order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        records = list(self._session.scalars(statement).all())

        export_audit_jsonl(records, path)
        return len(records)
