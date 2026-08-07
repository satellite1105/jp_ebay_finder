from decimal import Decimal
from pathlib import Path

from opportunity_finder.config import Settings

ENV_KEYS = (
    "APP_ENV",
    "APP_TIMEZONE",
    "LOG_LEVEL",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_POOL_SIZE",
    "MYSQL_MAX_OVERFLOW",
    "EBAY_ENABLED",
    "EBAY_ENVIRONMENT",
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_MARKETPLACE_ID",
    "YAHOO_SHOPPING_ENABLED",
    "YAHOO_SHOPPING_APP_ID",
    "YAHOO_CLIENT_ID",
    "RAKUTEN_ENABLED",
    "RAKUTEN_APPLICATION_ID",
    "RAKUTEN_ACCESS_KEY",
    "RAKUTEN_AFFILIATE_ID",
    "EXCHANGE_RATE_SOURCE",
    "DEFAULT_USD_JPY",
    "IMPORT_DIR",
    "EXPORT_DIR",
    "RAW_RESPONSE_DIR",
    "SLACK_WEBHOOK_URL",
)


def test_settings_reads_environment_variables(monkeypatch) -> None:
    values = {
        "APP_ENV": "test",
        "APP_TIMEZONE": "UTC",
        "LOG_LEVEL": "debug",
        "MYSQL_HOST": "db.internal",
        "MYSQL_PORT": "3307",
        "MYSQL_DATABASE": "finder_test",
        "MYSQL_USER": "finder",
        "MYSQL_PASSWORD": "db-secret",
        "MYSQL_POOL_SIZE": "8",
        "MYSQL_MAX_OVERFLOW": "12",
        "EBAY_ENABLED": "true",
        "EBAY_ENVIRONMENT": "sandbox",
        "EBAY_CLIENT_ID": "ebay-client-id",
        "EBAY_CLIENT_SECRET": "ebay-client-secret",
        "EBAY_MARKETPLACE_ID": "EBAY_GB",
        "YAHOO_SHOPPING_ENABLED": "true",
        "YAHOO_SHOPPING_APP_ID": "yahoo-app-id",
        "YAHOO_CLIENT_ID": "yahoo-client-id",
        "RAKUTEN_ENABLED": "true",
        "RAKUTEN_APPLICATION_ID": "rakuten-application-id",
        "RAKUTEN_ACCESS_KEY": "rakuten-access-key",
        "RAKUTEN_AFFILIATE_ID": "rakuten-affiliate-id",
        "EXCHANGE_RATE_SOURCE": "api",
        "DEFAULT_USD_JPY": "150.25",
        "IMPORT_DIR": "/tmp/finder/imports",
        "EXPORT_DIR": "/tmp/finder/exports",
        "RAW_RESPONSE_DIR": "/tmp/finder/raw",
        "SLACK_WEBHOOK_URL": "https://hooks.example.invalid/secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.app_timezone == "UTC"
    assert settings.log_level == "DEBUG"
    assert settings.mysql_host == "db.internal"
    assert settings.mysql_port == 3307
    assert settings.mysql_database == "finder_test"
    assert settings.mysql_user == "finder"
    assert settings.mysql_password == "db-secret"
    assert settings.mysql_pool_size == 8
    assert settings.mysql_max_overflow == 12
    assert settings.ebay_enabled is True
    assert settings.ebay_environment == "sandbox"
    assert settings.ebay_client_id == "ebay-client-id"
    assert settings.ebay_client_secret == "ebay-client-secret"
    assert settings.ebay_marketplace_id == "EBAY_GB"
    assert settings.yahoo_shopping_enabled is True
    assert settings.yahoo_shopping_app_id == "yahoo-app-id"
    assert settings.yahoo_client_id == "yahoo-client-id"
    assert settings.rakuten_enabled is True
    assert settings.rakuten_application_id == "rakuten-application-id"
    assert settings.rakuten_access_key == "rakuten-access-key"
    assert settings.rakuten_affiliate_id == "rakuten-affiliate-id"
    assert settings.exchange_rate_source == "api"
    assert settings.default_usd_jpy == Decimal("150.25")
    assert settings.import_dir == Path("/tmp/finder/imports")
    assert settings.export_dir == Path("/tmp/finder/exports")
    assert settings.raw_response_dir == Path("/tmp/finder/raw")
    assert settings.slack_webhook_url == "https://hooks.example.invalid/secret"
    assert "db-secret" not in repr(settings)
    assert "ebay-client-secret" not in repr(settings)


def test_settings_uses_documented_defaults(monkeypatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.app_timezone == "Asia/Tokyo"
    assert settings.log_level == "INFO"
    assert settings.mysql_host == "127.0.0.1"
    assert settings.mysql_port == 3306
    assert settings.mysql_database == "ebay_opportunity"
    assert settings.mysql_user == ""
    assert settings.mysql_password == ""
    assert settings.mysql_pool_size == 5
    assert settings.mysql_max_overflow == 5
    assert settings.ebay_enabled is False
    assert settings.yahoo_shopping_enabled is False
    assert settings.rakuten_enabled is False
    assert settings.default_usd_jpy == Decimal("157.0")
