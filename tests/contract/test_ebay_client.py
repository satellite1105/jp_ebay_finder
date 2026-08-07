"""Contract tests for eBay OAuth and Browse API clients."""

from __future__ import annotations

from base64 import b64encode

import httpx
import pytest
import respx

from opportunity_finder.clients.base import NonRetryableApiError
from opportunity_finder.clients.ebay_auth import EBAY_OAUTH_SCOPE, EbayAuthClient
from opportunity_finder.clients.ebay_browse import EbayAccessDeniedError, EbayBrowseClient

BASE_URL = "https://ebay.example.test"
TOKEN_URL = f"{BASE_URL}/identity/v1/oauth2/token"
SEARCH_URL = f"{BASE_URL}/buy/browse/v1/item_summary/search"
CLIENT_ID = "contract-client-id"
CLIENT_SECRET = "contract-client-secret"


def make_auth(*, max_attempts: int = 3) -> EbayAuthClient:
    return EbayAuthClient(
        CLIENT_ID,
        CLIENT_SECRET,
        base_url=BASE_URL,
        token_url=TOKEN_URL,
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


def make_browse(auth: EbayAuthClient, *, max_attempts: int = 3) -> EbayBrowseClient:
    return EbayBrowseClient(
        auth,
        base_url=BASE_URL,
        marketplace_id="EBAY_US",
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


def token_response(token: str = "application-token") -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": 7200, "token_type": "Application Access Token"},
    )


@respx.mock
def test_client_credentials_token_is_cached() -> None:
    route = respx.post(TOKEN_URL).mock(return_value=token_response())

    with make_auth() as auth:
        assert auth.get_token() == "application-token"
        assert auth.get_token() == "application-token"

    assert route.call_count == 1
    request = route.calls.last.request
    expected_basic = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {expected_basic}"
    assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    form = httpx.QueryParams(request.content.decode())
    assert form["grant_type"] == "client_credentials"
    assert form["scope"] == EBAY_OAUTH_SCOPE


@respx.mock
def test_token_is_refreshed_near_expiration() -> None:
    now = [100.0]
    route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "token-1", "expires_in": 100}),
            httpx.Response(200, json={"access_token": "token-2", "expires_in": 100}),
        ]
    )
    auth = EbayAuthClient(
        CLIENT_ID,
        CLIENT_SECRET,
        base_url=BASE_URL,
        token_url=TOKEN_URL,
        expiry_skew=10,
        clock=lambda: now[0],
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )

    with auth:
        assert auth.get_token() == "token-1"
        now[0] = 189.0
        assert auth.get_token() == "token-1"
        now[0] = 190.0
        assert auth.get_token() == "token-2"

    assert route.call_count == 2


@respx.mock
def test_keyword_search_uses_bearer_token() -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    route = respx.get(SEARCH_URL, params={"q": "vintage camera"}).mock(
        return_value=httpx.Response(200, json={"itemSummaries": [{"itemId": "item-1"}]})
    )

    with make_auth() as auth, make_browse(auth) as browse:
        payload = browse.search(keyword="vintage camera")

    assert payload == {"itemSummaries": [{"itemId": "item-1"}]}
    assert route.calls.last.request.headers["Authorization"] == "Bearer application-token"
    assert route.calls.last.request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"


@respx.mock
def test_gtin_search() -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    route = respx.get(SEARCH_URL, params={"gtin": "4901234567890"}).mock(
        return_value=httpx.Response(200, json={"itemSummaries": [{"itemId": "item-gtin"}]})
    )

    with make_auth() as auth, make_browse(auth) as browse:
        payload = browse.search(gtin="4901234567890")

    assert payload["itemSummaries"] == [{"itemId": "item-gtin"}]
    assert route.call_count == 1


@respx.mock
def test_pagination_follows_next_url_instead_of_total() -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    next_url = f"{SEARCH_URL}?q=camera&offset=1"
    route = respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "itemSummaries": [{"itemId": "item-1"}],
                    "total": 999999,
                    "next": next_url,
                },
            ),
            httpx.Response(200, json={"itemSummaries": [{"itemId": "item-2"}]}),
        ]
    )

    with make_auth() as auth, make_browse(auth) as browse:
        payload = browse.search(keyword="camera")

    assert route.call_count == 2
    assert str(route.calls[1].request.url) == next_url
    assert payload["itemSummaries"] == [{"itemId": "item-1"}, {"itemId": "item-2"}]
    assert "next" not in payload


@respx.mock
def test_401_refreshes_token_once_then_propagates_second_401() -> None:
    token_route = respx.post(TOKEN_URL).mock(
        side_effect=[token_response("stale-token"), token_response("fresh-token")]
    )
    search_route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(401, json={"errors": [{"message": "invalid token"}]})
    )

    with (
        make_auth() as auth,
        make_browse(auth) as browse,
        pytest.raises(NonRetryableApiError) as exc_info,
    ):
        browse.search(keyword="camera")

    assert exc_info.value.status_code == 401
    assert token_route.call_count == 2
    assert search_route.call_count == 2
    assert search_route.calls[0].request.headers["Authorization"] == "Bearer stale-token"
    assert search_route.calls[1].request.headers["Authorization"] == "Bearer fresh-token"


@pytest.mark.parametrize(
    ("status_code", "error_payload"),
    [
        (403, {"errors": [{"message": "Access denied"}]}),
        (400, {"errors": [{"message": "Application is not authorized for production access"}]}),
        (400, {"errors": [{"message": "Insufficient permission"}]}),
    ],
)
@respx.mock
def test_403_and_permission_errors_raise_access_denied(
    status_code: int, error_payload: dict
) -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(status_code, json=error_payload))

    with (
        make_auth() as auth,
        make_browse(auth) as browse,
        pytest.raises(EbayAccessDeniedError) as exc_info,
    ):
        browse.search(keyword="camera")

    assert exc_info.value.status_code == status_code
    assert route.call_count == 1


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
@respx.mock
def test_browse_retries_429_and_5xx(status_code: int) -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    route = respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(status_code, json={"error": "temporary"}),
            httpx.Response(200, json={"itemSummaries": []}),
        ]
    )

    with make_auth() as auth, make_browse(auth) as browse:
        assert browse.search(keyword="camera") == {"itemSummaries": []}

    assert route.call_count == 2


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
@respx.mock
def test_token_request_retries_429_and_5xx(status_code: int) -> None:
    route = respx.post(TOKEN_URL).mock(
        side_effect=[httpx.Response(status_code, json={"error": "temporary"}), token_response()]
    )

    with make_auth() as auth:
        assert auth.get_token() == "application-token"

    assert route.call_count == 2
