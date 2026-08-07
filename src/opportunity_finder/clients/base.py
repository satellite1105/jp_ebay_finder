"""Shared synchronous HTTP client with safe logging and bounded retries."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Self
from uuid import uuid4

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from opportunity_finder.logging_config import mask_secret

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "app_id",
    "access_key",
    "affiliate_id",
    "application_id",
    "authorization",
    "client_id",
    "client_secret",
    "password",
    "secret",
    "token",
)


class _ApiError(RuntimeError):
    """Base class carrying the failed response and request correlation ID."""

    def __init__(self, response: httpx.Response, request_id: str) -> None:
        self.response = response
        self.status_code = response.status_code
        self.request_id = request_id
        super().__init__(
            f"API request failed with HTTP {response.status_code} (request_id={request_id})"
        )


class RetryableApiError(_ApiError):
    """An API response that may succeed when attempted again."""


class NonRetryableApiError(_ApiError):
    """An API response that must be reported without another attempt."""


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_for_log(value: Any, *, key: object | None = None) -> Any:
    """Return a logging-safe copy, using the application's canonical masker."""
    if key is not None and _is_sensitive_key(key):
        return mask_secret(str(value))
    if isinstance(value, Mapping):
        return {
            item_key: _sanitize_for_log(item_value, key=item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, tuple):
        if len(value) == 2 and isinstance(value[0], str):
            return (value[0], _sanitize_for_log(value[1], key=value[0]))
        return tuple(_sanitize_for_log(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    return value


class ApiClient:
    """Wrap ``httpx.Client`` with request correlation and status-based retries."""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_attempts: int = 3,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_jitter: float = 1.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("connect_timeout and read_timeout must be greater than zero")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if backoff_initial < 0 or backoff_max < 0 or backoff_jitter < 0:
            raise ValueError("backoff values must not be negative")

        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)
        self.max_attempts = max_attempts
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._backoff_jitter = backoff_jitter
        self.last_request_id: str | None = None

    def request(
        self,
        method: str,
        url: str | httpx.URL,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send one logical request and return its unmodified JSON object."""
        request_id = str(uuid4())
        self.last_request_id = request_id

        request_headers = httpx.Headers(headers)
        request_headers["X-Request-ID"] = request_id
        effective_headers = httpx.Headers(self._client.headers)
        effective_headers.update(request_headers)
        safe_headers = _sanitize_for_log(dict(effective_headers))
        safe_params = _sanitize_for_log(kwargs.get("params"))
        safe_url = self._safe_absolute_url(url)

        logger.info(
            "API request started request_id=%s method=%s url=%s headers=%s params=%s",
            request_id,
            method.upper(),
            safe_url,
            safe_headers,
            safe_params,
            extra={"request_id": request_id, "method": method.upper(), "url": safe_url},
        )

        retrying = Retrying(
            retry=retry_if_exception_type(RetryableApiError),
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential_jitter(
                initial=self._backoff_initial,
                max=self._backoff_max,
                jitter=self._backoff_jitter,
            ),
            before_sleep=self._log_retry,
            reraise=True,
        )
        return retrying(
            self._request_once,
            method,
            url,
            request_id=request_id,
            headers=request_headers,
            **kwargs,
        )

    def get(self, url: str | httpx.URL, **kwargs: Any) -> dict[str, Any]:
        """Send a GET request and return its JSON object."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str | httpx.URL, **kwargs: Any) -> dict[str, Any]:
        """Send a POST request and return its JSON object."""
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        """Close the wrapped HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _request_once(
        self,
        method: str,
        url: str | httpx.URL,
        *,
        request_id: str,
        headers: httpx.Headers,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, url, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            logger.warning(
                "API request timed out request_id=%s method=%s error_type=%s",
                request_id,
                method.upper(),
                type(exc).__name__,
                extra={
                    "request_id": request_id,
                    "method": method.upper(),
                    "error_type": type(exc).__name__,
                },
            )
            raise

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableApiError(response, request_id)
        if response.is_error:
            raise NonRetryableApiError(response, request_id)

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("API response JSON must be an object")

        logger.info(
            "API request succeeded request_id=%s method=%s status=%s",
            request_id,
            method.upper(),
            response.status_code,
            extra={
                "request_id": request_id,
                "method": method.upper(),
                "status": response.status_code,
            },
        )
        return payload

    def _safe_absolute_url(self, url: str | httpx.URL) -> str:
        absolute_url = self._client.base_url.join(httpx.URL(url))
        return str(absolute_url).split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]

    @staticmethod
    def _log_retry(retry_state: RetryCallState) -> None:
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if not isinstance(exception, RetryableApiError):
            return
        logger.warning(
            "API request will be retried request_id=%s status=%s retry_count=%s",
            exception.request_id,
            exception.status_code,
            retry_state.attempt_number,
            extra={
                "request_id": exception.request_id,
                "status": exception.status_code,
                "retry_count": retry_state.attempt_number,
            },
        )


__all__ = ["ApiClient", "NonRetryableApiError", "RetryableApiError"]
