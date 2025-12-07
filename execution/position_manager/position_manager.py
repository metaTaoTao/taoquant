"""
Position Manager.

Manages position lifecycle, tracking, and exit execution.
Core implementation of position management logic.
"""

from __future__ import annotations
from typing import List, Optional, Dict
from datetime import datetime
import pandas as pd

from execution.position_manager.models import (
    Position,
    OrderAction,
    PositionSide,
    OrderType,
)
from execution.position_manager.exit_rules import (
    ExitRules,
    ZeroCostRule,
)


class PositionManager:
    """
    Manages position tracking and exit execution.

    Responsibilities:
    - Track open positions
    - Update position state (best price, trailing stops)
    - Check exit conditions (SL, TP, trailing stop)
    - Generate exit orders

    Does NOT:
    - Generate entry signals (that's Strategy's job)
    - Execute orders (that's Engine's job)
    - Calculate position sizes (that's risk management's job)
    """

    def __init__(self, max_positions: int = 10):
        """
        Initialize Position Manager.

        Parameters
        ----------
        max_positions : int
            Maximum number of concurrent positions
        """
        self.max_positions = max_positions
        self.positions: List[Position] = []
        self._position_counter = 0

    def can_enter_position(self) -> bool:
        """Check if we can enter a new position."""
        return len(self.positions) < self.max_positions

    def add_position(
        self,
        entry_idx: int,
        entry_time: datetime,
        entry_price: float,
        entry_atr: float,
        side: PositionSide,
        entry_size: float,
        exit_rules: ExitRules,
        zone_key: Optional[tuple] = None,
        is_2b_trade: bool = False,
    ) -> Position:
        """
        Add a new position.

        Parameters
        ----------
        entry_idx : int
            Bar index of entry
        entry_time : datetime
            Timestamp of entry
        entry_price : float
            Entry price
        entry_atr : float
            ATR at entry
        side : PositionSide
            Position direction
        entry_size : float
            Signal size
        exit_rules : ExitRules
            Exit rules for this position
        zone_key : tuple, optional
            Zone identifier
        is_2b_trade : bool
            Whether this is a 2B reversal trade

        Returns
        -------
        Position
            Created position
        """
        self._position_counter += 1
        position_id = f"pos_{self._position_counter}"

        position = Position(
            position_id=position_id,
            entry_idx=entry_idx,
            entry_time=entry_time,
            entry_price=entry_price,
            entry_atr=entry_atr,
            side=side,
            entry_size=entry_size,
            zone_key=zone_key,
            is_2b_trade=is_2b_trade,
            metadata={'exit_rules': exit_rules}
        )

        self.positions.append(position)
        return position

    def check_exits(
        self,
        bar_idx: int,
        price: float,
        atr: float
    ) -> List[OrderAction]:
        """
        Check exit conditions for all positions.

        Parameters
        ----------
        bar_idx : int
            Current bar index
        price : float
            Current price
        atr : float
            Current ATR

        Returns
        -------
        List[OrderAction]
            List of exit orders to execute
        """
        exit_orders = []
        positions_to_remove = []

        for i, pos in enumerate(self.positions):
            # Update best price for trailing stop
            self._update_best_price(pos, price)

            # Get exit rules for this position
            exit_rules: ExitRules = pos.metadata.get('exit_rules')
            if exit_rules is None:
                continue

            # Check exits in order of priority
            order = None

            # 1. Check Stop Loss (highest priority)
            order = self._check_stop_loss(pos, price, bar_idx, exit_rules)
            if order:
                exit_orders.append(order)
                positions_to_remove.append(i)
                continue

            # 2. Check TP1 (Zero-Cost) - only if not yet hit
            if not pos.tp1_hit and exit_rules.take_profit:
                order = self._check_zero_cost_tp(pos, price, atr, bar_idx, exit_rules)
                if order:
                    exit_orders.append(order)
                    # Don't remove position, just mark TP1 hit
                    pos.tp1_hit = True
                    pos.remaining_size *= (1 - order.exit_fraction)
                    continue

            # 3. Check Trailing Stop (only after TP1)
            # Use entry_atr (HTF ATR at entry) for trailing stop, not current_atr
            # This keeps trailing stop distance stable and avoids being too tight when ATR decreases
            if pos.tp1_hit and exit_rules.trailing_stop:
                order = self._check_trailing_stop(pos, price, pos.entry_atr, bar_idx, exit_rules)
                if order:
                    exit_orders.append(order)
                    positions_to_remove.append(i)
                    continue

        # Remove closed positions (in reverse order to preserve indices)
        for i in reversed(positions_to_remove):
            self.positions.pop(i)

        return exit_orders

    def _update_best_price(self, pos: Position, current_price: float):
        """
        Update best price for trailing stop.

        For SHORT: track lowest price (best profit)
        For LONG: track highest price (best profit)
        """
        if pos.is_short:
            if current_price < pos.best_price:
                pos.best_price = current_price
        else:
            if current_price > pos.best_price:
                pos.best_price = current_price

    def _check_stop_loss(
        self,
        pos: Position,
        price: float,
        bar_idx: int,
        exit_rules: ExitRules
    ) -> Optional[OrderAction]:
        """Check if stop loss is hit."""
        sl_price = exit_rules.stop_loss.calculate_stop_price(
            entry_price=pos.entry_price,
            entry_atr=pos.entry_atr,
            side=pos.side.value
        )

        # Check if SL hit
        if pos.is_short and price >= sl_price:
            return OrderAction(
                order_type=OrderType.SL,
                position_id=pos.position_id,
                exit_fraction=1.0,  # Close 100%
                price=price,
                bar_idx=bar_idx,
                reason=f'SL hit at {price:.2f} (SL={sl_price:.2f})',
                zone_key=pos.zone_key,
                is_2b_trade=pos.is_2b_trade,
                entry_price=pos.entry_price,
                entry_atr=pos.entry_atr,
            )
        elif pos.is_long and price <= sl_price:
            return OrderAction(
                order_type=OrderType.SL,
                position_id=pos.position_id,
                exit_fraction=1.0,
                price=price,
                bar_idx=bar_idx,
                reason=f'SL hit at {price:.2f} (SL={sl_price:.2f})',
                zone_key=pos.zone_key,
                is_2b_trade=pos.is_2b_trade,
                entry_price=pos.entry_price,
                entry_atr=pos.entry_atr,
            )

        return None

    def _check_zero_cost_tp(
        self,
        pos: Position,
        price: float,
        atr: float,
        bar_idx: int,
        exit_rules: ExitRules
    ) -> Optional[OrderAction]:
        """Check if zero-cost TP1 should trigger."""
        # Calculate profit and risk
        if pos.is_short:
            profit = pos.entry_price - price
        else:
            profit = price - pos.entry_price

        sl_price = exit_rules.stop_loss.calculate_stop_price(
            entry_price=pos.entry_price,
            entry_atr=pos.entry_atr,
            side=pos.side.value
        )
        risk = abs(pos.entry_price - sl_price)

        if risk <= 0:
            return None

        profit_ratio = profit / risk

        # Check each TP rule (usually just one for zero-cost)
        for tp_rule in exit_rules.take_profit:
            if isinstance(tp_rule, ZeroCostRule) and tp_rule.should_trigger(profit_ratio):
                return OrderAction(
                    order_type=OrderType.TP1,
                    position_id=pos.position_id,
                    exit_fraction=tp_rule.get_exit_fraction(),
                    price=price,
                    bar_idx=bar_idx,
                    reason=f'Zero-cost TP1 at {profit_ratio:.2f}R',
                    zone_key=pos.zone_key,
                    is_2b_trade=pos.is_2b_trade,
                )

        return None

    def _check_trailing_stop(
        self,
        pos: Position,
        price: float,
        atr: float,
        bar_idx: int,
        exit_rules: ExitRules
    ) -> Optional[OrderAction]:
        """Check if trailing stop is hit."""
        trailing_rule = exit_rules.trailing_stop

        # Calculate new trailing stop price
        new_stop = trailing_rule.calculate_stop_price(
            best_price=pos.best_price,
            current_atr=atr,
            side=pos.side.value
        )

        # Update trailing stop (move in favorable direction only)
        if pos.trailing_stop_price is None:
            pos.trailing_stop_price = new_stop
        else:
            if pos.is_short:
                # For short: move DOWN (tighter), never UP (looser)
                pos.trailing_stop_price = min(pos.trailing_stop_price, new_stop)
            else:
                # For long: move UP (tighter), never DOWN (looser)
                pos.trailing_stop_price = max(pos.trailing_stop_price, new_stop)

        # Check if trailing stop hit
        if pos.is_short and price >= pos.trailing_stop_price:
            return OrderAction(
                order_type=OrderType.TP2,
                position_id=pos.position_id,
                exit_fraction=1.0,  # Close remaining
                price=price,
                bar_idx=bar_idx,
                reason=f'Trailing stop hit at {price:.2f} (stop={pos.trailing_stop_price:.2f})',
                zone_key=pos.zone_key,
                is_2b_trade=pos.is_2b_trade,
            )
        elif pos.is_long and price <= pos.trailing_stop_price:
            return OrderAction(
                order_type=OrderType.TP2,
                position_id=pos.position_id,
                exit_fraction=1.0,
                price=price,
                bar_idx=bar_idx,
                reason=f'Trailing stop hit at {price:.2f} (stop={pos.trailing_stop_price:.2f})',
                zone_key=pos.zone_key,
                is_2b_trade=pos.is_2b_trade,
            )

        return None

    def force_close_all(self, bar_idx: int, price: float) -> List[OrderAction]:
        """
        Force close all remaining positions.

        Used at end of backtest.

        Parameters
        ----------
        bar_idx : int
            Current bar index
        price : float
            Current price

        Returns
        -------
        List[OrderAction]
            Force close orders
        """
        orders = []
        for pos in self.positions:
            orders.append(OrderAction(
                order_type=OrderType.FORCE_CLOSE,
                position_id=pos.position_id,
                exit_fraction=1.0,
                price=price,
                bar_idx=bar_idx,
                reason='Force close at end of backtest',
                zone_key=pos.zone_key,
                is_2b_trade=pos.is_2b_trade,
            ))

        self.positions.clear()
        return orders

    def get_position_count(self) -> int:
        """Get number of open positions."""
        return len(self.positions)

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID."""
        for pos in self.positions:
            if pos.position_id == position_id:
                return pos
        return None
