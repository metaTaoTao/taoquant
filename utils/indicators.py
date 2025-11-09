from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

try:
    import talib  # type: ignore
except ImportError:  # pragma: no cover
    talib = None


def sma(series: pd.Series, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    if window <= 0:
        raise ValueError("Window must be positive.")
    if talib:
        return pd.Series(talib.SMA(series.values, timeperiod=window), index=series.index)
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    if period <= 0:
        raise ValueError("Period must be positive.")
    if talib:
        return pd.Series(talib.RSI(series.values, timeperiod=period), index=series.index)
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain_series = pd.Series(gain, index=series.index).ewm(alpha=1 / period, adjust=False).mean()
    loss_series = pd.Series(loss, index=series.index).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain_series / loss_series
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(0.0)

