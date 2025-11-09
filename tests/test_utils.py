from __future__ import annotations

import pandas as pd

from utils.indicators import rsi, sma
from utils.resample import resample_ohlcv


def test_sma() -> None:
    data = pd.Series([1, 2, 3, 4, 5, 6], dtype="float64")
    result = sma(data, 3)
    assert result.iloc[-1] == 5.0


def test_rsi_bounds() -> None:
    data = pd.Series([1, 2, 3, 4, 3, 2, 1, 2, 3], dtype="float64")
    result = rsi(data, 3)
    assert result.max() <= 100
    assert result.min() >= 0


def test_resample() -> None:
    index = pd.date_range("2023-01-01", periods=4, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [1, 2, 3, 4],
            "high": [2, 3, 4, 5],
            "low": [0.5, 1.5, 2.5, 3.5],
            "close": [1.5, 2.5, 3.5, 4.5],
            "volume": [100, 110, 120, 130],
        },
        index=index,
    )
    resampled = resample_ohlcv(frame, "2h")
    assert len(resampled) == 2
    assert resampled.iloc[0]["open"] == 1

