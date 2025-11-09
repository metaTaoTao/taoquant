from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from data.schemas import COLUMNS_OHLCV, validate_columns


def load_csv_ohlcv(
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    base_dir: Path = Path("data/raw"),
) -> pd.DataFrame:
    """Load OHLCV data from CSV file into standardized dataframe."""
    safe_symbol = symbol.replace("/", "_").lower()
    filename = f"{safe_symbol}_{timeframe}.csv"
    path = base_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found at {path}")

    df = pd.read_csv(path, parse_dates=True, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    normalized_cols = [col.lower() for col in df.columns]
    if not validate_columns(normalized_cols):
        raise ValueError(f"CSV schema mismatch for {path}. Expected {COLUMNS_OHLCV}.")
    df.columns = COLUMNS_OHLCV

    if start:
        df = df[df.index >= pd.Timestamp(start, tz=timezone.utc)]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz=timezone.utc)]

    return df.sort_index()

