from decimal import Decimal

from opportunity_finder.domain.matching import match_products


def _match(**overrides: object) -> tuple[str, Decimal]:
    arguments = {
        "candidate_jan": None,
        "candidate_brand": None,
        "candidate_model_number": None,
        "candidate_title": "Sony WH-1000XM5 Wireless Headphones Black",
        "candidate_condition": "new",
        "candidate_unit_count": 1,
        "target_jan": None,
        "target_brand": None,
        "target_model_number": None,
        "target_title": "Unrelated product",
        "target_condition": "new",
        "target_unit_count": 1,
    }
    arguments.update(overrides)
    return match_products(**arguments)  # type: ignore[arg-type]


def test_jan_exact_match() -> None:
    method, confidence = _match(candidate_jan="4901234567894", target_jan="4901234567894")

    assert method == "jan"
    assert confidence == Decimal(100)


def test_brand_and_model_number_match_after_normalization() -> None:
    method, confidence = _match(
        candidate_brand="ＳＯＮＹ",
        candidate_model_number="ＷＨ－１０００ＸＭ５",
        target_brand="sony",
        target_model_number="wh-1000xm5",
    )

    assert method == "brand_model"
    assert confidence == Decimal(90)


def test_different_unit_count_forces_non_match() -> None:
    method, confidence = _match(
        candidate_jan="4901234567894",
        target_jan="4901234567894",
        candidate_brand="Sony",
        target_brand="Sony",
        candidate_model_number="WH-1000XM5",
        target_model_number="WH-1000XM5",
        target_title="Sony WH-1000XM5 Wireless Headphones Black",
        target_unit_count=2,
    )

    assert method == "none"
    assert confidence == Decimal(0)


def test_different_condition_forces_non_match() -> None:
    method, confidence = _match(
        candidate_jan="4901234567894",
        target_jan="4901234567894",
        candidate_brand="Sony",
        target_brand="Sony",
        candidate_model_number="WH-1000XM5",
        target_model_number="WH-1000XM5",
        target_title="Sony WH-1000XM5 Wireless Headphones Black",
        target_condition="used",
    )

    assert method == "none"
    assert confidence == Decimal(0)


def test_high_title_similarity_uses_fuzzy_title_match() -> None:
    method, confidence = _match(
        target_title="Black Wireless Headphones Sony WH-1000XM5",
    )

    assert method == "fuzzy_title"
    assert confidence >= Decimal(90)
    assert confidence <= Decimal(100)


def test_low_title_similarity_with_wrong_brand_is_non_match() -> None:
    method, confidence = _match(
        target_title="Canon EOS R5 Mirrorless Camera Body",
    )

    assert method == "none"
    assert confidence == Decimal(0)
