from __future__ import annotations

from typing import Final, List

COLUMNS_OHLCV: Final[List[str]] = ["open", "high", "low", "close", "volume"]


def validate_columns(columns: List[str]) -> bool:
    """Validate that provided columns match the OHLCV schema."""
    return [col.lower() for col in columns] == COLUMNS_OHLCV


