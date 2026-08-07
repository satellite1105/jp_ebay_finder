"""OAuth 2.0 client-credentials authentication for eBay REST APIs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from opportunity_finder.clients.base import ApiClient
from opportunity_finder.config import Settings

EBAY_API_BASE_URL = "https://api.ebay.com"
EBAY_OAUTH_TOKEN_PATH = "/identity/v1/oauth2/token"
EBAY_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"


class EbayAuthClient(ApiClient):
    """Acquire and cache an eBay application access token in this process."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        settings: Settings | None = None,
        base_url: str = EBAY_API_BASE_URL,
        token_path: str = EBAY_OAUTH_TOKEN_PATH,
        token_url: str | None = None,
        scope: str = EBAY_OAUTH_SCOPE,
        expiry_skew: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_attempts: int = 3,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_jitter: float = 1.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        resolved_settings = settings or Settings()
        resolved_client_id = (
            client_id if client_id is not None else resolved_settings.ebay_client_id
        ).strip()
        resolved_client_secret = (
            client_secret if client_secret is not None else resolved_settings.ebay_client_secret
        ).strip()
        if not resolved_client_id:
            raise ValueError("EBAY_CLIENT_ID must not be empty")
        if not resolved_client_secret:
            raise ValueError("EBAY_CLIENT_SECRET must not be empty")
        if expiry_skew < 0:
            raise ValueError("expiry_skew must not be negative")

        resolved_token_url = token_url or str(httpx.URL(base_url).join(token_path))
        parsed_token_url = httpx.URL(resolved_token_url)
        if not parsed_token_url.is_absolute_url:
            raise ValueError("token_url must be an absolute URL")

        self.client_id = resolved_client_id
        self._client_secret = resolved_client_secret
        self.token_url = str(parsed_token_url)
        self.scope = scope.strip()
        self.expiry_skew = float(expiry_skew)
        self._clock = clock
        self._access_token: str | None = None
        self._refresh_at = 0.0
        self._token_lock = threading.Lock()

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

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a cached application token, refreshing it when nearly expired."""
        with self._token_lock:
            now = self._clock()
            if not force_refresh and self._access_token and now < self._refresh_at:
                return self._access_token

            payload = self.post(
                self.token_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                auth=httpx.BasicAuth(self.client_id, self._client_secret),
                data={"grant_type": "client_credentials", "scope": self.scope},
            )
            token, expires_in = self._parse_token_response(payload)

            # For short-lived test or sandbox tokens, keep at least half of the
            # advertised lifetime instead of making every call refresh at once.
            safety_margin = min(self.expiry_skew, expires_in / 2)
            self._access_token = token
            self._refresh_at = self._clock() + expires_in - safety_margin
            return token

    def invalidate_token(self, token: str | None = None) -> None:
        """Discard the cache, optionally only when it still contains ``token``."""
        with self._token_lock:
            if token is not None and token != self._access_token:
                return
            self._access_token = None
            self._refresh_at = 0.0

    @staticmethod
    def _parse_token_response(payload: dict[str, Any]) -> tuple[str, float]:
        token = payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("eBay token response is missing access_token")

        expires_value = payload.get("expires_in")
        if type(expires_value) is bool:
            raise ValueError("eBay token response has invalid expires_in")
        try:
            expires_in = float(expires_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("eBay token response has invalid expires_in") from exc
        if expires_in <= 0:
            raise ValueError("eBay token response has invalid expires_in")
        return token.strip(), expires_in


__all__ = [
    "EBAY_API_BASE_URL",
    "EBAY_OAUTH_SCOPE",
    "EBAY_OAUTH_TOKEN_PATH",
    "EbayAuthClient",
]
