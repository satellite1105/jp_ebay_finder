"""Client for the Rakuten Product Search API."""

from __future__ import annotations

import re
from typing import Any

from opportunity_finder.clients.base import ApiClient

RAKUTEN_API_BASE_URL = "https://app.rakuten.co.jp"
PRODUCT_SEARCH_PATH = "/services/api/Product/Search/20170426"
_JAN_PATTERN = re.compile(r"^\d{8}(?:\d{5})?$")


class RakutenProductClient(ApiClient):
    """Thin synchronous wrapper around Rakuten Product Search."""

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

    def search_by_jan(self, jan_code: str, *, page: int = 1) -> dict[str, Any]:
        """Search by an eight- or thirteen-digit JAN and return raw JSON."""
        normalized_jan = jan_code.strip()
        if not _JAN_PATTERN.fullmatch(normalized_jan):
            raise ValueError("jan_code must contain exactly 8 or 13 digits")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be an integer greater than or equal to one")

        params: dict[str, str | int] = {
            "applicationId": self.application_id,
            "keyword": normalized_jan,
            "page": page,
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id

        return self.get(PRODUCT_SEARCH_PATH, params=params)


__all__ = ["PRODUCT_SEARCH_PATH", "RAKUTEN_API_BASE_URL", "RakutenProductClient"]
