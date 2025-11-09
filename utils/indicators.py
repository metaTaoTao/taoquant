from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import talib  # type: ignore
except ImportError:  # pragma: no cover
    talib = None


def _ensure_series(data: pd.Series | np.ndarray | "object") -> pd.Series:
    """Convert arbitrary sequence into pandas Series, preserving index if available."""
    if isinstance(data, pd.Series):
        return data
    values = np.asarray(data, dtype="float64")
    index = getattr(data, "index", None)
    if index is not None and len(index) == len(values):
        return pd.Series(values, index=index)
    return pd.Series(values)


def sma(series: pd.Series, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    if window <= 0:
        raise ValueError("Window must be positive.")
    series_obj = _ensure_series(series)
    if talib:
        values = talib.SMA(series_obj.values, timeperiod=window)
        return pd.Series(values, index=series_obj.index)
    return series_obj.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    if period <= 0:
        raise ValueError("Period must be positive.")
    series_obj = _ensure_series(series)
    if talib:
        values = talib.RSI(series_obj.values, timeperiod=period)
        return pd.Series(values, index=series_obj.index)
    delta = series_obj.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain_series = pd.Series(gain, index=series_obj.index).ewm(alpha=1 / period, adjust=False).mean()
    loss_series = pd.Series(loss, index=series_obj.index).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain_series / loss_series
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(0.0)

