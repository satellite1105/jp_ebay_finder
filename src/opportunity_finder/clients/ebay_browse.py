"""Client for searching active listings with the eBay Browse API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from opportunity_finder.clients.base import ApiClient, NonRetryableApiError
from opportunity_finder.clients.ebay_auth import EBAY_API_BASE_URL, EbayAuthClient
from opportunity_finder.config import Settings

ITEM_SUMMARY_SEARCH_PATH = "/buy/browse/v1/item_summary/search"


class EbayAccessDeniedError(NonRetryableApiError):
    """Raised when eBay Browse access is not approved or lacks permission."""


class EbayBrowseDisabledError(RuntimeError):
    """Raised before a request when the optional eBay integration is disabled."""


class EbayBrowseClient(ApiClient):
    """Search eBay by keyword or GTIN, following response ``next`` links."""

    def __init__(
        self,
        auth_client: EbayAuthClient | None = None,
        *,
        settings: Settings | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        enabled: bool | None = None,
        marketplace_id: str | None = None,
        base_url: str = EBAY_API_BASE_URL,
        search_path: str = ITEM_SUMMARY_SEARCH_PATH,
        token_url: str | None = None,
        max_pages: int = 100,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_attempts: int = 3,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_jitter: float = 1.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("max_pages must be an integer greater than or equal to one")

        resolved_settings = settings or Settings()
        credentials_injected = client_id is not None or client_secret is not None
        resolved_enabled = (
            enabled
            if enabled is not None
            else (
                True
                if auth_client is not None or credentials_injected
                else resolved_settings.ebay_enabled
            )
        )
        resolved_marketplace_id = (
            marketplace_id if marketplace_id is not None else resolved_settings.ebay_marketplace_id
        ).strip()
        if not resolved_marketplace_id:
            raise ValueError("marketplace_id must not be empty")

        self.enabled = resolved_enabled
        self.marketplace_id = resolved_marketplace_id
        self.search_path = search_path
        self.max_pages = max_pages
        self._owns_auth_client = auth_client is None and resolved_enabled
        self.auth_client = auth_client
        if self.auth_client is None and resolved_enabled:
            self.auth_client = EbayAuthClient(
                client_id,
                client_secret,
                settings=resolved_settings,
                base_url=base_url,
                token_url=token_url,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                max_attempts=max_attempts,
                backoff_initial=backoff_initial,
                backoff_max=backoff_max,
                backoff_jitter=backoff_jitter,
            )

        super().__init__(
            base_url=base_url,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            max_attempts=max_attempts,
            backoff_initial=backoff_initial,
            backoff_max=backoff_max,
            backoff_jitter=backoff_jitter,
            headers=headers,
        )
        base = self._client.base_url
        self._base_origin = (base.scheme, base.host, base.port)

    def search(self, keyword: str | None = None, gtin: str | None = None) -> dict:
        """Return raw Browse JSON with item summaries combined across ``next`` pages."""
        self._ensure_enabled()
        normalized_keyword = keyword.strip() if keyword is not None else ""
        normalized_gtin = gtin.strip() if gtin is not None else ""
        if not normalized_keyword and not normalized_gtin:
            raise ValueError("at least one of keyword or gtin must be provided")

        initial_params: dict[str, str | int] = {}
        if normalized_keyword:
            initial_params["q"] = normalized_keyword
        if normalized_gtin:
            initial_params["gtin"] = normalized_gtin

        page = self._authorized_get(self.search_path, params=initial_params)
        combined = dict(page)
        combined_items: list[Any] = []
        seen_next: set[str] = set()
        page_count = 0

        while True:
            page_count += 1
            items = page.get("itemSummaries")
            if isinstance(items, list):
                combined_items.extend(items)

            next_value = page.get("next")
            if next_value is None or next_value == "":
                break
            if page_count >= self.max_pages:
                raise RuntimeError(f"eBay pagination exceeded max_pages={self.max_pages}")

            next_key = str(next_value)
            if next_key in seen_next:
                raise RuntimeError("eBay pagination returned a repeated next value")
            seen_next.add(next_key)
            next_url, next_params = self._resolve_next(next_value, initial_params)
            page = self._authorized_get(next_url, params=next_params)

        if "itemSummaries" in combined or combined_items:
            combined["itemSummaries"] = combined_items
        combined.pop("next", None)
        return combined

    def close(self) -> None:
        """Close the Browse pool and an internally-created authentication pool."""
        super().close()
        if self._owns_auth_client and self.auth_client is not None:
            self.auth_client.close()

    def _authorized_get(
        self,
        url: str | httpx.URL,
        *,
        params: Mapping[str, str | int] | None,
    ) -> dict[str, Any]:
        if self.auth_client is None:
            raise RuntimeError("eBay authentication client is not configured")
        token = self.auth_client.get_token()
        for auth_attempt in range(2):
            try:
                return self.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
                    },
                    params=params,
                )
            except NonRetryableApiError as exc:
                if exc.status_code == 401:
                    if auth_attempt == 0:
                        self.auth_client.invalidate_token(token)
                        token = self.auth_client.get_token(force_refresh=True)
                        continue
                    raise
                if exc.status_code == 403 or self._indicates_access_denied(exc.response):
                    raise EbayAccessDeniedError(exc.response, exc.request_id) from exc
                raise

        raise AssertionError("unreachable authentication retry state")

    def _resolve_next(
        self,
        next_value: object,
        initial_params: Mapping[str, str | int],
    ) -> tuple[str | httpx.URL, Mapping[str, str | int] | None]:
        if isinstance(next_value, int) and not isinstance(next_value, bool):
            return self.search_path, {**initial_params, "offset": next_value}
        if isinstance(next_value, str) and next_value.strip().isdigit():
            return self.search_path, {**initial_params, "offset": int(next_value.strip())}
        if not isinstance(next_value, str) or not next_value.strip():
            raise ValueError("eBay pagination next must be a URL or offset")

        raw_next_url = httpx.URL(next_value.strip())
        if not raw_next_url.path and raw_next_url.query:
            search_url = self._client.base_url.join(httpx.URL(self.search_path))
            next_url = search_url.join(raw_next_url)
        else:
            next_url = self._client.base_url.join(raw_next_url)
        next_origin = (next_url.scheme, next_url.host, next_url.port)
        if next_origin != self._base_origin:
            raise ValueError("eBay pagination next URL must use the configured API origin")
        return next_url, None

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise EbayBrowseDisabledError("eBay Browse integration is disabled")

    @staticmethod
    def _indicates_access_denied(response: httpx.Response) -> bool:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        normalized = str(body).lower()
        return any(
            marker in normalized
            for marker in (
                "access denied",
                "insufficient permission",
                "insufficient privilege",
                "not authorized",
                "not authorised",
                "permission denied",
                "production access",
            )
        )


__all__ = [
    "ITEM_SUMMARY_SEARCH_PATH",
    "EbayAccessDeniedError",
    "EbayBrowseClient",
    "EbayBrowseDisabledError",
]
