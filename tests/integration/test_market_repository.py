"""Integration tests for the market data repository against MySQL."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_finder.db.models import EbayListing
from opportunity_finder.db.repositories.market_repository import MarketRepository


def _utc_datetime(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC).replace(tzinfo=None)


def _new_query(repository: MarketRepository, *, suffix: str) -> int:
    query = repository.get_or_create_query(
        query_text=f"integration-market-{suffix}",
        query_type="KEYWORD",
        marketplace="EBAY_US",
        category_id="9355",
        condition_filter="NEW",
        created_at=_utc_datetime(2026, 1, 1),
    )
    return query.id


def _new_listing(
    repository: MarketRepository,
    *,
    query_id: int,
    external_item_id: str,
    seen_at: datetime,
    is_active: bool = True,
) -> EbayListing:
    return repository.upsert_ebay_listing(
        query_id=query_id,
        source="EBAY_BROWSE",
        external_item_id=external_item_id,
        title="Japanese test item",
        item_url="https://example.invalid/item",
        condition_raw="New",
        condition_normalized="NEW",
        seller_country="JP",
        match_method="TITLE",
        match_confidence=Decimal("0.900000"),
        is_active=is_active,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
    )


def test_market_query_crud_and_get_or_create(db_session: Session, clean_db: None) -> None:
    repository = MarketRepository(db_session)
    suffix = uuid4().hex
    created_at = _utc_datetime(2026, 1, 1)

    query = repository.get_or_create_query(
        query_text=f"camera-{suffix}",
        query_type="KEYWORD",
        marketplace="EBAY_US",
        category_id="31388",
        condition_filter="USED",
        created_at=created_at,
    )
    same_query = repository.get_or_create_query(
        query_text=f"camera-{suffix}",
        query_type="KEYWORD",
        marketplace="EBAY_US",
        category_id="31388",
        condition_filter="USED",
        enabled=False,
    )

    assert query.id is not None
    assert same_query.id == query.id
    assert same_query.enabled is True
    assert repository.get_query(query.id) is query

    updated = repository.update_query(query.id, query_text=f"lens-{suffix}", enabled=False)
    assert updated is not None
    assert updated.query_text == f"lens-{suffix}"
    assert updated.enabled is False
    assert updated.updated_at >= created_at

    assert repository.delete_query(query.id) is True
    assert repository.get_query(query.id) is None
    assert repository.delete_query(query.id) is False


def test_research_metric_crud_and_latest_by_researched_at(
    db_session: Session, clean_db: None
) -> None:
    repository = MarketRepository(db_session)
    query_id = _new_query(repository, suffix=uuid4().hex)
    earlier = _utc_datetime(2026, 2, 1)
    later = earlier + timedelta(days=1)

    first = repository.add_research_metric(
        query_id=query_id,
        period_days=90,
        sold_count=10,
        active_count=20,
        seller_count=5,
        median_sold_price=Decimal("100.2500"),
        average_sold_price=Decimal("101.5000"),
        minimum_sold_price=Decimal("80.0000"),
        maximum_sold_price=Decimal("140.0000"),
        average_shipping=Decimal("12.0000"),
        currency="USD",
        sell_through_rate=Decimal("0.500000"),
        researched_at=earlier,
        notes="earlier",
    )
    second = repository.add_research_metric(
        query_id=query_id,
        period_days=90,
        sold_count=12,
        currency="USD",
        researched_at=later,
        notes="later",
    )

    assert repository.get_research_metric(first.id) is first
    assert repository.get_latest_research_metric(query_id) is second
    assert second.sold_count == 12

    updated = repository.update_research_metric(second.id, sold_count=13, notes="updated")
    assert updated is second
    assert updated.sold_count == 13
    assert updated.notes == "updated"

    assert repository.delete_research_metric(second.id) is True
    assert repository.get_latest_research_metric(query_id) is first
    assert repository.delete_research_metric(first.id) is True
    assert repository.get_latest_research_metric(query_id) is None
    assert repository.delete_query(query_id) is True


def test_ebay_listing_upsert_active_filter_and_unique_constraint(
    db_session: Session, clean_db: None
) -> None:
    repository = MarketRepository(db_session)
    query_id = _new_query(repository, suffix=uuid4().hex)
    base_time = _utc_datetime(2026, 3, 1)
    external_item_id = f"item-{uuid4().hex}"

    listing = _new_listing(
        repository,
        query_id=query_id,
        external_item_id=external_item_id,
        seen_at=base_time,
    )
    inactive = _new_listing(
        repository,
        query_id=query_id,
        external_item_id=f"inactive-{uuid4().hex}",
        seen_at=base_time + timedelta(minutes=1),
        is_active=False,
    )
    updated = repository.upsert_ebay_listing(
        query_id=query_id,
        source="EBAY_BROWSE",
        external_item_id=external_item_id,
        title="Updated Japanese test item",
        match_method="MODEL",
        match_confidence=Decimal("0.990000"),
        is_active=True,
        first_seen_at=base_time + timedelta(days=2),
        last_seen_at=base_time + timedelta(days=1),
    )

    assert updated.id == listing.id
    assert updated.title == "Updated Japanese test item"
    assert updated.first_seen_at == base_time
    assert updated.last_seen_at == base_time + timedelta(days=1)
    assert (
        repository.get_ebay_listing_by_external_id(
            source="EBAY_BROWSE", external_item_id=external_item_id
        )
        is listing
    )
    assert repository.get_active_listings(query_id) == [listing]

    duplicate = EbayListing(
        query_id=query_id,
        source="EBAY_BROWSE",
        external_item_id=external_item_id,
        title="Constraint duplicate",
        match_method="TITLE",
        match_confidence=Decimal("0.500000"),
        is_active=True,
        first_seen_at=base_time,
        last_seen_at=base_time,
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(duplicate)
        db_session.flush()

    assert repository.delete_ebay_listing(inactive.id) is True
    assert repository.delete_ebay_listing(listing.id) is True
    assert repository.get_active_listings(query_id) == []
    assert repository.delete_query(query_id) is True


def test_listing_snapshot_crud_and_latest_by_captured_at(
    db_session: Session, clean_db: None
) -> None:
    repository = MarketRepository(db_session)
    query_id = _new_query(repository, suffix=uuid4().hex)
    listing = _new_listing(
        repository,
        query_id=query_id,
        external_item_id=f"snapshot-{uuid4().hex}",
        seen_at=_utc_datetime(2026, 4, 1),
    )
    earlier = _utc_datetime(2026, 4, 1, 1)
    later = earlier + timedelta(hours=1)

    first = repository.add_listing_snapshot(
        listing_id=listing.id,
        price_usd=Decimal("150.123456"),
        shipping_usd=Decimal("10.000000"),
        currency="USD",
        quantity_available=2,
        captured_at=earlier,
        raw_payload={"sequence": 1},
    )
    second = repository.add_listing_snapshot(
        listing_id=listing.id,
        price_usd=Decimal("145.000000"),
        captured_at=later,
        raw_payload={"sequence": 2},
    )

    assert repository.get_listing_snapshot(first.id) is first
    assert repository.get_latest_listing_snapshot(listing.id) is second
    assert second.price_usd == Decimal("145.000000")

    updated = repository.update_listing_snapshot(
        second.id,
        price_usd=Decimal("144.500000"),
        quantity_available=1,
    )
    assert updated is second
    assert updated.price_usd == Decimal("144.500000")
    assert updated.quantity_available == 1

    assert repository.delete_listing_snapshot(second.id) is True
    assert repository.get_latest_listing_snapshot(listing.id) is first
    assert repository.delete_listing_snapshot(first.id) is True
    assert repository.get_latest_listing_snapshot(listing.id) is None
    assert repository.delete_ebay_listing(listing.id) is True
    assert repository.delete_query(query_id) is True
