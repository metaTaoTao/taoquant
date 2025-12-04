"""
Volatility indicators.

Pure functions for calculating volatility-based indicators:
- ATR (Average True Range)
- Bollinger Bands (future)
- Standard Deviation (future)
"""

from __future__ import annotations

import pandas as pd


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Calculate Average True Range using RMA (Wilder's Smoothing).

    This matches TradingView's ta.atr() implementation:
    - ATR = RMA(True Range, period)
    - RMA is an exponentially weighted moving average with alpha = 1/period

    Parameters
    ----------
    high : pd.Series
        High prices
    low : pd.Series
        Low prices
    close : pd.Series
        Close prices
    period : int
        ATR period (default: 14)

    Returns
    -------
    pd.Series
        ATR values (same index as input)

    Examples
    --------
    >>> atr = calculate_atr(data['high'], data['low'], data['close'], period=14)
    >>> data['atr'] = atr

    Notes
    -----
    True Range is the maximum of:
    - high - low
    - abs(high - previous_close)
    - abs(low - previous_close)

    RMA formula:
    - First value: SMA of first 'period' values
    - Subsequent values: (previous_RMA * (period-1) + current_TR) / period
    - Equivalent to ewm(alpha=1/period, adjust=False)

    References
    ----------
    - Wilder, J. Welles (1978). New Concepts in Technical Trading Systems
    - TradingView ta.atr(): https://www.tradingview.com/pine-script-reference/v5/#fun_ta{dot}atr
    """
    # Calculate True Range components
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    # True Range = max of three components
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Apply RMA (Wilder's smoothing)
    # ewm with adjust=False matches TV's RMA
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    return atr


def calculate_atr_bands(
    close: pd.Series,
    atr: pd.Series,
    multiplier: float = 2.0,
) -> tuple[pd.Series, pd.Series]:
    """
    Calculate ATR-based bands around price.

    Parameters
    ----------
    close : pd.Series
        Close prices
    atr : pd.Series
        ATR values
    multiplier : float
        ATR multiplier for band width

    Returns
    -------
    tuple[pd.Series, pd.Series]
        (upper_band, lower_band)

    Examples
    --------
    >>> atr = calculate_atr(data['high'], data['low'], data['close'])
    >>> upper, lower = calculate_atr_bands(data['close'], atr, multiplier=2.0)
    """
    upper_band = close + (atr * multiplier)
    lower_band = close - (atr * multiplier)

    return upper_band, lower_band
