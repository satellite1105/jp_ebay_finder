from dataclasses import dataclass
from decimal import Decimal

from opportunity_finder.services.matching_service import MatchingService


@dataclass
class Product:
    jan_code: str | None
    brand: str | None
    model_number: str | None
    title: str
    condition: str = "new"
    unit_count: int = 1


def test_find_best_match_selects_highest_confidence_target() -> None:
    candidate = Product(
        jan_code="4901234567894",
        brand="Sony",
        model_number="WH-1000XM5",
        title="Sony WH-1000XM5 Wireless Headphones Black",
    )
    brand_model_match = Product(
        jan_code=None,
        brand="ＳＯＮＹ",
        model_number="ＷＨ－１０００ＸＭ５",
        title="Different title",
    )
    jan_match = Product(
        jan_code="4901234567894",
        brand="Unrelated",
        model_number="OTHER",
        title="Unrelated title",
    )
    no_match = Product(
        jan_code=None,
        brand="Canon",
        model_number="EOS-R5",
        title="Canon EOS R5 Mirrorless Camera Body",
    )

    target, method, confidence = MatchingService().find_best_match(
        candidate,
        [brand_model_match, jan_match, no_match],
    )

    assert target is jan_match
    assert method == "jan"
    assert confidence == Decimal(100)


def test_find_best_match_returns_none_when_no_target_matches() -> None:
    candidate = Product(
        jan_code="4901234567894",
        brand="Sony",
        model_number="WH-1000XM5",
        title="Sony WH-1000XM5 Wireless Headphones Black",
    )
    targets = [
        Product(
            jan_code="4901234567894",
            brand="Sony",
            model_number="WH-1000XM5",
            title="Sony WH-1000XM5 Wireless Headphones Black",
            condition="used",
        ),
        Product(
            jan_code=None,
            brand="Canon",
            model_number="EOS-R5",
            title="Canon EOS R5 Mirrorless Camera Body",
        ),
    ]

    target, method, confidence = MatchingService().find_best_match(candidate, targets)

    assert target is None
    assert method == "none"
    assert confidence == Decimal(0)
