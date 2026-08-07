"""Persistence operations for calculated opportunity snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import OpportunitySnapshot


class OpportunityRepository:
    """Store and retrieve immutable opportunity calculation results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_snapshot(
        self,
        snapshot: OpportunitySnapshot | Mapping[str, Any] | None = None,
        **values: Any,
    ) -> OpportunitySnapshot:
        """Persist one snapshot and assign its database-generated identifier."""
        if snapshot is not None and values:
            raise ValueError("Pass either snapshot or keyword values, not both")

        if isinstance(snapshot, OpportunitySnapshot):
            entity = snapshot
        elif snapshot is not None:
            entity = OpportunitySnapshot(**dict(snapshot))
        else:
            entity = OpportunitySnapshot(**values)

        self.session.add(entity)
        self.session.flush()
        return entity

    def _top_opportunities_statement(
        self, *, limit: int, decision: str | None = None
    ) -> Select[tuple[OpportunitySnapshot]]:
        """Build the shared ranking statement, including its MySQL index hint."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        statement = select(OpportunitySnapshot).with_hint(
            OpportunitySnapshot,
            "FORCE INDEX (ix_opportunity_rank)",
            dialect_name="mysql",
        )
        if decision is not None:
            statement = statement.where(OpportunitySnapshot.decision == decision)

        return statement.order_by(
            OpportunitySnapshot.opportunity_score.desc(),
            OpportunitySnapshot.id.desc(),
        ).limit(limit)

    def get_top_opportunities(
        self, limit: int, decision: str | None = None
    ) -> list[OpportunitySnapshot]:
        """Return the highest-scoring snapshots, optionally for one decision."""
        statement = self._top_opportunities_statement(limit=limit, decision=decision)
        return list(self.session.scalars(statement).all())

    def get_latest_by_product(self, product_id: int) -> OpportunitySnapshot | None:
        """Return the most recently calculated snapshot for a product."""
        statement = (
            select(OpportunitySnapshot)
            .where(OpportunitySnapshot.product_id == product_id)
            .order_by(
                OpportunitySnapshot.calculated_at.desc(),
                OpportunitySnapshot.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(statement).first()
