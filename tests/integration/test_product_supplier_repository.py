"""Integration tests for product and supplier repositories against MySQL."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_finder.db.models import Product, SupplierItem
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository


def test_get_or_create_reuses_product_with_same_jan(db_session: Session, clean_db: None) -> None:
    repository = ProductRepository(db_session)

    created = repository.get_or_create(
        jan_code="4901234567894",
        internal_sku="SKU-FIRST",
        normalized_name="test product",
        original_name="Test Product",
    )
    duplicate = repository.get_or_create(
        jan_code="4901234567894",
        internal_sku="SKU-SECOND",
        normalized_name="different name",
        original_name="Different Name",
    )

    assert duplicate.id == created.id
    assert duplicate.internal_sku == "SKU-FIRST"
    assert repository.get_by_jan("4901234567894") is created
    assert repository.get_by_id(created.id) is created
    assert db_session.scalar(select(func.count()).select_from(Product)) == 1


def test_database_rejects_duplicate_product_jan(db_session: Session, clean_db: None) -> None:
    original = _create_product(db_session)
    duplicate = Product(
        jan_code=original.jan_code,
        internal_sku="OTHER-SKU",
        normalized_name="duplicate product",
        original_name="Duplicate Product",
        created_at=original.created_at,
        updated_at=original.updated_at,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_upsert_supplier_item_updates_same_source_external_id(
    db_session: Session, clean_db: None
) -> None:
    product = _create_product(db_session)
    repository = SupplierRepository(db_session)
    first_seen_input = datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)
    last_seen_input = first_seen_input + timedelta(hours=1)
    first_seen = first_seen_input.replace(tzinfo=None)
    last_seen = last_seen_input.replace(tzinfo=None)

    created = repository.upsert_supplier_item(
        product_id=product.id,
        source="YAHOO",
        external_item_id="item-123",
        shop_name="First Shop",
        title="First title",
        item_url="https://example.test/first",
        jan_code=product.jan_code,
        brand="First Brand",
        model_number="MODEL-1",
        match_method="JAN",
        match_confidence=Decimal("1.000000"),
        is_active=True,
        first_seen_at=first_seen_input,
        last_seen_at=first_seen_input,
        raw_payload={"version": 1},
    )
    updated = repository.upsert_supplier_item(
        product_id=product.id,
        source="YAHOO",
        external_item_id="item-123",
        shop_name="Updated Shop",
        title="Updated title",
        item_url="https://example.test/updated",
        jan_code=product.jan_code,
        brand="Updated Brand",
        model_number="MODEL-2",
        match_method="MODEL_NUMBER",
        match_confidence=Decimal("0.950000"),
        is_active=False,
        first_seen_at=last_seen_input,
        last_seen_at=last_seen_input,
        raw_payload={"version": 2},
    )

    assert updated.id == created.id
    assert updated.first_seen_at == first_seen
    assert updated.last_seen_at == last_seen
    assert updated.shop_name == "Updated Shop"
    assert updated.title == "Updated title"
    assert updated.match_method == "MODEL_NUMBER"
    assert updated.match_confidence == Decimal("0.950000")
    assert updated.is_active is False
    assert updated.raw_payload == {"version": 2}
    assert repository.get_supplier_item("YAHOO", "item-123") is updated
    assert db_session.scalar(select(func.count()).select_from(SupplierItem)) == 1


def test_database_rejects_duplicate_supplier_external_identity(
    db_session: Session, clean_db: None
) -> None:
    original = _create_supplier_item(db_session)
    duplicate = SupplierItem(
        product_id=original.product_id,
        source=original.source,
        external_item_id=original.external_item_id,
        title="Duplicate supplier item",
        match_method="JAN",
        match_confidence=Decimal(1),
        first_seen_at=original.first_seen_at,
        last_seen_at=original.last_seen_at,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_add_price_snapshot_preserves_effective_cost(db_session: Session, clean_db: None) -> None:
    supplier_item = _create_supplier_item(db_session)
    repository = SupplierRepository(db_session)

    snapshot = repository.add_price_snapshot(
        supplier_item_id=supplier_item.id,
        item_price_jpy=Decimal("1000.0000"),
        domestic_shipping_jpy=Decimal("300.0000"),
        points_value_jpy=Decimal("50.0000"),
        coupon_value_jpy=Decimal("100.0000"),
        available=True,
        effective_cost_jpy=Decimal("1150.0000"),
        captured_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        raw_payload={"price": "1000"},
    )

    db_session.expire(snapshot)
    loaded = repository.get_latest_price_snapshot(supplier_item.id)

    assert loaded is not None
    assert loaded.id == snapshot.id
    assert loaded.effective_cost_jpy == Decimal("1150.0000")
    assert loaded.domestic_shipping_jpy == Decimal("300.0000")
    assert loaded.points_value_jpy == Decimal("50.0000")
    assert loaded.coupon_value_jpy == Decimal("100.0000")


def test_get_latest_price_snapshot_orders_by_captured_at(
    db_session: Session, clean_db: None
) -> None:
    supplier_item = _create_supplier_item(db_session)
    repository = SupplierRepository(db_session)
    newer_time = datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC)
    older_time = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)

    newer = repository.add_price_snapshot(
        supplier_item_id=supplier_item.id,
        item_price_jpy=Decimal(1200),
        domestic_shipping_jpy=Decimal(0),
        available=True,
        effective_cost_jpy=Decimal(1200),
        captured_at=newer_time,
    )
    repository.add_price_snapshot(
        supplier_item_id=supplier_item.id,
        item_price_jpy=Decimal(1000),
        domestic_shipping_jpy=Decimal(0),
        available=True,
        effective_cost_jpy=Decimal(1000),
        captured_at=older_time,
    )

    latest = repository.get_latest_price_snapshot(supplier_item.id)

    assert latest is not None
    assert latest.id == newer.id
    assert latest.captured_at == newer_time.replace(tzinfo=None)
    assert latest.effective_cost_jpy == Decimal("1200.0000")


def _create_product(db_session: Session) -> Product:
    return ProductRepository(db_session).get_or_create(
        jan_code="4987654321098",
        internal_sku="TEST-SKU",
        normalized_name="repository test product",
        original_name="Repository Test Product",
    )


def _create_supplier_item(db_session: Session) -> SupplierItem:
    product = _create_product(db_session)
    return SupplierRepository(db_session).upsert_supplier_item(
        product_id=product.id,
        source="RAKUTEN",
        external_item_id="snapshot-item",
        title="Snapshot test item",
        jan_code=product.jan_code,
        match_method="JAN",
        match_confidence=Decimal(1),
        first_seen_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
