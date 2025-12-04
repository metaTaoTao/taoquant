"""
Position sizing utilities for risk management.

Pure functions for calculating position sizes based on various methods:
- Fixed percentage
- Fixed risk (risk amount / stop distance)
- Kelly Criterion (future)
- Volatility-based (ATR)

All functions return position sizes as fraction of equity.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def calculate_fixed_size(
    equity: pd.Series,
    percentage: float = 0.5,
) -> pd.Series:
    """
    Calculate fixed position size as percentage of equity.

    Simplest sizing method: always use X% of equity.

    Parameters
    ----------
    equity : pd.Series
        Current equity at each bar
    percentage : float
        Position size as fraction (0.5 = 50%)

    Returns
    -------
    pd.Series
        Position sizes (same index as equity)

    Examples
    --------
    >>> # Always use 50% of equity
    >>> sizes = calculate_fixed_size(equity, percentage=0.5)
    """
    return pd.Series(percentage, index=equity.index)


def calculate_risk_based_size(
    equity: pd.Series,
    stop_distance: pd.Series,
    current_price: pd.Series,
    risk_per_trade: float = 0.01,
    leverage: float = 1.0,
) -> pd.Series:
    """
    Calculate position size based on fixed risk amount.

    This is the recommended method for risk management.

    Formula:
    1. risk_amount = equity * risk_per_trade
    2. position_qty = risk_amount / stop_distance
    3. position_value = position_qty * current_price
    4. size_fraction = position_value / equity
    5. size_fraction *= leverage (if using leverage)

    Parameters
    ----------
    equity : pd.Series
        Current equity at each bar
    stop_distance : pd.Series
        Distance to stop loss (in price units)
        Example: If entry=100, SL=95, then stop_distance=5
    current_price : pd.Series
        Current market price
    risk_per_trade : float
        Risk percentage per trade (0.01 = 1%)
    leverage : float
        Leverage multiplier (default: 1.0 = no leverage)

    Returns
    -------
    pd.Series
        Position sizes as fraction of equity

    Examples
    --------
    >>> # Risk 1% per trade with 3 ATR stop
    >>> stop_distance = data['atr'] * 3
    >>> sizes = calculate_risk_based_size(
    ...     equity=equity,
    ...     stop_distance=stop_distance,
    ...     current_price=data['close'],
    ...     risk_per_trade=0.01,
    ...     leverage=5.0
    ... )

    Notes
    -----
    - This ensures consistent risk across all trades
    - Automatically adjusts position size based on stop distance
    - Wider stops = smaller positions
    - Tighter stops = larger positions
    """
    # Calculate risk amount
    risk_amount = equity * risk_per_trade

    # Calculate position quantity in base asset
    position_qty = risk_amount / stop_distance

    # Convert to position value
    position_value = position_qty * current_price

    # Convert to fraction of equity
    size_fraction = position_value / equity

    # Apply leverage
    size_fraction = size_fraction * leverage

    return size_fraction.fillna(0)


def calculate_atr_based_size(
    equity: pd.Series,
    atr: pd.Series,
    current_price: pd.Series,
    atr_target: float = 100.0,
    leverage: float = 1.0,
) -> pd.Series:
    """
    Calculate position size based on ATR (volatility-adjusted).

    This method adjusts position size inversely to volatility:
    - High volatility (high ATR) → smaller positions
    - Low volatility (low ATR) → larger positions

    Formula:
    1. size_fraction = atr_target / (atr / current_price)
    2. size_fraction *= leverage

    Parameters
    ----------
    equity : pd.Series
        Current equity at each bar
    atr : pd.Series
        ATR values
    current_price : pd.Series
        Current market price
    atr_target : float
        Target ATR in dollars (default: 100)
        This is the ATR you want for a 1x position
    leverage : float
        Leverage multiplier (default: 1.0)

    Returns
    -------
    pd.Series
        Position sizes as fraction of equity

    Examples
    --------
    >>> # Adjust size based on volatility
    >>> atr = calculate_atr(data['high'], data['low'], data['close'])
    >>> sizes = calculate_atr_based_size(
    ...     equity=equity,
    ...     atr=atr,
    ...     current_price=data['close'],
    ...     atr_target=100.0,
    ...     leverage=5.0
    ... )
    """
    # Calculate ATR as percentage of price
    atr_pct = atr / current_price

    # Inverse sizing: target_atr / actual_atr
    size_fraction = atr_target / (atr_pct * 100)

    # Normalize to equity
    size_fraction = size_fraction / 100

    # Apply leverage
    size_fraction = size_fraction * leverage

    return size_fraction.fillna(0)


def apply_position_limits(
    sizes: pd.Series,
    max_size: Optional[float] = None,
    min_size: Optional[float] = None,
) -> pd.Series:
    """
    Apply position size limits.

    Parameters
    ----------
    sizes : pd.Series
        Position sizes to limit
    max_size : Optional[float]
        Maximum position size (e.g., 2.0 = 200% with leverage)
    min_size : Optional[float]
        Minimum position size (e.g., 0.01 = 1%)

    Returns
    -------
    pd.Series
        Limited position sizes

    Examples
    --------
    >>> sizes = calculate_risk_based_size(...)
    >>> limited = apply_position_limits(
    ...     sizes,
    ...     max_size=2.0,  # Max 200% (with leverage)
    ...     min_size=0.01   # Min 1%
    ... )
    """
    limited = sizes.copy()

    if max_size is not None:
        limited = limited.clip(upper=max_size)

    if min_size is not None:
        limited = limited.clip(lower=min_size)

    return limited


def calculate_multi_position_size(
    equity: pd.Series,
    stop_distance: pd.Series,
    current_price: pd.Series,
    risk_per_trade: float = 0.01,
    max_positions: int = 5,
    leverage: float = 1.0,
) -> pd.Series:
    """
    Calculate position size with multi-position support.

    This adjusts the base risk to account for multiple concurrent positions.

    Formula:
    1. adjusted_risk = risk_per_trade / sqrt(max_positions)
    2. Use adjusted_risk for position sizing

    Parameters
    ----------
    equity : pd.Series
        Current equity
    stop_distance : pd.Series
        Stop distance
    current_price : pd.Series
        Current price
    risk_per_trade : float
        Base risk per trade
    max_positions : int
        Maximum concurrent positions
    leverage : float
        Leverage multiplier

    Returns
    -------
    pd.Series
        Position sizes

    Examples
    --------
    >>> # Allow up to 5 concurrent positions
    >>> sizes = calculate_multi_position_size(
    ...     equity=equity,
    ...     stop_distance=data['atr'] * 3,
    ...     current_price=data['close'],
    ...     risk_per_trade=0.01,
    ...     max_positions=5,
    ...     leverage=5.0
    ... )

    Notes
    -----
    - Uses sqrt(N) adjustment to account for diversification
    - If max_positions=5, each position risks 0.01/sqrt(5) ≈ 0.45%
    - Total portfolio risk is still approximately risk_per_trade
    """
    # Adjust risk for multiple positions (diversification)
    adjusted_risk = risk_per_trade / (max_positions ** 0.5)

    return calculate_risk_based_size(
        equity=equity,
        stop_distance=stop_distance,
        current_price=current_price,
        risk_per_trade=adjusted_risk,
        leverage=leverage,
    )
