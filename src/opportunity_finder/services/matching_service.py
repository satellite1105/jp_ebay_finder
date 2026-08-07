"""Application service for selecting the best product match."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from opportunity_finder.domain.matching import match_products


class MatchableProduct(Protocol):
    """Product attributes required by the domain matching rules."""

    jan_code: str | None
    brand: str | None
    model_number: str | None
    title: str
    condition: str
    unit_count: int


class MatchingService:
    """Apply domain matching rules to an in-memory collection of targets."""

    def find_best_match(
        self,
        candidate: MatchableProduct,
        targets: list[MatchableProduct],
    ) -> tuple[object | None, str, Decimal]:
        """Return the target with the highest non-zero match confidence."""
        best_target: object | None = None
        best_method = "none"
        best_confidence = Decimal(0)

        for target in targets:
            method, confidence = match_products(
                candidate_jan=candidate.jan_code,
                candidate_brand=candidate.brand,
                candidate_model_number=candidate.model_number,
                candidate_title=candidate.title,
                candidate_condition=candidate.condition,
                candidate_unit_count=candidate.unit_count,
                target_jan=target.jan_code,
                target_brand=target.brand,
                target_model_number=target.model_number,
                target_title=target.title,
                target_condition=target.condition,
                target_unit_count=target.unit_count,
            )
            if confidence > best_confidence:
                best_target = target
                best_method = method
                best_confidence = confidence

        return best_target, best_method, best_confidence
