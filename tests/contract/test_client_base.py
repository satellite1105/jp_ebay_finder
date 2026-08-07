"""Contract tests for the shared synchronous API client."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from opportunity_finder.clients.base import (
    ApiClient,
    NonRetryableApiError,
    RetryableApiError,
)

BASE_URL = "https://api.example.test"
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
NON_RETRYABLE_STATUS_CODES = (400, 401, 403, 404)


def make_client(*, max_attempts: int = 3) -> ApiClient:
    """Create a fast client whose retry waits are disabled for contract tests."""
    return ApiClient(
        base_url=BASE_URL,
        connect_timeout=0.1,
        read_timeout=0.1,
        max_attempts=max_attempts,
        backoff_initial=0,
        backoff_max=0,
        backoff_jitter=0,
    )


@respx.mock
def test_returns_raw_json_dict_for_successful_response() -> None:
    route = respx.get(f"{BASE_URL}/items").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "item-1"}]})
    )

    with make_client() as client:
        payload = client.get("/items")

    assert payload == {"items": [{"id": "item-1"}]}
    assert route.call_count == 1
    assert client.last_request_id is not None


@pytest.mark.parametrize("status_code", RETRYABLE_STATUS_CODES)
@respx.mock
def test_retryable_status_is_retried_until_success(status_code: int) -> None:
    route = respx.get(f"{BASE_URL}/items").mock(
        side_effect=[
            httpx.Response(status_code, json={"error": "temporary"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    with make_client(max_attempts=3) as client:
        payload = client.get("/items")

    assert payload == {"ok": True}
    assert route.call_count == 2


@pytest.mark.parametrize("status_code", RETRYABLE_STATUS_CODES)
@respx.mock
def test_retryable_status_fails_after_max_attempts(status_code: int) -> None:
    route = respx.get(f"{BASE_URL}/items").mock(
        return_value=httpx.Response(status_code, json={"error": "temporary"})
    )

    with make_client(max_attempts=3) as client, pytest.raises(RetryableApiError) as exc_info:
        client.get("/items")

    assert exc_info.value.status_code == status_code
    assert route.call_count == 3


@pytest.mark.parametrize("status_code", NON_RETRYABLE_STATUS_CODES)
@respx.mock
def test_non_retryable_status_is_not_retried(status_code: int) -> None:
    route = respx.get(f"{BASE_URL}/items").mock(
        return_value=httpx.Response(status_code, json={"error": "invalid request"})
    )

    with make_client(max_attempts=3) as client, pytest.raises(NonRetryableApiError) as exc_info:
        client.get("/items")

    assert exc_info.value.status_code == status_code
    assert route.call_count == 1


@respx.mock
def test_timeout_is_propagated_without_retry() -> None:
    route = respx.get(f"{BASE_URL}/slow").mock(side_effect=httpx.ReadTimeout("timed out"))

    with make_client(max_attempts=3) as client, pytest.raises(httpx.ReadTimeout):
        client.get("/slow")

    assert route.call_count == 1


@respx.mock
def test_logs_request_id_and_masks_authorization_and_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    authorization = "Bearer highly-sensitive-token"
    api_key = "highly-sensitive-api-key"
    route = respx.get(f"{BASE_URL}/items").mock(return_value=httpx.Response(200, json={"ok": True}))

    caplog.set_level(logging.INFO, logger="opportunity_finder.clients.base")
    with make_client() as client:
        client.get(
            "/items",
            headers={"Authorization": authorization, "X-API-Key": api_key},
        )

    assert route.call_count == 1
    assert client.last_request_id is not None
    assert client.last_request_id in caplog.text
    assert authorization not in caplog.text
    assert "highly-sensitive-token" not in caplog.text
    assert api_key not in caplog.text
    assert "***" in caplog.text
