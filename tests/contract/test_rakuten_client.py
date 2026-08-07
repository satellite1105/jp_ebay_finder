"""Contract tests for the two Rakuten API clients and their normalizers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from opportunity_finder.clients.base import NonRetryableApiError
from opportunity_finder.clients.rakuten_ichiba import (
    ICHIBA_ITEM_SEARCH_PATH,
    RakutenIchibaClient,
)
from opportunity_finder.clients.rakuten_product import (
    PRODUCT_SEARCH_PATH,
    RakutenProductClient,
)
from opportunity_finder.normalizers.rakuten_normalizer import (
    normalize_ichiba_response,
    normalize_product_response,
)

BASE_URL = "https://rakuten.example.test"
APPLICATION_ID = "test-application-id"
CAPTURED_AT = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
NON_RETRYABLE_STATUS_CODES = (400, 401, 403, 404)


def make_ichiba_client(*, max_attempts: int = 3) -> RakutenIchibaClient:
    return RakutenIchibaClient(
        APPLICATION_ID,
        affiliate_id="test-affiliate-id",
        base_url=BASE_URL,
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


def make_product_client(*, max_attempts: int = 3) -> RakutenProductClient:
    return RakutenProductClient(
        APPLICATION_ID,
        base_url=BASE_URL,
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


@respx.mock
def test_ichiba_success_normalizes_to_supplier_offer() -> None:
    item = {
        "itemCode": "shop-1:item-123",
        "itemName": "Kokuyo Campus Notebook",
        "itemPrice": 3200,
        "availability": 1,
        "postageFlag": 1,
        "shippingPrice": 550,
        "pointRate": 2,
        "janCode": "4901480123456",
        "brandName": "KOKUYO",
        "modelNumber": "NO-3AN",
        "itemUrl": "https://item.rakuten.example/item-123",
    }
    route = respx.get(f"{BASE_URL}{ICHIBA_ITEM_SEARCH_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={"Items": [{"Item": item}], "page": 1, "pageCount": 3},
        )
    )

    with make_ichiba_client() as client:
        payload = client.search_by_keyword("Campus NO-3AN")
    offers = normalize_ichiba_response(payload, captured_at=CAPTURED_AT)

    assert route.call_count == 1
    assert route.calls.last.request.url.params["applicationId"] == APPLICATION_ID
    assert route.calls.last.request.url.params["affiliateId"] == "test-affiliate-id"
    assert route.calls.last.request.url.params["keyword"] == "Campus NO-3AN"
    assert route.calls.last.request.url.params["page"] == "1"
    assert len(offers) == 1
    offer = offers[0]
    assert offer.source == "RAKUTEN"
    assert offer.external_item_id == "shop-1:item-123"
    assert offer.title == "Kokuyo Campus Notebook"
    assert offer.item_price_jpy == Decimal(3200)
    assert offer.domestic_shipping_jpy == Decimal(550)
    assert offer.points_value_jpy == Decimal(64)
    assert offer.available is True
    assert offer.jan_code == "4901480123456"
    assert offer.brand == "KOKUYO"
    assert offer.model_number == "NO-3AN"
    assert offer.captured_at == CAPTURED_AT
    assert offer.raw_payload == item


@respx.mock
def test_product_success_normalizes_to_supplier_offer() -> None:
    product = {
        "productId": "product-456",
        "productName": "Kokuyo Campus Notebook A5",
        "salesMinPrice": 2980,
        "salesMaxPrice": 3980,
        "brandName": "KOKUYO",
        "productNo": "NO-3AN",
        "janCode": "4901480123456",
        "productUrlPC": "https://product.rakuten.example/product-456",
    }
    route = respx.get(f"{BASE_URL}{PRODUCT_SEARCH_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={"Products": [{"Product": product}], "page": 1, "pageCount": 1},
        )
    )

    with make_product_client() as client:
        payload = client.search_by_jan("4901480123456")
    offers = normalize_product_response(
        payload,
        jan_code="4901480123456",
        captured_at=CAPTURED_AT,
    )

    assert route.call_count == 1
    assert route.calls.last.request.url.params["applicationId"] == APPLICATION_ID
    assert route.calls.last.request.url.params["keyword"] == "4901480123456"
    assert len(offers) == 1
    offer = offers[0]
    assert offer.source == "RAKUTEN"
    assert offer.external_item_id == "product-456"
    assert offer.title == "Kokuyo Campus Notebook A5"
    assert offer.item_price_jpy == Decimal(2980)
    assert offer.domestic_shipping_jpy == Decimal(0)
    assert offer.available is True
    assert offer.jan_code == "4901480123456"
    assert offer.brand == "KOKUYO"
    assert offer.model_number == "NO-3AN"
    assert offer.captured_at == CAPTURED_AT
    assert offer.raw_payload == product


@pytest.mark.parametrize("status_code", RETRYABLE_STATUS_CODES)
@pytest.mark.parametrize("client_kind", ["ichiba", "product"])
@respx.mock
def test_retryable_status_is_retried(status_code: int, client_kind: str) -> None:
    if client_kind == "ichiba":
        path = ICHIBA_ITEM_SEARCH_PATH
        client = make_ichiba_client()
        call = lambda: client.search_by_keyword("notebook")
        success_payload = {"Items": []}
    else:
        path = PRODUCT_SEARCH_PATH
        client = make_product_client()
        call = lambda: client.search_by_jan("4901480123456")
        success_payload = {"Products": []}

    route = respx.get(f"{BASE_URL}{path}").mock(
        side_effect=[
            httpx.Response(status_code, json={"error": "temporary"}),
            httpx.Response(200, json=success_payload),
        ]
    )

    with client:
        payload = call()

    assert payload == success_payload
    assert route.call_count == 2


@pytest.mark.parametrize("status_code", NON_RETRYABLE_STATUS_CODES)
@pytest.mark.parametrize("client_kind", ["ichiba", "product"])
@respx.mock
def test_non_retryable_status_is_not_retried(status_code: int, client_kind: str) -> None:
    if client_kind == "ichiba":
        path = ICHIBA_ITEM_SEARCH_PATH
        client = make_ichiba_client()
        call = lambda: client.search_by_keyword("notebook")
    else:
        path = PRODUCT_SEARCH_PATH
        client = make_product_client()
        call = lambda: client.search_by_jan("4901480123456")

    route = respx.get(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(status_code, json={"error": "invalid request"})
    )

    with client, pytest.raises(NonRetryableApiError) as exc_info:
        call()

    assert exc_info.value.status_code == status_code
    assert route.call_count == 1


@pytest.mark.parametrize("client_kind", ["ichiba", "product"])
@respx.mock
def test_page_parameter_is_forwarded(client_kind: str) -> None:
    if client_kind == "ichiba":
        path = ICHIBA_ITEM_SEARCH_PATH
        client = make_ichiba_client()
        call = lambda: client.search_by_keyword("notebook", page=4)
        payload = {"Items": [], "page": 4, "pageCount": 8}
    else:
        path = PRODUCT_SEARCH_PATH
        client = make_product_client()
        call = lambda: client.search_by_jan("4901480123456", page=4)
        payload = {"Products": [], "page": 4, "pageCount": 8}

    route = respx.get(f"{BASE_URL}{path}").mock(return_value=httpx.Response(200, json=payload))

    with client:
        assert call() == payload

    assert route.calls.last.request.url.params["page"] == "4"


def test_normalizers_reject_changed_response_shapes() -> None:
    with pytest.raises(ValidationError):
        normalize_ichiba_response({"Items": [{"unexpected": {}}]})
    with pytest.raises(ValidationError):
        normalize_product_response({"Products": [{"unexpected": {}}]})
