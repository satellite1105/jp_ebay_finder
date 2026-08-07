"""Client for the Rakuten Ichiba Item Search API."""

from __future__ import annotations

from typing import Any

from opportunity_finder.clients.base import ApiClient

RAKUTEN_API_BASE_URL = "https://app.rakuten.co.jp"
ICHIBA_ITEM_SEARCH_PATH = "/services/api/IchibaItem/Search/20220601"


class RakutenIchibaClient(ApiClient):
    """Thin synchronous wrapper around Rakuten Ichiba Item Search."""

    def __init__(
        self,
        application_id: str,
        *,
        affiliate_id: str | None = None,
        base_url: str = RAKUTEN_API_BASE_URL,
        **client_options: Any,
    ) -> None:
        normalized_application_id = application_id.strip()
        if not normalized_application_id:
            raise ValueError("application_id must not be empty")

        self.application_id = normalized_application_id
        self.affiliate_id = affiliate_id.strip() if affiliate_id else None
        super().__init__(base_url=base_url, **client_options)

    def search_by_keyword(self, keyword: str, *, page: int = 1) -> dict[str, Any]:
        """Search currently listed items and return Rakuten's raw JSON object."""
        normalized_keyword = keyword.strip()
        if not normalized_keyword:
            raise ValueError("keyword must not be empty")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be an integer greater than or equal to one")

        params: dict[str, str | int] = {
            "applicationId": self.application_id,
            "keyword": normalized_keyword,
            "page": page,
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id

        return self.get(ICHIBA_ITEM_SEARCH_PATH, params=params)


__all__ = ["ICHIBA_ITEM_SEARCH_PATH", "RAKUTEN_API_BASE_URL", "RakutenIchibaClient"]
