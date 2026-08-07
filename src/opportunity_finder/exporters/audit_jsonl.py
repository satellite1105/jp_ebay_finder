"""Export audit log records as newline-delimited JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

AUDIT_COLUMNS = (
    "id",
    "run_id",
    "entity_type",
    "entity_id",
    "action",
    "actor",
    "before_value",
    "after_value",
    "reason",
    "created_at",
)


def export_audit_jsonl(records: Iterable[Mapping[str, Any] | object], path: str | Path) -> None:
    """Write each audit record as exactly one valid JSON object per line."""
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="\n") as jsonl_file:
        for record in records:
            payload = {column: _record_value(record, column) for column in AUDIT_COLUMNS}
            json.dump(
                payload,
                jsonl_file,
                ensure_ascii=False,
                separators=(",", ":"),
                default=_json_default,
            )
            jsonl_file.write("\n")


def _record_value(record: Mapping[str, Any] | object, column: str) -> Any:
    if isinstance(record, Mapping):
        return record[column]
    return getattr(record, column)


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
