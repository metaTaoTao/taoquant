from __future__ import annotations

from typing import Literal

import pandas as pd

from indicators.sr_volume_boxes import SupportResistanceVolumeBoxesIndicator


def _average_true_range(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Compute Average True Range using a simple moving average."""
    high_low = high - low
    high_close = (high - close.shift(1)).abs()
    low_close = (low - close.shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr


def build_sr_range(
    df15: pd.DataFrame,
    lookback_period: int = 20,
    atr_len: int = 200,
    pivot_source: Literal["close", "high", "low"] = "close",
) -> pd.DataFrame:
    """Build confirmed support/resistance range on 15m data.

    Parameters
    ----------
    df15 : pd.DataFrame
        Resampled 15-minute OHLCV dataframe (DatetimeIndex).
    lookback_period : int, optional
        Pivot confirmation window, default 20.
    atr_len : int, optional
        ATR length used by the indicator, default 200.
    pivot_source : {"close","high","low"}, optional
        Price column used to compute pivots, default "close".

    Returns
    -------
    pd.DataFrame
        Dataframe aligned with df15 containing support/resistance and metadata.
    """

    if df15.index.duplicated().any():
        raise ValueError("df15 index must not contain duplicates")
    if not isinstance(df15.index, pd.DatetimeIndex):
        raise TypeError("df15 must have a DatetimeIndex")

    data = df15.copy()
    data.sort_index(inplace=True)
    data.columns = [str(col).lower() for col in data.columns]

    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(data.columns)
    if missing:
        raise ValueError(f"Input dataframe is missing required columns: {sorted(missing)}")

    indicator = SupportResistanceVolumeBoxesIndicator(
        lookback_period=lookback_period,
        atr_len=atr_len,
        pivot_source=pivot_source,
    )
    
    # 🔴 BREAKPOINT 1: Inspect raw data before indicator calculation
    # Set breakpoint here to check: data.head(), data.tail(), data.shape
    out = indicator.calculate(data)
    
    # 🔴 BREAKPOINT 2: Inspect indicator output (pivot points)
    # Set breakpoint here to check: out[['pivot_high', 'pivot_low']].dropna()
    # Compare pivot_high/pivot_low values with TradingView pivot(20,20)
    
    out["confirmed_low"] = out["pivot_low"].shift(lookback_period)
    out["confirmed_high"] = out["pivot_high"].shift(lookback_period)
    
    # 🔴 BREAKPOINT 3: Inspect confirmed pivots (after +20 bar shift)
    # Set breakpoint here to check: out[['pivot_low', 'confirmed_low', 'pivot_high', 'confirmed_high']].head(50)
    # Verify: confirmed_low at bar i should equal pivot_low at bar (i-20)
    
    out["support"] = out["confirmed_low"].ffill()
    out["resistance"] = out["confirmed_high"].ffill()
    
    # 🔴 BREAKPOINT 4: Inspect final S/R levels
    # Set breakpoint here to check: out[['support', 'resistance', 'range_valid']].dropna()
    # Compare support/resistance with TradingView after +20 bar confirmation
    out["range_valid"] = (out["support"] < out["resistance"]) & out["support"].notna() & out["resistance"].notna()
    out["midline"] = (out["support"] + out["resistance"]) / 2.0

    # Calculate ATR short (50) for micro-oscillation cooldown
    out["atr_short"] = _average_true_range(out["high"], out["low"], out["close"], period=50)

    columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "atr",
        "atr_short",
        "pivot_high",
        "pivot_low",
        "support",
        "resistance",
        "range_valid",
        "midline",
    ]

    return out[columns]
