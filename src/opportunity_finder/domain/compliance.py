"""Small predicates for compliance decisions."""

from opportunity_finder.domain.models import ComplianceDecision


def is_blocked(compliance: ComplianceDecision) -> bool:
    """Return whether an item must never be considered for purchase."""
    return compliance.compliance_status == "blocked"


def needs_review(compliance: ComplianceDecision) -> bool:
    """Return whether a human compliance review is required."""
    return compliance.compliance_status in {"review", "needs_review"}
