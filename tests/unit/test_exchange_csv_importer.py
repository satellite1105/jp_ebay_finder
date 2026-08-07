from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from opportunity_finder.importers.exchange_csv import (
    ExchangeRateInput,
    import_exchange_csv,
)


def _write_csv(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    path.write_text(content, encoding=encoding)
    return path


def test_valid_csv_is_parsed_into_validated_models(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        "base_currency,quote_currency,rate,effective_at\n"
        "USD,JPY,150.12345678,2026-08-07T12:30:45\n"
        "EUR,JPY,172.5,2026-08-07T13:00:00+09:00\n",
    )

    result = import_exchange_csv(path)

    assert result.valid_rows == [
        ExchangeRateInput(
            base_currency="USD",
            quote_currency="JPY",
            rate=Decimal("150.12345678"),
            effective_at=datetime.fromisoformat("2026-08-07T12:30:45"),
        ),
        ExchangeRateInput(
            base_currency="EUR",
            quote_currency="JPY",
            rate=Decimal("172.5"),
            effective_at=datetime.fromisoformat("2026-08-07T13:00:00+09:00"),
        ),
    ]
    assert result.rows_total == 2
    assert result.quarantined_rows == []


@pytest.mark.parametrize("invalid_rate", ["0", "-0.01"])
def test_non_positive_rate_is_quarantined_without_blocking_valid_rows(
    tmp_path: Path, invalid_rate: str
) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        "base_currency,quote_currency,rate,effective_at\n"
        f"USD,JPY,{invalid_rate},2026-08-07T12:00:00\n"
        "EUR,JPY,172.5,2026-08-07T13:00:00\n",
    )

    result = import_exchange_csv(path)

    assert [row.base_currency for row in result.valid_rows] == ["EUR"]
    assert len(result.quarantined_rows) == 1
    assert result.quarantined_rows[0].row["rate"] == invalid_rate
    assert "greater than 0" in result.quarantined_rows[0].error


def test_currency_code_with_wrong_length_is_quarantined(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        "base_currency,quote_currency,rate,effective_at\n"
        "US,JPY,150,2026-08-07T12:00:00\n"
        "EUR,JPY,172.5,2026-08-07T13:00:00\n",
    )

    result = import_exchange_csv(path)

    assert [row.base_currency for row in result.valid_rows] == ["EUR"]
    assert len(result.quarantined_rows) == 1
    assert result.quarantined_rows[0].row["base_currency"] == "US"
    assert "at least 3 characters" in result.quarantined_rows[0].error


def test_missing_required_column_raises_file_level_error(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        "base_currency,quote_currency,rate\nUSD,JPY,150\n",
    )

    with pytest.raises(ValueError, match=r"Missing required columns: effective_at"):
        import_exchange_csv(path)


def test_utf8_bom_and_file_sha256(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "exchange_rates.csv",
        "base_currency,quote_currency,rate,effective_at\nUSD,JPY,150,2026-08-07T12:00:00\n",
        encoding="utf-8-sig",
    )

    result = import_exchange_csv(path)

    assert [row.base_currency for row in result.valid_rows] == ["USD"]
    assert result.quarantined_rows == []
    assert result.file_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(result.file_sha256) == 64
