"""
Volatility regime indicators for grid / market-making strategies.

All functions are pure (no I/O, no side effects).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_atr_pct(atr: pd.Series, close: pd.Series) -> pd.Series:
    """
    ATR as a fraction of price: atr / close.
    """
    atr_f = atr.astype(float)
    close_f = close.astype(float).replace(0.0, np.nan)
    return (atr_f / close_f).replace([np.inf, -np.inf], np.nan)


def rolling_quantile_score(
    series: pd.Series,
    lookback: int = 1440,
    low_q: float = 0.20,
    high_q: float = 0.80,
) -> pd.Series:
    """
    Map a series into a 0..1 score using rolling low/high quantiles.

    score = clip((x - q_low) / (q_high - q_low), 0, 1)
    """
    if lookback <= 10:
        raise ValueError("lookback must be > 10")
    if not (0.0 < low_q < high_q < 1.0):
        raise ValueError("require 0 < low_q < high_q < 1")

    x = series.astype(float)
    ql = x.rolling(lookback, min_periods=lookback).quantile(low_q)
    qh = x.rolling(lookback, min_periods=lookback).quantile(high_q)
    denom = (qh - ql).replace(0.0, np.nan)
    score = ((x - ql) / denom).clip(lower=0.0, upper=1.0)
    return score.fillna(0.0)


