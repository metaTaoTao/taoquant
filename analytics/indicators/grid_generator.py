"""
Grid Level Generator (Pure Functions).

This module implements grid level generation logic for TaoGrid strategy:
1. ATR-based spacing calculation
2. Grid level generation with volatility cushion
3. Mid-shift calculation (for DGT in Sprint 2)

All functions are PURE FUNCTIONS:
- Same inputs → same outputs
- No side effects
- No state mutations

Design Principles (from CLAUDE.md):
1. Pure functions only
2. Type hints everywhere
3. Comprehensive docstrings
4. No data fetching
5. No logging

References:
    - Strategy Doc Section 3.3: Grid spacing formula
    - Strategy Doc Section 3.2: Volatility cushion
    - Strategy Doc Section 4.1: DGT (mid shift)
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd


def calculate_grid_spacing(
    atr: pd.Series,
    min_return: float = 0.005,
    maker_fee: float = 0.0002,
    slippage: float = 0.0,  # Changed default to 0.0 for limit orders
    volatility_k: float = 0.6,
    use_limit_orders: bool = True,  # New parameter: whether using limit orders
) -> pd.Series:
    """
    Calculate grid spacing percentage based on ATR.

    Formula (from strategy doc Section 3.3):
        gap_% = min_return + 2×maker_fee + 2×slippage + k × volatility

    Where:
        - min_return: minimum NET return per grid AFTER all costs (default 0.5%)
          This is the profit you want AFTER paying fees and slippage
        - maker_fee: exchange maker fee per side (default 0.02%, so 2× = 0.04% total)
        - slippage: slippage per side (default 0.0% for limit orders)
          NOTE: For limit orders, slippage should be 0 as orders execute at limit price
          Only use slippage > 0 for market orders
        - volatility: ATR-based volatility measure
        - k: volatility safety factor (0.4-1.0)
        - use_limit_orders: If True, forces slippage = 0 (default True)

    IMPORTANT: 
        - min_return is NET return (after all costs)
        - Grid spacing = min_return + trading costs
        - Trading requires TWO-WAY costs:
          - Buy: maker_fee + slippage
          - Sell: maker_fee + slippage
          - Total: 2×maker_fee + 2×slippage

    Logic:
        - Higher ATR → wider spacing (avoid frequent trading in volatile markets)
        - Lower ATR → tighter spacing (capture more mean-reversion)
        - Grid spacing ensures: (spacing - costs) >= min_return

    Parameters
    ----------
    atr : pd.Series
        ATR (Average True Range) series
    min_return : float, optional
        Minimum NET return per grid (AFTER all costs), by default 0.005 (0.5%)
        This is the profit you want after paying fees and slippage
    maker_fee : float, optional
        Maker fee rate PER SIDE, by default 0.001 (0.1%)
        Total fee for round trip = 2 × maker_fee
    slippage : float, optional
        Slippage rate PER SIDE, by default 0.0005 (0.05%)
        Total slippage for round trip = 2 × slippage
    volatility_k : float, optional
        Volatility safety factor, by default 0.6 (range: 0.4-1.0)

    Returns
    -------
    pd.Series
        Grid spacing as percentage (e.g., 0.01 = 1%)
        Index matches input ATR series

    Examples
    --------
    >>> import pandas as pd
    >>> atr = pd.Series([100, 150, 200], index=pd.date_range('2025-01-01', periods=3))
    >>> spacing = calculate_grid_spacing(atr, min_return=0.005, maker_fee=0.001, slippage=0.0005, volatility_k=0.6)
    >>> spacing
    # Result depends on ATR normalization

    Notes
    -----
    - ATR is normalized by its rolling mean to get relative volatility
    - Spacing is dynamic: adapts to market conditions
    - In low volatility, spacing can be as low as min_return + 2×maker_fee + 2×slippage
    - In high volatility, spacing expands to avoid overtrading
    - Grid spacing ensures: (spacing - costs) >= min_return

    Raises
    ------
    ValueError
        If parameters are invalid (negative values, min_return too low, etc.)
    """
    # ========== Parameter Validation ==========
    if min_return <= 0:
        raise ValueError(f"min_return must be > 0, got {min_return}")

    if maker_fee < 0:
        raise ValueError(f"maker_fee cannot be negative, got {maker_fee}")

    if slippage < 0:
        raise ValueError(f"slippage cannot be negative, got {slippage}")

    if volatility_k < 0 or volatility_k > 2.0:
        raise ValueError(f"volatility_k should be in [0, 2.0], got {volatility_k}")

    # For limit orders, slippage should be 0
    if use_limit_orders and slippage > 0:
        import warnings
        warnings.warn(
            f"use_limit_orders=True but slippage={slippage} > 0. "
            f"Limit orders execute at limit price with no slippage. "
            f"Forcing slippage=0."
        )
        slippage = 0.0

    # ========== Calculate Trading Costs ==========
    trading_costs = (2 * maker_fee) + (2 * slippage)  # TWO-WAY costs

    # Ensure min_return can cover trading costs
    if min_return < trading_costs:
        import warnings
        warnings.warn(
            f"min_return ({min_return:.2%}) < trading_costs ({trading_costs:.2%}). "
            f"Net profit per trade will be negative! "
            f"Recommended: min_return >= {trading_costs:.2%}"
        )

    # ========== Normalize ATR ==========
    # Normalize ATR by its rolling mean (20-period)
    # This gives relative volatility measure
    atr_rolling_mean = atr.rolling(window=20, min_periods=1).mean()
    atr_pct = atr / atr_rolling_mean

    # ========== Calculate Spacing ==========
    # IMPROVED FORMULA (Multiplicative): spacing = base × (1 + k × volatility)
    # This prevents volatility from dominating the spacing calculation
    #
    # Old (additive): spacing = base + k × (atr_pct - 1.0)
    #   Problem: When atr_pct = 9, adjustment = 0.6 × 8 = 4.8 (480%!) → dominates
    #
    # New (multiplicative): spacing = base × (1 + k × max(0, atr_pct - 1.0))
    #   Effect: When atr_pct = 9, spacing = base × (1 + 0.2 × 8) = base × 2.6 → controlled
    #
    # min_return is NET return (after all costs)
    # So grid spacing = min_return + trading costs (base), then scaled by volatility
    base_spacing = min_return + trading_costs  # Gross spacing needed for min_return net profit

    # Volatility multiplier (only expand spacing, never reduce below base)
    # Use max(0, ...) to ensure we only expand when ATR > mean, never contract
    volatility_multiplier = 1.0 + volatility_k * np.maximum(0, atr_pct - 1.0)

    # Apply multiplicative adjustment
    spacing_pct = base_spacing * volatility_multiplier

    # ========== Lower Bound Protection ==========
    # Ensure spacing is at least base_spacing (to guarantee min_return net profit)
    # With multiplicative formula and max(0, ...), this is automatically satisfied
    # but we keep it as a safety check
    spacing_pct = spacing_pct.clip(lower=base_spacing)

    # ========== Upper Bound Protection ==========
    # Prevent spacing from becoming too large (reduces turnover excessively)
    # Note: For ranging strategies, use volatility_k=0 to disable ATR adjustment entirely
    MAX_SPACING = 0.02  # 2% maximum spacing (reasonable upper bound)
    spacing_pct = spacing_pct.clip(upper=MAX_SPACING)

    return spacing_pct


def generate_grid_levels(
    mid_price: float,
    support: float,
    resistance: float,
    cushion: float,
    spacing_pct: float,
    layers_buy: int,
    layers_sell: int,
) -> Dict[str, np.ndarray | float]:
    """
    Generate grid levels from mid price with volatility cushion.

    Logic (from strategy doc Section 3.2):
    1. Calculate effective boundaries:
       - eff_support = support - cushion
       - eff_resistance = resistance + cushion
    2. Generate buy levels: from mid down to eff_support
    3. Generate sell levels: from mid up to eff_resistance
    4. Use geometric spacing (multiplicative)

    The volatility cushion prevents premature stop-out on false breakouts.

    Parameters
    ----------
    mid_price : float
        Mid price (can be static or dynamic with DGT)
        In MVP: mid = (support + resistance) / 2
        In Sprint 2: mid can shift based on price action
    support : float
        Support level (lower bound)
    resistance : float
        Resistance level (upper bound)
    cushion : float
        Volatility cushion (typically ATR × multiplier)
        Example: ATR(14) × 0.8
    spacing_pct : float
        Grid spacing as percentage (from calculate_grid_spacing)
        Example: 0.01 = 1%
    layers_buy : int
        Number of buy grid layers
    layers_sell : int
        Number of sell grid layers

    Returns
    -------
    Dict[str, np.ndarray | float]
        Dictionary containing:
        - 'buy_levels': array of buy prices (descending from mid)
        - 'sell_levels': array of sell prices (ascending from mid)
        - 'mid': mid price used
        - 'eff_support': effective support with cushion
        - 'eff_resistance': effective resistance with cushion

    Examples
    --------
    >>> grid = generate_grid_levels(
    ...     mid_price=100000.0,
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     cushion=500.0,  # ATR cushion
    ...     spacing_pct=0.01,  # 1%
    ...     layers_buy=5,
    ...     layers_sell=5
    ... )
    >>> grid['buy_levels']
    array([99000., 98010., 97029.9, 96059.7, 95099.1])
    >>> grid['sell_levels']
    array([101000., 102010., 103030.1, 104060.4, 105100.8])

    Notes
    -----
    - Buy levels are BELOW mid (where we want to buy)
    - Sell levels are ABOVE mid (where we want to sell)
    - Geometric spacing: price[i+1] = price[i] × (1 ± spacing_pct)
    - Levels are clipped to effective boundaries
    - If insufficient space, fewer layers are generated
    """
    # Calculate effective boundaries with cushion
    eff_support = support - cushion
    eff_resistance = resistance + cushion

    # Validate mid is within S/R range
    if mid_price < support or mid_price > resistance:
        # Allow mid outside S/R if using DGT
        # Just clip to boundaries
        mid_price = np.clip(mid_price, support, resistance)

    # Generate buy levels (from mid down to support)
    buy_levels = []
    price = mid_price
    for i in range(layers_buy):
        # Move down by spacing_pct
        price = price / (1 + spacing_pct)

        # Check if within effective support
        if price >= eff_support:
            buy_levels.append(price)
        else:
            # Stop if beyond effective support
            break

    # Generate sell levels from buy levels (for 1x spacing pairing)
    # Each sell_level[i] = buy_level[i] × (1 + spacing_pct)
    # This creates 1x spacing pairing: buy[i] -> sell[i] = 1 × spacing
    # 
    # Note: layers_sell parameter is now redundant since sell_levels are generated
    # from buy_levels. We keep it for backward compatibility but ignore it.
    sell_levels = []
    for buy_price in buy_levels:
        sell_price = buy_price * (1 + spacing_pct)
        # Check if within effective resistance
        if sell_price <= eff_resistance:
            sell_levels.append(sell_price)
        else:
            # Stop if beyond effective resistance
            break

    return {
        "buy_levels": np.array(buy_levels),
        "sell_levels": np.array(sell_levels),
        "mid": mid_price,
        "eff_support": eff_support,
        "eff_resistance": eff_resistance,
    }


def calculate_mid_shift(
    data: pd.DataFrame,
    current_mid: float,
    support: float,
    resistance: float,
    threshold_bars: int = 20,
) -> float:
    """
    Calculate new mid price based on price distribution (DGT - Sprint 2).

    Logic (from strategy doc Section 4.1):
    - If price stays in upper half for N bars → shift mid up
    - If price stays in lower half for N bars → shift mid down
    - Shift amount: 20% of half-range distance
    - Never shift beyond S/R boundaries

    This is the core of DGT (Dynamic Grid Trading).

    Parameters
    ----------
    data : pd.DataFrame
        Recent OHLCV data
        Must have 'close' column
    current_mid : float
        Current mid price
    support : float
        Support level (lower bound)
    resistance : float
        Resistance level (upper bound)
    threshold_bars : int, optional
        Number of bars to check, by default 20

    Returns
    -------
    float
        New mid price (or current_mid if no shift needed)

    Examples
    --------
    >>> # Price consistently in upper half
    >>> data = pd.DataFrame({'close': [102000] * 20})
    >>> new_mid = calculate_mid_shift(
    ...     data=data,
    ...     current_mid=100000.0,
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     threshold_bars=20
    ... )
    >>> new_mid > 100000.0  # Shifted up
    True

    Notes
    -----
    - This function is NOT used in Sprint 1 (MVP)
    - Will be integrated in Sprint 2 when enable_mid_shift=True
    - Prevents grid from being "stuck" in static position
    - Allows grid to follow trending range-bound markets
    - Requires careful tuning of threshold_bars to avoid noise
    """
    # Check if enough data
    if len(data) < threshold_bars:
        return current_mid

    # Get recent data
    recent_data = data.tail(threshold_bars)

    # Calculate how many bars are in upper/lower half
    upper_half = (recent_data["close"] > current_mid).sum()
    lower_half = (recent_data["close"] < current_mid).sum()

    upper_pct = upper_half / threshold_bars
    lower_pct = lower_half / threshold_bars

    # Check if consistently in upper half (80% threshold)
    if upper_pct > 0.8:
        # Shift mid upward
        # Amount: 20% of distance from mid to resistance
        shift_amount = (resistance - current_mid) * 0.2
        new_mid = current_mid + shift_amount

        # Ensure mid doesn't exceed resistance
        new_mid = min(new_mid, resistance)

        return new_mid

    # Check if consistently in lower half
    elif lower_pct > 0.8:
        # Shift mid downward
        # Amount: 20% of distance from support to mid
        shift_amount = (current_mid - support) * 0.2
        new_mid = current_mid - shift_amount

        # Ensure mid doesn't go below support
        new_mid = max(new_mid, support)

        return new_mid

    # No shift needed
    return current_mid


def calculate_effective_mid(
    data: pd.DataFrame,
    static_mid: float,
    support: float,
    resistance: float,
    enable_mid_shift: bool = False,
    mid_shift_threshold: int = 20,
) -> pd.Series:
    """
    Calculate effective mid price (static or dynamic).

    Wrapper function that handles both:
    - Sprint 1 (MVP): static mid
    - Sprint 2: dynamic mid with DGT

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data
    static_mid : float
        Static mid price (support + resistance) / 2
    support : float
        Support level
    resistance : float
        Resistance level
    enable_mid_shift : bool, optional
        Whether to enable DGT mid-shift, by default False
    mid_shift_threshold : int, optional
        Bars needed to trigger shift, by default 20

    Returns
    -------
    pd.Series
        Mid price series (static or dynamic)

    Examples
    --------
    >>> # Sprint 1: static mid
    >>> mid = calculate_effective_mid(
    ...     data=data,
    ...     static_mid=100000.0,
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     enable_mid_shift=False
    ... )
    >>> # All values are 100000.0
    >>>
    >>> # Sprint 2: dynamic mid
    >>> mid = calculate_effective_mid(
    ...     data=data,
    ...     static_mid=100000.0,
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     enable_mid_shift=True
    ... )
    >>> # Mid shifts based on price action
    """
    if not enable_mid_shift:
        # Sprint 1: static mid
        return pd.Series(static_mid, index=data.index)

    # Sprint 2: dynamic mid with DGT
    mid_series = pd.Series(index=data.index, dtype=float)

    # Initialize with static mid
    current_mid = static_mid

    for i in range(len(data)):
        # Calculate mid shift based on historical data up to this point
        if i >= mid_shift_threshold:
            historical_data = data.iloc[: i + 1]
            current_mid = calculate_mid_shift(
                data=historical_data,
                current_mid=current_mid,
                support=support,
                resistance=resistance,
                threshold_bars=mid_shift_threshold,
            )

        mid_series.iloc[i] = current_mid

    return mid_series
