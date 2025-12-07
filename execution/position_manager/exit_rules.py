"""
Exit Rules System.

Defines exit conditions as declarative rules (what, not how).
Position Manager executes these rules.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
from abc import ABC, abstractmethod


@dataclass
class StopLossRule:
    """
    Stop loss rule configuration.

    Defines when and how to stop out of a position.
    """
    type: str = 'atr'  # 'atr', 'fixed', 'percentage'
    atr_mult: float = 3.0  # ATR multiplier
    fixed_distance: Optional[float] = None  # Fixed distance in price
    percentage: Optional[float] = None  # Percentage from entry

    def calculate_stop_price(
        self,
        entry_price: float,
        entry_atr: float,
        side: str
    ) -> float:
        """
        Calculate stop loss price.

        Parameters
        ----------
        entry_price : float
            Entry price
        entry_atr : float
            ATR at entry
        side : str
            'long' or 'short'

        Returns
        -------
        float
            Stop loss price
        """
        if self.type == 'atr':
            distance = entry_atr * self.atr_mult
        elif self.type == 'fixed':
            distance = self.fixed_distance
        elif self.type == 'percentage':
            distance = entry_price * (self.percentage / 100)
        else:
            raise ValueError(f"Unknown stop loss type: {self.type}")

        if side == 'short':
            return entry_price + distance  # Stop above entry for short
        else:
            return entry_price - distance  # Stop below entry for long


@dataclass
class ZeroCostRule:
    """
    Zero-cost position rule.

    Triggers partial exit when profit reaches certain R:R to lock in
    initial risk, making remaining position "zero cost".
    """
    trigger_rr: float = 3.33  # Trigger at 3.33R
    exit_pct: float = 0.30  # Exit 30% of position
    lock_risk: bool = True  # Move SL to breakeven after TP1

    def should_trigger(self, profit_ratio: float) -> bool:
        """Check if zero-cost TP should trigger."""
        return profit_ratio >= self.trigger_rr

    def get_exit_fraction(self) -> float:
        """Get fraction of position to exit."""
        return self.exit_pct


@dataclass
class TrailingStopRule:
    """
    Trailing stop rule.

    Follows price movement to lock in profit.
    """
    distance_atr_mult: float = 5.0  # Distance from best price
    offset_atr_mult: float = 2.0  # Offset to give room

    # Computed
    @property
    def net_distance_mult(self) -> float:
        """Net distance from best price."""
        return self.distance_atr_mult - self.offset_atr_mult

    def calculate_stop_price(
        self,
        best_price: float,
        current_atr: float,
        side: str
    ) -> float:
        """
        Calculate trailing stop price.

        Parameters
        ----------
        best_price : float
            Best price seen so far
        current_atr : float
            Current ATR
        side : str
            'long' or 'short'

        Returns
        -------
        float
            Trailing stop price
        """
        distance = current_atr * self.distance_atr_mult
        offset = current_atr * self.offset_atr_mult
        net_distance = distance - offset

        if side == 'short':
            # For short: stop above best (lowest) price
            return best_price + net_distance
        else:
            # For long: stop below best (highest) price
            return best_price - net_distance


@dataclass
class TakeProfitRule:
    """
    Simple take profit rule.

    Exit at fixed R:R ratio.
    """
    target_rr: float = 2.0
    exit_pct: float = 1.0  # Exit 100% by default

    def should_trigger(self, profit_ratio: float) -> bool:
        """Check if TP should trigger."""
        return profit_ratio >= self.target_rr


@dataclass
class ExitRules:
    """
    Complete set of exit rules for a position.

    Aggregates all exit conditions.
    """
    stop_loss: StopLossRule
    trailing_stop: Optional[TrailingStopRule] = None
    take_profit: List[ZeroCostRule] = None  # Can have multiple TP levels

    def __post_init__(self):
        """Initialize defaults."""
        if self.take_profit is None:
            self.take_profit = []

    @classmethod
    def create_default(cls, side: str = 'short') -> ExitRules:
        """
        Create default exit rules.

        Parameters
        ----------
        side : str
            'long' or 'short'

        Returns
        -------
        ExitRules
            Default exit rules
        """
        return cls(
            stop_loss=StopLossRule(type='atr', atr_mult=3.0),
            take_profit=[
                ZeroCostRule(
                    trigger_rr=3.33,
                    exit_pct=0.30,
                    lock_risk=True
                )
            ],
            trailing_stop=TrailingStopRule(
                distance_atr_mult=5.0,
                offset_atr_mult=2.0
            )
        )

    @classmethod
    def create_2b_rules(cls) -> ExitRules:
        """
        Create 2B reversal exit rules.

        Returns
        -------
        ExitRules
            2B-specific exit rules
        """
        return cls(
            stop_loss=StopLossRule(type='atr', atr_mult=3.0),
            take_profit=[
                ZeroCostRule(
                    trigger_rr=2.0,  # More aggressive for 2B
                    exit_pct=0.30,
                    lock_risk=True
                )
            ],
            trailing_stop=TrailingStopRule(
                distance_atr_mult=5.0,
                offset_atr_mult=2.0
            )
        )
