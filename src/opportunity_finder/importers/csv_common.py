"""Utilities shared by CSV importers and exporters."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


def compute_file_sha256(path: str | Path) -> str:
    """Return the hexadecimal SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class QuarantinedRow:
    """A rejected CSV row and the error that caused its rejection."""

    row: dict[str, object]
    error: str


@dataclass(slots=True)
class QuarantineCollector:
    """Collect invalid rows while allowing an importer loop to continue."""

    rows: list[QuarantinedRow] = field(default_factory=list)

    def quarantine_row(self, row: Mapping[str, object], error: Exception | str) -> None:
        """Store an isolated copy of an invalid row and its error."""
        self.rows.append(QuarantinedRow(row=dict(row), error=str(error)))


def sanitize_formula_cell(value: str) -> str:
    """Neutralize values that spreadsheet programs could execute as formulas."""
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
