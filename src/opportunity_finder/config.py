"""Application settings loaded from environment variables and ``.env``."""

import logging
from decimal import Decimal
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration matching the keys documented in ``.env.example``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_timezone: str = "Asia/Tokyo"
    log_level: str = "INFO"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = "ebay_opportunity"
    mysql_user: str = ""
    mysql_password: str = Field(default="", repr=False)
    mysql_pool_size: int = Field(default=5, ge=0)
    mysql_max_overflow: int = Field(default=5, ge=0)

    ebay_enabled: bool = False
    ebay_environment: str = "production"
    ebay_client_id: str = Field(default="", repr=False)
    ebay_client_secret: str = Field(default="", repr=False)
    ebay_marketplace_id: str = "EBAY_US"

    yahoo_shopping_enabled: bool = False
    yahoo_shopping_app_id: str = Field(default="", repr=False)
    yahoo_client_id: str = Field(default="", repr=False)

    rakuten_enabled: bool = False
    rakuten_application_id: str = Field(default="", repr=False)
    rakuten_access_key: str = Field(default="", repr=False)
    rakuten_affiliate_id: str = Field(default="", repr=False)

    exchange_rate_source: str = "manual"
    default_usd_jpy: Decimal = Decimal("157.0")

    import_dir: Path = Path("/opt/opportunity-finder/data/imports")
    export_dir: Path = Path("/opt/opportunity-finder/output")
    raw_response_dir: Path = Path("/opt/opportunity-finder/data/raw")

    slack_webhook_url: str = Field(default="", repr=False)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize and validate a standard logging level name."""
        normalized = value.strip().upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"invalid log level: {value!r}")
        return normalized
