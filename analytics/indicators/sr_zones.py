"""
Support/Resistance zone detection.

Pure functions for detecting and managing S/R zones based on pivot analysis.

Algorithm:
1. Detect pivot highs (local maxima) using rolling window
2. Calculate ATR for zone merging tolerance
3. Merge nearby pivots into zones
4. Track zone touches and breaks

This implementation replicates TradingView Pine Script logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from analytics.indicators.volatility import calculate_atr


@dataclass
class Zone:
    """
    Represents a support or resistance zone.

    Attributes
    ----------
    top : float
        Zone top price
    bottom : float
        Zone bottom price
    touches : int
        Number of times price touched this zone
    is_broken : bool
        Whether zone was broken by price
    fail_count : int
        Number of failed signals from this zone
    start_time : pd.Timestamp
        When zone was created (pivot bar time)
    end_time : Optional[pd.Timestamp]
        When zone was broken (None if still active)
    """

    top: float
    bottom: float
    touches: int = 1
    is_broken: bool = False
    fail_count: int = 0
    start_time: Optional[pd.Timestamp] = None
    end_time: Optional[pd.Timestamp] = None


def detect_pivot_highs(
    high: pd.Series,
    left_len: int,
    right_len: int,
) -> pd.Series:
    """
    Detect pivot highs using rolling window analysis.

    Equivalent to TradingView's pivothigh(high, left, right).

    A bar at index T is a pivot high if:
    - high[T] is the maximum of the window [T-left_len, T+right_len]

    Parameters
    ----------
    high : pd.Series
        High prices
    left_len : int
        Left lookback bars
    right_len : int
        Right confirmation bars

    Returns
    -------
    pd.Series
        Series with pivot high values at pivot indices, NaN elsewhere

    Examples
    --------
    >>> pivots = detect_pivot_highs(data['high'], left_len=90, right_len=10)
    >>> pivot_prices = pivots.dropna()
    >>> print(f"Found {len(pivot_prices)} pivot highs")

    Notes
    -----
    - Requires (left_len + right_len + 1) bars to confirm first pivot
    - Later bars are confirmed with right_len lag
    - Multiple bars can have same high value (all marked as pivots)

    Algorithm:
    1. Calculate rolling max with window = left_len + right_len + 1
    2. Shift back by right_len to center on pivot bar
    3. Mark bars where high equals rolling max
    """
    window_size = left_len + right_len + 1

    # Calculate rolling maximum
    rolling_max = high.rolling(
        window=window_size,
        min_periods=window_size
    ).max()

    # Shift back to center on pivot bar
    shifted_max = rolling_max.shift(-right_len)

    # Find pivots: where high equals local maximum
    is_pivot = high == shifted_max

    # Return series with pivot values (NaN elsewhere)
    pivots = pd.Series(index=high.index, dtype=float)
    pivots[is_pivot] = high[is_pivot]

    return pivots


def compute_sr_zones(
    data: pd.DataFrame,
    left_len: int = 90,
    right_len: int = 10,
    merge_atr_mult: float = 3.5,
    atr_period: int = 14,
    min_zone_thickness_atr: float = 0.2,
) -> pd.DataFrame:
    """
    Compute support/resistance zones from OHLCV data.

    This is a PURE FUNCTION: same input → same output, no side effects.

    Algorithm:
    1. Detect pivot highs using rolling window
    2. Calculate ATR for dynamic tolerance
    3. For each pivot:
       - Calculate zone body (max(open, close) at pivot bar)
       - Add minimum thickness (0.2 * ATR)
       - Try to merge with existing zones
       - If no merge, create new zone
    4. Return DataFrame with zone columns aligned to input data

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data with columns: [open, high, low, close, volume]
    left_len : int
        Left lookback for pivot detection (default: 90)
    right_len : int
        Right confirmation for pivot detection (default: 10)
    merge_atr_mult : float
        ATR multiplier for zone merging tolerance (default: 3.5)
    atr_period : int
        ATR calculation period (default: 14)
    min_zone_thickness_atr : float
        Minimum zone thickness as ATR multiple (default: 0.2)

    Returns
    -------
    pd.DataFrame
        Original data with added columns:
        - zone_top: float (NaN if no zone at this bar)
        - zone_bottom: float
        - zone_touches: int (number of touches)
        - zone_is_broken: bool

    Examples
    --------
    >>> # Detect zones on 4H data
    >>> data_4h = resample_ohlcv(data, '4h')
    >>> zones_4h = compute_sr_zones(
    ...     data_4h,
    ...     left_len=90,
    ...     right_len=10,
    ...     merge_atr_mult=3.5
    ... )
    >>>
    >>> # Check active zones
    >>> active_zones = zones_4h[zones_4h['zone_is_broken'] == False]
    >>> print(f"Found {len(active_zones)} active zones")

    Notes
    -----
    - This function processes data incrementally (bar-by-bar simulation)
    - Mimics TradingView Pine Script behavior
    - Zones are confirmed with right_len lag
    - ATR is calculated on the same timeframe as input data
    """
    # Validate input
    required_cols = ['open', 'high', 'low', 'close']
    missing_cols = [col for col in required_cols if col not in data.columns]
    if missing_cols:
        raise ValueError(f"Data missing required columns: {missing_cols}")

    # Detect pivot highs
    pivots = detect_pivot_highs(data['high'], left_len, right_len)

    # Calculate ATR
    atr = calculate_atr(
        data['high'],
        data['low'],
        data['close'],
        period=atr_period
    )

    # Get pivot events: index → (pivot_real_idx, p_high, p_body)
    pivot_indices = np.where(~np.isnan(pivots.values))[0]

    pivot_events = {}
    for pivot_real_idx in pivot_indices:
        p_high = pivots.iloc[pivot_real_idx]

        # Pivot is confirmed right_len bars after it happens
        confirmation_idx = pivot_real_idx + right_len

        if confirmation_idx < len(data):
            # Body top = max(open, close) at pivot bar
            p_body = max(
                data['open'].iloc[pivot_real_idx],
                data['close'].iloc[pivot_real_idx]
            )

            pivot_events[confirmation_idx] = (pivot_real_idx, p_high, p_body)

    # Initialize zones list
    zones: List[Zone] = []

    # Process each bar (incremental simulation)
    for i in range(len(data)):
        current_close = data['close'].iloc[i]
        current_atr = atr.iloc[i] if i < len(atr) else 0.01
        if np.isnan(current_atr):
            current_atr = 0.01

        # 1. Check breaks for active zones
        for zone in zones:
            if not zone.is_broken:
                break_threshold = zone.top + (current_atr * 0.5)
                if current_close > break_threshold:
                    zone.is_broken = True
                    zone.end_time = data.index[i]

        # 2. Check for new pivot confirmation
        if i in pivot_events:
            pivot_real_idx, p_high, p_body = pivot_events[i]

            # Add minimum thickness
            if (p_high - p_body) < (current_atr * min_zone_thickness_atr):
                p_body = p_high - (current_atr * min_zone_thickness_atr)

            # Try to merge with existing zones
            merged = False
            tolerance = current_atr * merge_atr_mult

            for zone in zones:
                if zone.is_broken:
                    continue

                # Check if pivot overlaps with zone
                if p_high <= (zone.top + tolerance) and p_high >= (zone.bottom - tolerance):
                    # Merge: expand zone and increment touches
                    zone.top = max(zone.top, p_high)
                    zone.bottom = min(zone.bottom, p_body)
                    zone.touches += 1
                    merged = True
                    break

            # If not merged, create new zone
            if not merged:
                new_zone = Zone(
                    top=p_high,
                    bottom=p_body,
                    start_time=data.index[pivot_real_idx],
                    end_time=data.index[i],
                    touches=1,
                    is_broken=False
                )
                zones.append(new_zone)

    # Convert zones to DataFrame columns
    # For each bar, find the nearest active zone
    zone_tops = []
    zone_bottoms = []
    zone_touches_list = []
    zone_is_broken_list = []

    for i in range(len(data)):
        # Find active zones at this time
        current_time = data.index[i]
        active_zones_at_time = [
            z for z in zones
            if z.start_time <= current_time and (z.end_time is None or z.end_time >= current_time)
        ]

        if active_zones_at_time:
            # Use first active zone (can be extended to multiple zones)
            zone = active_zones_at_time[0]
            zone_tops.append(zone.top)
            zone_bottoms.append(zone.bottom)
            zone_touches_list.append(zone.touches)
            zone_is_broken_list.append(zone.is_broken)
        else:
            zone_tops.append(np.nan)
            zone_bottoms.append(np.nan)
            zone_touches_list.append(0)
            zone_is_broken_list.append(False)

    # Add columns to data
    result = data.copy()
    result['zone_top'] = zone_tops
    result['zone_bottom'] = zone_bottoms
    result['zone_touches'] = zone_touches_list
    result['zone_is_broken'] = zone_is_broken_list
    result['atr'] = atr

    return result


def get_active_zones(data_with_zones: pd.DataFrame) -> pd.DataFrame:
    """
    Extract active (non-broken) zones from data.

    Parameters
    ----------
    data_with_zones : pd.DataFrame
        Data with zone columns (from compute_sr_zones)

    Returns
    -------
    pd.DataFrame
        DataFrame with only active zones

    Examples
    --------
    >>> zones = compute_sr_zones(data)
    >>> active = get_active_zones(zones)
    >>> print(f"Active zones: {len(active)}")
    """
    return data_with_zones[
        (data_with_zones['zone_is_broken'] == False) &
        (data_with_zones['zone_top'].notna())
    ]
