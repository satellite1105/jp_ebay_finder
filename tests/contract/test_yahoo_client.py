"""Contract tests for Yahoo! Shopping search and response normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from opportunity_finder.clients.base import NonRetryableApiError, RetryableApiError
from opportunity_finder.clients.yahoo_shopping import (
    YahooShoppingClient,
    YahooShoppingDisabledError,
)
from opportunity_finder.domain.models import SupplierOffer
from opportunity_finder.normalizers.yahoo_normalizer import normalize_yahoo_response

BASE_URL = "https://shopping.yahooapis.jp"
SEARCH_URL = f"{BASE_URL}/ShoppingWebService/V3/itemSearch"
APP_ID = "contract-test-app-id"
JAN_CODE = "4901234567890"
NON_RETRYABLE_STATUS_CODES = (400, 401, 403, 404)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)


def make_client(*, max_attempts: int = 3, enabled: bool = True) -> YahooShoppingClient:
    return YahooShoppingClient(
        app_id=APP_ID,
        enabled=enabled,
        base_url=BASE_URL,
        connect_timeout=0.1,
        read_timeout=0.1,
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


def yahoo_response(*, hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "totalResultsAvailable": len(hits),
        "totalResultsReturned": len(hits),
        "firstResultsPosition": 1,
        "request": {"query": "test"},
        "hits": hits,
    }


def yahoo_hit() -> dict[str, Any]:
    return {
        "index": 1,
        "name": "Contract Test Camera",
        "description": "A camera used by the contract test.",
        "inStock": True,
        "url": "https://store.shopping.yahoo.co.jp/example/item-123.html",
        "code": "example_item-123",
        "price": 12800,
        "point": {"amount": 100, "bonusAmount": 20},
        "shipping": {"code": 2, "name": "送料無料"},
        "brand": {"id": 123, "name": "Example Brand"},
        "janCode": JAN_CODE,
        "seller": {"sellerId": "example", "name": "Example Store"},
    }


@respx.mock
def test_search_prefers_jan_when_jan_has_hits() -> None:
    jan_route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "jan_code": JAN_CODE},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[yahoo_hit()])))
    query_route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "Contract Camera"},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[])))

    with make_client() as client:
        raw = client.search(jan_code=JAN_CODE, query="Contract Camera")

    assert raw["hits"][0]["code"] == "example_item-123"
    assert jan_route.call_count == 1
    assert query_route.call_count == 0


@respx.mock
def test_search_falls_back_to_query_when_jan_has_no_hits() -> None:
    jan_route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "jan_code": JAN_CODE},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[])))
    query_route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "Contract Camera"},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[yahoo_hit()])))

    with make_client() as client:
        raw = client.search(jan_code=JAN_CODE, query="Contract Camera")

    assert raw["hits"][0]["code"] == "example_item-123"
    assert jan_route.call_count == 1
    assert query_route.call_count == 1


@respx.mock
def test_search_uses_query_when_jan_is_not_provided() -> None:
    route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "Contract Camera"},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[yahoo_hit()])))

    with make_client() as client:
        raw = client.search(query="Contract Camera")

    assert raw == yahoo_response(hits=[yahoo_hit()])
    assert route.call_count == 1


@respx.mock
def test_200_response_normalizes_to_supplier_offer_and_preserves_raw_payload() -> None:
    hit = yahoo_hit()
    route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "jan_code": JAN_CODE},
    ).mock(return_value=httpx.Response(200, json=yahoo_response(hits=[hit])))
    captured_at = datetime(2026, 8, 8, 1, 2, 3, tzinfo=UTC)

    with make_client() as client:
        raw = client.search_by_jan(JAN_CODE)
    offers = normalize_yahoo_response(raw, captured_at=captured_at)

    assert route.call_count == 1
    assert len(offers) == 1
    offer = offers[0]
    assert isinstance(offer, SupplierOffer)
    assert offer.source == "YAHOO"
    assert offer.external_item_id == "example_item-123"
    assert offer.title == "Contract Test Camera"
    assert offer.item_price_jpy == Decimal(12800)
    assert offer.domestic_shipping_jpy == Decimal(0)
    assert offer.points_value_jpy == Decimal(120)
    assert offer.available is True
    assert offer.jan_code == JAN_CODE
    assert offer.brand == "Example Brand"
    assert offer.captured_at == captured_at
    assert offer.raw_payload == hit


@pytest.mark.parametrize("status_code", NON_RETRYABLE_STATUS_CODES)
@respx.mock
def test_non_retryable_status_is_not_retried(status_code: int) -> None:
    route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "camera"},
    ).mock(return_value=httpx.Response(status_code, json={"error": "invalid request"}))

    with make_client(max_attempts=3) as client, pytest.raises(NonRetryableApiError) as exc_info:
        client.search_by_query("camera")

    assert exc_info.value.status_code == status_code
    assert route.call_count == 1


@pytest.mark.parametrize("status_code", RETRYABLE_STATUS_CODES)
@respx.mock
def test_retryable_status_is_retried_to_max_attempts(status_code: int) -> None:
    route = respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "camera"},
    ).mock(return_value=httpx.Response(status_code, json={"error": "temporary"}))

    with make_client(max_attempts=3) as client, pytest.raises(RetryableApiError) as exc_info:
        client.search_by_query("camera")

    assert exc_info.value.status_code == status_code
    assert route.call_count == 3


@respx.mock
def test_schema_mismatch_raises_validation_error() -> None:
    invalid_payload = {
        "totalResultsAvailable": 1,
        "totalResultsReturned": 1,
        "firstResultsPosition": 1,
        "hits": [{"code": "broken", "price": "not-an-integer"}],
    }
    respx.get(
        SEARCH_URL,
        params={"appid": APP_ID, "query": "broken"},
    ).mock(return_value=httpx.Response(200, json=invalid_payload))

    with make_client() as client:
        raw = client.search_by_query("broken")

    with pytest.raises(ValidationError):
        normalize_yahoo_response(raw)


@respx.mock
def test_disabled_client_stops_before_http_request() -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json=yahoo_response(hits=[]))
    )

    with make_client(enabled=False) as client, pytest.raises(YahooShoppingDisabledError):
        client.search_by_query("camera")

    assert route.call_count == 0
