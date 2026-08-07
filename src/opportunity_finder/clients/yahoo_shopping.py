"""Yahoo! Shopping item-search client."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from opportunity_finder.clients.base import ApiClient
from opportunity_finder.config import Settings

YAHOO_SHOPPING_BASE_URL = "https://shopping.yahooapis.jp"
ITEM_SEARCH_PATH = "/ShoppingWebService/V3/itemSearch"


class YahooShoppingDisabledError(RuntimeError):
    """Raised before a request when Yahoo! Shopping integration is disabled."""


class YahooShoppingClient(ApiClient):
    """Search Yahoo! Shopping by JAN code and then by a text query."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        app_id: str | None = None,
        enabled: bool | None = None,
        base_url: str = YAHOO_SHOPPING_BASE_URL,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_attempts: int = 3,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_jitter: float = 1.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        resolved_settings = settings or Settings()
        app_id_was_injected = app_id is not None
        resolved_app_id = (
            app_id if app_id_was_injected else resolved_settings.yahoo_shopping_app_id
        ).strip()
        resolved_enabled = (
            enabled
            if enabled is not None
            else (True if app_id_was_injected else resolved_settings.yahoo_shopping_enabled)
        )

        if resolved_enabled and not resolved_app_id:
            raise ValueError("YAHOO_SHOPPING_APP_ID must not be empty when Yahoo is enabled")

        self.app_id = resolved_app_id
        self.enabled = resolved_enabled
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

    def search_by_jan(self, jan_code: str) -> dict:
        """Return the unmodified item-search JSON for a JAN code."""
        normalized_jan = jan_code.strip()
        if not normalized_jan or not normalized_jan.isdigit() or len(normalized_jan) not in (8, 13):
            raise ValueError("jan_code must contain exactly 8 or 13 digits")
        return self._search({"jan_code": normalized_jan})

    def search_by_query(self, query: str) -> dict:
        """Return the unmodified item-search JSON for a keyword query."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        return self._search({"query": normalized_query})

    def search(self, jan_code: str | None = None, query: str | None = None) -> dict:
        """Prefer JAN search, falling back to a query when JAN has no hits."""
        normalized_jan = jan_code.strip() if jan_code is not None else ""
        normalized_query = query.strip() if query is not None else ""

        if normalized_jan:
            jan_response = self.search_by_jan(normalized_jan)
            if self._has_hits(jan_response) or not normalized_query:
                return jan_response
        if normalized_query:
            return self.search_by_query(normalized_query)
        raise ValueError("at least one of jan_code or query must be provided")

    def _search(self, search_params: Mapping[str, str]) -> dict:
        self._ensure_enabled()
        # Keep the credential out of ApiClient's logged params. ApiClient removes
        # query strings before logging the URL, while Yahoo still receives appid.
        url = httpx.URL(
            ITEM_SEARCH_PATH,
            params={"appid": self.app_id, **search_params},
        )
        return self.get(url)

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise YahooShoppingDisabledError("Yahoo! Shopping integration is disabled")

    @staticmethod
    def _has_hits(payload: dict) -> bool:
        hits = payload.get("hits")
        return isinstance(hits, list) and bool(hits)


__all__ = ["YahooShoppingClient", "YahooShoppingDisabledError"]
