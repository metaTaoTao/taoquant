"""
Grid Inventory Tracker (Sprint 2).

This module tracks position inventory for TaoGrid strategy:
1. Current long/short exposure
2. Grid level utilization
3. Inventory limits checking

All functions maintain inventory state but remain testable.

Design Principles:
- Pure inventory tracking logic
- No side effects (no logging, no data fetching)
- Type hints everywhere
- Comprehensive docstrings

References:
    - Implementation Plan: Sprint 2, Phase 2.2
    - Strategy Doc: Section 6 (Risk Management)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class InventoryState:
    """
    Snapshot of current grid inventory.

    Attributes
    ----------
    long_exposure : float
        Current long exposure (in base currency units)
        Example: 1.5 BTC long
    short_exposure : float
        Current short exposure (in base currency units)
        Example: 0.8 BTC short
    net_exposure : float
        Net exposure (long - short)
        Example: 0.7 BTC net long
    long_pct : float
        Long exposure as percentage of max
        Example: 0.75 = 75% of max long units
    short_pct : float
        Short exposure as percentage of max
    grid_fills : Dict[str, float]
        Grid level fills: {'buy_L1': 0.5, 'sell_L1': 0.3, ...}
        Value is the fill amount in base currency
    """

    long_exposure: float = 0.0
    short_exposure: float = 0.0
    net_exposure: float = 0.0
    long_pct: float = 0.0
    short_pct: float = 0.0
    grid_fills: Dict[str, float] = None

    def __post_init__(self):
        """Initialize grid_fills if not provided."""
        if self.grid_fills is None:
            self.grid_fills = {}


class GridInventoryTracker:
    """
    Track grid position inventory over time.

    This class maintains stateful inventory tracking for grid strategies.
    It tracks:
    - Current long/short exposure
    - Grid level utilization
    - Whether inventory limits are exceeded

    Example
    -------
    >>> tracker = GridInventoryTracker(max_long_units=10.0, max_short_units=10.0)
    >>> tracker.update(long_size=1.5, short_size=0.0, grid_level='buy_L1')
    >>> state = tracker.get_state()
    >>> state.long_exposure
    1.5
    >>> state.long_pct
    0.15  # 15% of max
    """

    def __init__(
        self,
        max_long_units: float = 10.0,
        max_short_units: float = 10.0,
    ):
        """
        Initialize inventory tracker.

        Parameters
        ----------
        max_long_units : float, optional
            Maximum allowed long exposure (in base currency)
            Example: 10.0 BTC
        max_short_units : float, optional
            Maximum allowed short exposure (in base currency)
            Example: 10.0 BTC
        """
        self.max_long_units = max_long_units
        self.max_short_units = max_short_units

        # Current inventory state
        self._long_exposure = 0.0
        self._short_exposure = 0.0
        self._grid_fills: Dict[str, float] = {}

        # History (for analysis)
        self._history: list[InventoryState] = []

    def update(
        self,
        long_size: float = 0.0,
        short_size: float = 0.0,
        grid_level: Optional[str] = None,
    ) -> None:
        """
        Update inventory with new position changes.

        Parameters
        ----------
        long_size : float, optional
            Change in long position (positive = add, negative = reduce)
            Example: 0.5 = add 0.5 BTC long
        short_size : float, optional
            Change in short position (positive = add, negative = reduce)
            Example: -0.3 = close 0.3 BTC short
        grid_level : str, optional
            Grid level identifier (e.g., 'buy_L1', 'sell_L2')
            If provided, tracks per-level fills

        Notes
        -----
        - Positive long_size = open long or add to long
        - Negative long_size = close long or reduce long
        - Positive short_size = open short or add to short
        - Negative short_size = close short or reduce short
        """
        # Update exposures
        self._long_exposure = max(0.0, self._long_exposure + long_size)
        self._short_exposure = max(0.0, self._short_exposure + short_size)

        # Update grid-level tracking if level specified
        if grid_level:
            if grid_level not in self._grid_fills:
                self._grid_fills[grid_level] = 0.0

            # Track total filled at this level
            self._grid_fills[grid_level] += abs(long_size) + abs(short_size)

        # Save snapshot to history
        self._history.append(self.get_state())

    def get_state(self) -> InventoryState:
        """
        Get current inventory state snapshot.

        Returns
        -------
        InventoryState
            Current inventory state with exposures and percentages
        """
        long_pct = self._long_exposure / self.max_long_units if self.max_long_units > 0 else 0.0
        short_pct = self._short_exposure / self.max_short_units if self.max_short_units > 0 else 0.0
        net_exposure = self._long_exposure - self._short_exposure

        return InventoryState(
            long_exposure=self._long_exposure,
            short_exposure=self._short_exposure,
            net_exposure=net_exposure,
            long_pct=long_pct,
            short_pct=short_pct,
            grid_fills=self._grid_fills.copy(),
        )

    def check_limit(self, side: str = 'both') -> bool:
        """
        Check if inventory limit is exceeded.

        Parameters
        ----------
        side : str, optional
            Which side to check: 'long', 'short', or 'both'

        Returns
        -------
        bool
            True if limit exceeded, False otherwise

        Examples
        --------
        >>> tracker = GridInventoryTracker(max_long_units=10.0)
        >>> tracker.update(long_size=5.0)
        >>> tracker.check_limit('long')
        False
        >>> tracker.update(long_size=6.0)  # Total 11.0
        >>> tracker.check_limit('long')
        True
        """
        state = self.get_state()

        if side == 'long':
            return state.long_pct >= 1.0
        elif side == 'short':
            return state.short_pct >= 1.0
        elif side == 'both':
            return state.long_pct >= 1.0 or state.short_pct >= 1.0
        else:
            raise ValueError(f"Invalid side: {side}. Must be 'long', 'short', or 'both'")

    def get_available_capacity(self, side: str) -> float:
        """
        Get remaining capacity for new positions.

        Parameters
        ----------
        side : str
            'long' or 'short'

        Returns
        -------
        float
            Remaining capacity in base currency units

        Examples
        --------
        >>> tracker = GridInventoryTracker(max_long_units=10.0)
        >>> tracker.update(long_size=3.0)
        >>> tracker.get_available_capacity('long')
        7.0
        """
        state = self.get_state()

        if side == 'long':
            return max(0.0, self.max_long_units - state.long_exposure)
        elif side == 'short':
            return max(0.0, self.max_short_units - state.short_exposure)
        else:
            raise ValueError(f"Invalid side: {side}. Must be 'long' or 'short'")

    def reset(self) -> None:
        """
        Reset inventory to zero.

        This should be called at the start of each backtest.
        """
        self._long_exposure = 0.0
        self._short_exposure = 0.0
        self._grid_fills.clear()
        self._history.clear()

    def get_history(self) -> pd.DataFrame:
        """
        Get inventory history as DataFrame.

        Returns
        -------
        pd.DataFrame
            History with columns: long_exposure, short_exposure, net_exposure, etc.

        Notes
        -----
        - Useful for analyzing inventory evolution during backtest
        - Each row is a snapshot after an inventory update
        """
        if not self._history:
            return pd.DataFrame()

        records = [
            {
                'long_exposure': state.long_exposure,
                'short_exposure': state.short_exposure,
                'net_exposure': state.net_exposure,
                'long_pct': state.long_pct,
                'short_pct': state.short_pct,
            }
            for state in self._history
        ]

        return pd.DataFrame(records)


def calculate_inventory_from_trades(
    trades: pd.DataFrame,
    max_long_units: float,
    max_short_units: float,
) -> pd.DataFrame:
    """
    Calculate inventory evolution from trade history.

    This is a utility function for post-backtest analysis.

    Parameters
    ----------
    trades : pd.DataFrame
        Trade history with columns: ['timestamp', 'size', 'direction']
        - size: position size (positive)
        - direction: 'long' or 'short'
    max_long_units : float
        Maximum long exposure
    max_short_units : float
        Maximum short exposure

    Returns
    -------
    pd.DataFrame
        Inventory history with columns:
        - timestamp
        - long_exposure
        - short_exposure
        - net_exposure
        - long_pct
        - short_pct

    Examples
    --------
    >>> trades = pd.DataFrame({
    ...     'timestamp': pd.date_range('2025-01-01', periods=3, freq='1h'),
    ...     'size': [1.0, 0.5, 1.5],
    ...     'direction': ['long', 'long', 'short']
    ... })
    >>> inventory = calculate_inventory_from_trades(
    ...     trades, max_long_units=10.0, max_short_units=10.0
    ... )
    >>> inventory['long_exposure'].iloc[-1]
    1.5
    >>> inventory['short_exposure'].iloc[-1]
    1.5
    """
    tracker = GridInventoryTracker(
        max_long_units=max_long_units,
        max_short_units=max_short_units
    )

    inventory_records = []

    for _, trade in trades.iterrows():
        # Update inventory
        if trade['direction'] == 'long':
            tracker.update(long_size=trade['size'])
        elif trade['direction'] == 'short':
            tracker.update(short_size=trade['size'])

        # Record state
        state = tracker.get_state()
        inventory_records.append({
            'timestamp': trade.get('timestamp', pd.NaT),
            'long_exposure': state.long_exposure,
            'short_exposure': state.short_exposure,
            'net_exposure': state.net_exposure,
            'long_pct': state.long_pct,
            'short_pct': state.short_pct,
        })

    return pd.DataFrame(inventory_records)
