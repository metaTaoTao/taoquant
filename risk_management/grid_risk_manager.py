"""
Grid Risk Manager (Sprint 2).

This module implements risk management and throttling rules for TaoGrid:
1. Inventory limit throttle
2. Profit target lock
3. Volatility spike throttle

Design Principles:
- Pure risk checking logic
- No side effects
- Type hints everywhere
- Comprehensive docstrings

References:
    - Implementation Plan: Sprint 2, Phase 2.3
    - Strategy Doc: Section 6 (Risk Management)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ThrottleStatus:
    """
    Throttling status and decision.

    Attributes
    ----------
    inventory_throttled : bool
        True if inventory limit exceeded
    profit_locked : bool
        True if daily profit target reached
    volatility_throttled : bool
        True if volatility spike detected
    size_multiplier : float
        Position size multiplier (0.0 = stop, 0.5 = reduce, 1.0 = full)
    reason : str
        Human-readable throttling reason
    """

    inventory_throttled: bool = False
    profit_locked: bool = False
    volatility_throttled: bool = False
    size_multiplier: float = 1.0
    reason: str = ""


class GridRiskManager:
    """
    Risk manager for grid trading strategies.

    Implements three throttling rules:
    1. **Inventory Limit**: Stop new orders if inventory exceeds max units
    2. **Profit Target Lock**: Reduce size when daily profit target reached
    3. **Volatility Spike**: Reduce size when volatility spikes

    Example
    -------
    >>> manager = GridRiskManager(
    ...     max_long_units=10.0,
    ...     max_short_units=10.0,
    ...     profit_target_pct=0.5,
    ...     volatility_threshold=2.0
    ... )
    >>> status = manager.check_throttle(
    ...     long_exposure=9.5,
    ...     short_exposure=0.0,
    ...     daily_pnl=5000,
    ...     risk_budget=10000,
    ...     current_atr=500,
    ...     avg_atr=250
    ... )
    >>> status.size_multiplier
    0.0  # Stop: inventory near limit
    """

    def __init__(
        self,
        max_long_units: float = 10.0,
        max_short_units: float = 10.0,
        inventory_threshold: float = 0.9,
        profit_target_pct: float = 0.5,
        profit_reduction: float = 0.5,
        volatility_threshold: float = 2.0,
        volatility_reduction: float = 0.5,
    ):
        """
        Initialize risk manager.

        Parameters
        ----------
        max_long_units : float, optional
            Maximum long exposure (in base currency), by default 10.0
        max_short_units : float, optional
            Maximum short exposure (in base currency), by default 10.0
        inventory_threshold : float, optional
            Inventory threshold to trigger throttle (0-1), by default 0.9
            Example: 0.9 = stop when 90% of max inventory used
        profit_target_pct : float, optional
            Daily profit target as % of risk budget, by default 0.5
            Example: 0.5 = 50% of daily risk budget
        profit_reduction : float, optional
            Size reduction when profit target reached, by default 0.5
            Example: 0.5 = reduce to 50% size
        volatility_threshold : float, optional
            ATR spike threshold (ratio to average), by default 2.0
            Example: 2.0 = throttle when ATR > 2x average
        volatility_reduction : float, optional
            Size reduction during volatility spike, by default 0.5
        """
        self.max_long_units = max_long_units
        self.max_short_units = max_short_units
        self.inventory_threshold = inventory_threshold
        self.profit_target_pct = profit_target_pct
        self.profit_reduction = profit_reduction
        self.volatility_threshold = volatility_threshold
        self.volatility_reduction = volatility_reduction

    def check_inventory_limit(
        self,
        long_exposure: float,
        short_exposure: float,
    ) -> bool:
        """
        Check if inventory limit exceeded.

        Logic:
        - If long_exposure / max_long_units >= threshold: throttle
        - If short_exposure / max_short_units >= threshold: throttle

        Parameters
        ----------
        long_exposure : float
            Current long exposure (in base currency)
        short_exposure : float
            Current short exposure (in base currency)

        Returns
        -------
        bool
            True if limit exceeded, False otherwise

        Examples
        --------
        >>> manager = GridRiskManager(max_long_units=10.0, inventory_threshold=0.9)
        >>> manager.check_inventory_limit(long_exposure=8.0, short_exposure=0.0)
        False
        >>> manager.check_inventory_limit(long_exposure=9.5, short_exposure=0.0)
        True  # 95% > 90% threshold
        """
        long_pct = long_exposure / self.max_long_units if self.max_long_units > 0 else 0.0
        short_pct = short_exposure / self.max_short_units if self.max_short_units > 0 else 0.0

        return long_pct >= self.inventory_threshold or short_pct >= self.inventory_threshold

    def check_profit_target(
        self,
        daily_pnl: float,
        risk_budget: float,
    ) -> bool:
        """
        Check if daily profit target reached.

        Logic:
        - If daily_pnl >= risk_budget × profit_target_pct: lock profit

        Parameters
        ----------
        daily_pnl : float
            Current daily P&L
        risk_budget : float
            Daily risk budget

        Returns
        -------
        bool
            True if profit target reached, False otherwise

        Examples
        --------
        >>> manager = GridRiskManager(profit_target_pct=0.5)
        >>> manager.check_profit_target(daily_pnl=3000, risk_budget=10000)
        False  # 3000 < 5000 (50% of 10000)
        >>> manager.check_profit_target(daily_pnl=6000, risk_budget=10000)
        True  # 6000 > 5000
        """
        if risk_budget <= 0:
            return False

        profit_target = risk_budget * self.profit_target_pct
        return daily_pnl >= profit_target

    def check_volatility_spike(
        self,
        current_atr: float,
        avg_atr: float,
    ) -> bool:
        """
        Check if volatility spike detected.

        Logic:
        - If current_atr / avg_atr >= threshold: throttle

        Parameters
        ----------
        current_atr : float
            Current ATR value
        avg_atr : float
            Average ATR (e.g., 20-period SMA of ATR)

        Returns
        -------
        bool
            True if volatility spike, False otherwise

        Examples
        --------
        >>> manager = GridRiskManager(volatility_threshold=2.0)
        >>> manager.check_volatility_spike(current_atr=300, avg_atr=200)
        False  # 1.5x < 2.0x
        >>> manager.check_volatility_spike(current_atr=450, avg_atr=200)
        True  # 2.25x > 2.0x
        """
        if avg_atr <= 0:
            return False

        atr_ratio = current_atr / avg_atr
        return atr_ratio >= self.volatility_threshold

    def check_throttle(
        self,
        long_exposure: float,
        short_exposure: float,
        daily_pnl: float,
        risk_budget: float,
        current_atr: float,
        avg_atr: float,
    ) -> ThrottleStatus:
        """
        Get comprehensive throttling status.

        This is the main entry point for risk checking.

        Parameters
        ----------
        long_exposure : float
            Current long exposure
        short_exposure : float
            Current short exposure
        daily_pnl : float
            Current daily P&L
        risk_budget : float
            Daily risk budget
        current_atr : float
            Current ATR value
        avg_atr : float
            Average ATR

        Returns
        -------
        ThrottleStatus
            Throttling decision with size_multiplier and reason

        Notes
        -----
        Throttling priority (highest to lowest):
        1. Inventory limit (size_multiplier = 0.0, stop all orders)
        2. Profit target (size_multiplier = profit_reduction)
        3. Volatility spike (size_multiplier = volatility_reduction)
        4. No throttle (size_multiplier = 1.0)

        Examples
        --------
        >>> manager = GridRiskManager(
        ...     max_long_units=10.0,
        ...     inventory_threshold=0.9,
        ...     profit_target_pct=0.5,
        ...     volatility_threshold=2.0
        ... )
        >>> # Case 1: Inventory limit exceeded
        >>> status = manager.check_throttle(
        ...     long_exposure=9.5,
        ...     short_exposure=0.0,
        ...     daily_pnl=1000,
        ...     risk_budget=10000,
        ...     current_atr=250,
        ...     avg_atr=250
        ... )
        >>> status.size_multiplier
        0.0
        >>> status.reason
        'Inventory limit exceeded (95.0% of max)'
        >>>
        >>> # Case 2: Profit target reached
        >>> status = manager.check_throttle(
        ...     long_exposure=5.0,
        ...     short_exposure=0.0,
        ...     daily_pnl=6000,
        ...     risk_budget=10000,
        ...     current_atr=250,
        ...     avg_atr=250
        ... )
        >>> status.size_multiplier
        0.5
        >>> status.reason
        'Profit target reached (60.0% of risk budget)'
        """
        status = ThrottleStatus()

        # Check inventory limit (highest priority)
        status.inventory_throttled = self.check_inventory_limit(
            long_exposure, short_exposure
        )

        if status.inventory_throttled:
            long_pct = long_exposure / self.max_long_units if self.max_long_units > 0 else 0.0
            short_pct = short_exposure / self.max_short_units if self.max_short_units > 0 else 0.0
            max_pct = max(long_pct, short_pct)

            status.size_multiplier = 0.0
            status.reason = f"Inventory limit exceeded ({max_pct:.1%} of max)"
            return status

        # Check profit lock
        status.profit_locked = self.check_profit_target(daily_pnl, risk_budget)

        if status.profit_locked:
            profit_pct = daily_pnl / risk_budget if risk_budget > 0 else 0.0
            status.size_multiplier = self.profit_reduction
            status.reason = f"Profit target reached ({profit_pct:.1%} of risk budget)"
            return status

        # Check volatility spike
        status.volatility_throttled = self.check_volatility_spike(
            current_atr, avg_atr
        )

        if status.volatility_throttled:
            atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
            status.size_multiplier = self.volatility_reduction
            status.reason = f"Volatility spike ({atr_ratio:.1f}x average ATR)"
            return status

        # No throttle
        status.size_multiplier = 1.0
        status.reason = "No throttle"
        return status


def calculate_throttled_size(
    base_size: float,
    throttle_status: ThrottleStatus,
) -> float:
    """
    Calculate throttled position size.

    Utility function to apply throttle to position size.

    Parameters
    ----------
    base_size : float
        Base position size (before throttling)
    throttle_status : ThrottleStatus
        Throttling decision

    Returns
    -------
    float
        Throttled position size

    Examples
    --------
    >>> status = ThrottleStatus(size_multiplier=0.5, reason="Profit lock")
    >>> calculate_throttled_size(base_size=1.0, throttle_status=status)
    0.5
    >>> status = ThrottleStatus(size_multiplier=0.0, reason="Inventory limit")
    >>> calculate_throttled_size(base_size=1.0, throttle_status=status)
    0.0
    """
    return base_size * throttle_status.size_multiplier
