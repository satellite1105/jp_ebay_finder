"""Contract tests for eBay response normalization and CSV fallback."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import respx

from opportunity_finder.clients.ebay_auth import EbayAuthClient
from opportunity_finder.clients.ebay_browse import EbayBrowseClient
from opportunity_finder.config import Settings
from opportunity_finder.db.models import AuditLog, MarketQuery
from opportunity_finder.normalizers.ebay_normalizer import normalize_ebay_response
from opportunity_finder.services.ebay_service import EbayService

BASE_URL = "https://ebay-fallback.example.test"
TOKEN_URL = f"{BASE_URL}/identity/v1/oauth2/token"
SEARCH_URL = f"{BASE_URL}/buy/browse/v1/item_summary/search"


class _SessionStub:
    def __init__(self, query: Any) -> None:
        self.query = query
        self.added: list[Any] = []

    def get(self, model: type[Any], row_id: int) -> Any:
        if model is MarketQuery and row_id == self.query.id:
            return self.query
        return None

    def add(self, value: Any) -> None:
        self.added.append(value)

    def flush(self) -> None:
        return None


def test_normalize_extracts_price_shipping_condition_and_seller_country() -> None:
    raw = {
        "total": 5000,
        "itemSummaries": [
            {
                "itemId": "v1|123|0",
                "title": "Sony Camera New",
                "itemWebUrl": "https://www.ebay.com/itm/123",
                "price": {"value": "149.95", "currency": "USD"},
                "shippingOptions": [
                    {"shippingCost": {"value": "12.50", "currency": "USD"}},
                    {"shippingCost": {"value": "8.25", "currency": "USD"}},
                ],
                "condition": "New with defects",
                "itemLocation": {"country": "us"},
                "seller": {"username": "camera-shop"},
                "estimatedAvailabilities": [{"estimatedAvailableQuantity": 3}],
            }
        ],
    }

    listings = normalize_ebay_response(raw)

    assert len(listings) == 1
    listing = listings[0]
    assert str(listing.price) == "149.95"
    assert str(listing.shipping) == "8.25"
    assert listing.currency == "USD"
    assert listing.condition_raw == "New with defects"
    assert listing.condition_normalized == "new"
    assert listing.seller_country == "US"
    assert listing.seller_username == "camera-shop"
    assert listing.quantity_available == 3


@respx.mock
def test_access_denied_falls_back_without_propagating() -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "test-token", "expires_in": 7200},
        )
    )
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(403, json={"errors": [{"message": "Access denied"}]})
    )
    query = SimpleNamespace(
        id=7,
        query_text="Sony camera",
        query_type="KEYWORD",
        product_id=None,
        condition_filter=None,
        enabled=True,
    )
    session = _SessionStub(query)
    settings = Settings(_env_file=None, ebay_enabled=True)

    with (
        EbayAuthClient(
            "client-id",
            "client-secret",
            base_url=BASE_URL,
            token_url=TOKEN_URL,
            backoff_initial=0,
            backoff_max=0,
            backoff_jitter=0,
        ) as auth,
        EbayBrowseClient(
            auth,
            base_url=BASE_URL,
            marketplace_id="EBAY_US",
            backoff_initial=0,
            backoff_max=0,
            backoff_jitter=0,
        ) as browse,
    ):
        summary = EbayService(session, browse, settings=settings).refresh_listings([query.id])  # type: ignore[arg-type]

    assert summary.fallback_to_csv is True
    assert summary.listings_saved == 0
    audit_logs = [row for row in session.added if isinstance(row, AuditLog)]
    assert len(audit_logs) == 1
    assert audit_logs[0].action == "fallback_to_csv"
    assert audit_logs[0].reason is not None
    assert "access denied" in audit_logs[0].reason.lower()
