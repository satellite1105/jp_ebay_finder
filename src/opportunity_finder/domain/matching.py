"""Product matching rules for comparable marketplace listings."""

import unicodedata
from decimal import Decimal

from rapidfuzz import fuzz


def _normalize_identifier(value: str) -> str:
    """Normalize identifier text for case and full-width differences."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def match_products(
    candidate_jan: str | None,
    candidate_brand: str | None,
    candidate_model_number: str | None,
    candidate_title: str,
    candidate_condition: str,
    candidate_unit_count: int,
    target_jan: str | None,
    target_brand: str | None,
    target_model_number: str | None,
    target_title: str,
    target_condition: str,
    target_unit_count: int,
) -> tuple[str, Decimal]:
    """Match two products, rejecting incompatible condition or set counts."""
    if candidate_condition != target_condition or candidate_unit_count != target_unit_count:
        return "none", Decimal(0)

    if candidate_jan and target_jan and candidate_jan == target_jan:
        return "jan", Decimal(100)

    if (
        candidate_brand
        and target_brand
        and candidate_model_number
        and target_model_number
        and _normalize_identifier(candidate_brand) == _normalize_identifier(target_brand)
        and _normalize_identifier(candidate_model_number)
        == _normalize_identifier(target_model_number)
    ):
        return "brand_model", Decimal(90)

    score = fuzz.token_sort_ratio(candidate_title, target_title)
    if score >= 90:
        return "fuzzy_title", Decimal(str(score))

    return "none", Decimal(0)
