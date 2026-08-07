"""Structured JSON logging with redaction of sensitive values."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_MASK = "***"

_AUTH_VALUE_PATTERN = re.compile(
    r"^(?P<scheme>Bearer|Basic|Digest|Token)\s+.+$",
    flags=re.IGNORECASE,
)
_AUTH_IN_TEXT_PATTERN = re.compile(
    r"(?P<prefix>\bauthorization\s*[:=]\s*)"
    r"(?P<scheme>Bearer|Basic|Digest|Token)\s+[^\s,;]+",
    flags=re.IGNORECASE,
)
_URL_PASSWORD_PATTERN = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s@]+(?=@)",
    flags=re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<prefix>\b(?:api[_-]?key|app[_-]?id|access[_-]?key|affiliate[_-]?id|"
    r"application[_-]?id|client[_-]?(?:id|secret)|mysql[_-]?password|password|secret|"
    r"token|webhook[_-]?url)\b\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    flags=re.IGNORECASE,
)

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
    "webhook_url",
)

_CONTEXT_FIELDS = (
    "run_id",
    "command",
    "source",
    "product_id",
    "query_id",
    "elapsed_ms",
    "status",
    "error_type",
    "retry_count",
    "rows_read",
    "rows_written",
)

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        *logging.makeLogRecord({}).__dict__,
        "asctime",
        "message",
    }
)
_RESERVED_PAYLOAD_FIELDS = frozenset({"timestamp", "level", "logger", "message", "exception"})


def _masked_assignment(match: re.Match[str]) -> str:
    value = match.group("value")
    quote = value[0] if value and value[0] in {"'", '"'} else ""
    return f"{match.group('prefix')}{quote}{_MASK}{quote}"


def _sanitize_text(value: str) -> str:
    sanitized = _URL_PASSWORD_PATTERN.sub(rf"\g<prefix>{_MASK}", value)
    sanitized = _AUTH_IN_TEXT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{match.group('scheme')} {_MASK}",
        sanitized,
    )
    return _SENSITIVE_ASSIGNMENT_PATTERN.sub(_masked_assignment, sanitized)


def mask_secret(value: str) -> str:
    """Mask a secret while retaining useful authorization or URL structure."""
    if not value:
        return value

    authorization = _AUTH_VALUE_PATTERN.fullmatch(value.strip())
    if authorization:
        return f"{authorization.group('scheme')} {_MASK}"

    sanitized = _sanitize_text(value)
    if sanitized != value:
        return sanitized
    return _MASK


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any, *, key: object | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return mask_secret(str(value))
    if isinstance(value, Mapping):
        return {item_key: _sanitize(item, key=item_key) for item_key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _sanitize_text(record.getMessage()),
            **dict.fromkeys(_CONTEXT_FIELDS),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and key not in _RESERVED_PAYLOAD_FIELDS:
                payload[key] = _sanitize(value, key=key)

        if record.exc_info:
            payload["exception"] = _sanitize_text(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Configure the root logger to emit redacted structured JSON to stderr."""
    normalized = level.strip().upper()
    level_mapping = logging.getLevelNamesMapping()
    if normalized not in level_mapping:
        raise ValueError(f"invalid log level: {level!r}")

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level_mapping[normalized], handlers=[handler], force=True)
    logging.captureWarnings(True)


__all__ = ["JsonFormatter", "configure_logging", "mask_secret"]
