"""
Regime / factor indicators for grid strategies.

All functions are pure (no I/O, no side effects).
They are designed to be pre-computed on OHLCV data and fed into strategies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    """
    Exponential moving average (EMA).

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int
        EMA period.

    Returns
    -------
    pd.Series
        EMA series.
    """
    if period <= 0:
        raise ValueError("period must be > 0")
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """
    Rolling z-score: (x - mean) / std.

    Parameters
    ----------
    series : pd.Series
        Input series.
    window : int
        Rolling window length.

    Returns
    -------
    pd.Series
        Z-score series (NaN until window is available).
    """
    if window <= 1:
        raise ValueError("window must be > 1")
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    z = (series - mean) / std.replace(0.0, np.nan)
    return z


def calculate_ema_slope(ema: pd.Series, lookback: int) -> pd.Series:
    """
    EMA slope proxy using percentage change over a lookback.

    Parameters
    ----------
    ema : pd.Series
        EMA series.
    lookback : int
        Lookback bars to compute slope.

    Returns
    -------
    pd.Series
        Slope (fractional change) series.
    """
    if lookback <= 0:
        raise ValueError("lookback must be > 0")
    return ema.pct_change(periods=lookback)


def trend_score_from_slope(slope: pd.Series, slope_ref: float = 0.001) -> pd.Series:
    """
    Map slope into a bounded trend score in [-1, 1] using tanh normalization.

    Parameters
    ----------
    slope : pd.Series
        Slope series (fractional change).
    slope_ref : float
        Reference slope magnitude (controls sensitivity).

    Returns
    -------
    pd.Series
        Trend score in [-1, 1].
    """
    if slope_ref <= 0:
        raise ValueError("slope_ref must be > 0")
    return np.tanh(slope / slope_ref)


