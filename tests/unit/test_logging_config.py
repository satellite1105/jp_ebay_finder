import json
import logging

from opportunity_finder.logging_config import configure_logging, mask_secret


def test_mask_secret_redacts_plain_api_key() -> None:
    api_key = "api-key-that-must-not-appear"

    masked = mask_secret(api_key)

    assert api_key not in masked
    assert masked == "***"


def test_mask_secret_redacts_authorization_header() -> None:
    token = "authorization-token"

    masked = mask_secret(f"Bearer {token}")
    masked_header = mask_secret(f"Authorization: Bearer {token}")

    assert token not in masked
    assert masked == "Bearer ***"
    assert token not in masked_header
    assert masked_header == "Authorization: Bearer ***"


def test_mask_secret_redacts_mysql_url_password() -> None:
    password = "mysql-password"

    masked = mask_secret(f"mysql+pymysql://finder:{password}@db.internal/ebay_opportunity")

    assert password not in masked
    assert masked == "mysql+pymysql://finder:***@db.internal/ebay_opportunity"


def test_configure_logging_installs_json_formatter(capsys) -> None:
    configure_logging("INFO")

    logging.getLogger("test.logging").info(
        "request completed",
        extra={
            "authorization": "Bearer private-token",
            "credentials": {"mysql_password": "private-password"},
            "status": "ok",
        },
    )

    output = capsys.readouterr().err
    payload = json.loads(output)
    assert payload["level"] == "INFO"
    assert payload["message"] == "request completed"
    assert payload["authorization"] == "Bearer ***"
    assert payload["credentials"]["mysql_password"] == "***"
    assert payload["status"] == "ok"
    assert "timestamp" in payload
