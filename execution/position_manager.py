"""
Position management system for tracking multiple concurrent positions.

This module provides a clean replacement for the VirtualTrade system,
with proper separation of concerns and type safety.

Design Principles:
- Immutable positions: once created, properties don't change (except state)
- Clear state transitions: active → closed
- Pure calculations: P&L calculation is deterministic
- Type-safe: full type hints
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

import pandas as pd


class PositionDirection(Enum):
    """Position direction enum."""

    LONG = "long"
    SHORT = "short"


class PositionStatus(Enum):
    """Position status enum."""

    ACTIVE = "active"
    CLOSED = "closed"


@dataclass
class Position:
    """
    Represents a single trading position.

    This is a clean replacement for VirtualTrade with better design:
    - Immutable core properties (entry_time, entry_price, etc.)
    - Mutable state properties (status, exit_time, etc.)
    - Pure P&L calculation methods

    Attributes
    ----------
    position_id : str
        Unique identifier for this position
    entry_time : datetime
        Time when position was entered
    entry_price : float
        Entry price
    size : float
        Position size (quantity of base asset)
        Positive for long, negative for short
    direction : PositionDirection
        Position direction (LONG or SHORT)
    stop_loss : Optional[float]
        Stop loss price (None if no SL)
    take_profit : Optional[float]
        Take profit price (None if no TP)
    metadata : dict
        Additional metadata (strategy name, zone info, etc.)

    State Attributes (mutable)
    ---------------------------
    status : PositionStatus
        Current status (ACTIVE or CLOSED)
    exit_time : Optional[datetime]
        Time when position was closed
    exit_price : Optional[float]
        Exit price
    exit_reason : Optional[str]
        Reason for exit (SL, TP, signal, etc.)
    realized_pnl : float
        Realized P&L (0 until closed)

    Examples
    --------
    >>> pos = Position(
    ...     position_id="SHORT_1",
    ...     entry_time=pd.Timestamp('2025-01-01 00:00:00'),
    ...     entry_price=100.0,
    ...     size=-0.5,  # Short 0.5 BTC
    ...     direction=PositionDirection.SHORT,
    ...     stop_loss=105.0,
    ...     take_profit=90.0
    ... )
    >>>
    >>> # Calculate unrealized P&L
    >>> pnl = pos.calculate_unrealized_pnl(95.0)
    >>> print(f"Unrealized P&L: ${pnl:.2f}")
    >>>
    >>> # Close position
    >>> pos.close(exit_price=95.0, exit_time=pd.Timestamp('2025-01-02'), reason="TP")
    >>> print(f"Realized P&L: ${pos.realized_pnl:.2f}")
    """

    # Core properties (immutable)
    position_id: str
    entry_time: datetime
    entry_price: float
    size: float
    direction: PositionDirection
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    # State properties (mutable)
    status: PositionStatus = PositionStatus.ACTIVE
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: float = 0.0

    def __post_init__(self):
        """Validate position after initialization."""
        if self.size == 0:
            raise ValueError("Position size cannot be zero")

        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")

        # Validate direction matches size sign
        if self.direction == PositionDirection.LONG and self.size < 0:
            raise ValueError("Long position must have positive size")

        if self.direction == PositionDirection.SHORT and self.size > 0:
            raise ValueError("Short position must have negative size")

    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L at current price.

        For LONG: P&L = (current_price - entry_price) * |size|
        For SHORT: P&L = (entry_price - current_price) * |size|

        Parameters
        ----------
        current_price : float
            Current market price

        Returns
        -------
        float
            Unrealized P&L in quote currency

        Examples
        --------
        >>> # Long position: bought at 100, now at 110
        >>> long_pos = Position(..., entry_price=100, size=1.0, direction=LONG)
        >>> long_pos.calculate_unrealized_pnl(110)  # +10
        10.0
        >>>
        >>> # Short position: sold at 100, now at 90
        >>> short_pos = Position(..., entry_price=100, size=-1.0, direction=SHORT)
        >>> short_pos.calculate_unrealized_pnl(90)  # +10
        10.0
        """
        if self.status != PositionStatus.ACTIVE:
            return 0.0

        if self.direction == PositionDirection.LONG:
            return (current_price - self.entry_price) * abs(self.size)
        else:  # SHORT
            return (self.entry_price - current_price) * abs(self.size)

    def calculate_return_pct(self, current_price: float) -> float:
        """
        Calculate return percentage.

        Parameters
        ----------
        current_price : float
            Current market price

        Returns
        -------
        float
            Return percentage (e.g., 0.05 = 5%)
        """
        pnl = self.calculate_unrealized_pnl(current_price)
        position_value = self.entry_price * abs(self.size)
        return pnl / position_value if position_value > 0 else 0.0

    def close(
        self,
        exit_price: float,
        exit_time: datetime,
        reason: str = "manual"
    ) -> float:
        """
        Close the position and calculate realized P&L.

        Parameters
        ----------
        exit_price : float
            Exit price
        exit_time : datetime
            Exit timestamp
        reason : str
            Reason for exit (SL, TP, signal, manual, etc.)

        Returns
        -------
        float
            Realized P&L

        Raises
        ------
        ValueError
            If position is already closed
        """
        if self.status == PositionStatus.CLOSED:
            raise ValueError(f"Position {self.position_id} is already closed")

        self.status = PositionStatus.CLOSED
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason
        self.realized_pnl = self.calculate_unrealized_pnl(exit_price)

        return self.realized_pnl

    def update_stop_loss(self, new_sl: float) -> None:
        """
        Update stop loss price (for trailing stops, break-even moves, etc.).

        Parameters
        ----------
        new_sl : float
            New stop loss price

        Raises
        ------
        ValueError
            If position is already closed
        """
        if self.status == PositionStatus.CLOSED:
            raise ValueError(f"Cannot update SL on closed position {self.position_id}")

        self.stop_loss = new_sl

    def update_take_profit(self, new_tp: float) -> None:
        """
        Update take profit price.

        Parameters
        ----------
        new_tp : float
            New take profit price

        Raises
        ------
        ValueError
            If position is already closed
        """
        if self.status == PositionStatus.CLOSED:
            raise ValueError(f"Cannot update TP on closed position {self.position_id}")

        self.take_profit = new_tp

    def check_stop_loss(self, high: float, low: float) -> bool:
        """
        Check if stop loss was hit during a bar.

        Parameters
        ----------
        high : float
            Bar high price
        low : float
            Bar low price

        Returns
        -------
        bool
            True if stop loss was hit
        """
        if self.stop_loss is None:
            return False

        if self.direction == PositionDirection.LONG:
            # Long SL is below entry, triggered if low <= SL
            return low <= self.stop_loss
        else:  # SHORT
            # Short SL is above entry, triggered if high >= SL
            return high >= self.stop_loss

    def check_take_profit(self, high: float, low: float) -> bool:
        """
        Check if take profit was hit during a bar.

        Parameters
        ----------
        high : float
            Bar high price
        low : float
            Bar low price

        Returns
        -------
        bool
            True if take profit was hit
        """
        if self.take_profit is None:
            return False

        if self.direction == PositionDirection.LONG:
            # Long TP is above entry, triggered if high >= TP
            return high >= self.take_profit
        else:  # SHORT
            # Short TP is below entry, triggered if low <= TP
            return low <= self.take_profit

    def to_dict(self) -> dict:
        """
        Convert position to dictionary.

        Returns
        -------
        dict
            Dictionary representation
        """
        return {
            'position_id': self.position_id,
            'entry_time': self.entry_time,
            'entry_price': self.entry_price,
            'size': self.size,
            'direction': self.direction.value,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'status': self.status.value,
            'exit_time': self.exit_time,
            'exit_price': self.exit_price,
            'exit_reason': self.exit_reason,
            'realized_pnl': self.realized_pnl,
            'metadata': self.metadata,
        }


class PositionTracker:
    """
    Tracks multiple concurrent positions and manages their lifecycle.

    This is a stateful manager that:
    - Creates new positions
    - Updates existing positions (SL/TP adjustments)
    - Closes positions based on exit conditions
    - Tracks equity over time

    Design Pattern: Manager/Repository pattern

    Examples
    --------
    >>> tracker = PositionTracker(initial_cash=100000.0)
    >>>
    >>> # Open position
    >>> pos = tracker.open_position(
    ...     position_id="SHORT_1",
    ...     entry_time=pd.Timestamp('2025-01-01'),
    ...     entry_price=100.0,
    ...     size=-0.5,
    ...     direction=PositionDirection.SHORT,
    ...     stop_loss=105.0,
    ...     take_profit=90.0
    ... )
    >>>
    >>> # Update equity
    >>> tracker.update_equity(current_price=95.0)
    >>> print(f"Current Equity: ${tracker.get_equity():.2f}")
    >>>
    >>> # Close position
    >>> tracker.close_position(
    ...     position_id="SHORT_1",
    ...     exit_price=95.0,
    ...     exit_time=pd.Timestamp('2025-01-02'),
    ...     reason="TP"
    ... )
    """

    def __init__(self, initial_cash: float):
        """
        Initialize position tracker.

        Parameters
        ----------
        initial_cash : float
            Starting capital
        """
        if initial_cash <= 0:
            raise ValueError(f"initial_cash must be positive, got {initial_cash}")

        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: List[Position] = []
        self.equity_history: List[dict] = []

    def open_position(
        self,
        position_id: str,
        entry_time: datetime,
        entry_price: float,
        size: float,
        direction: PositionDirection,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> Position:
        """
        Open a new position.

        Parameters
        ----------
        position_id : str
            Unique position ID
        entry_time : datetime
            Entry timestamp
        entry_price : float
            Entry price
        size : float
            Position size (negative for short)
        direction : PositionDirection
            Position direction
        stop_loss : Optional[float]
            Stop loss price
        take_profit : Optional[float]
            Take profit price
        metadata : Optional[dict]
            Additional metadata

        Returns
        -------
        Position
            Newly created position

        Raises
        ------
        ValueError
            If position_id already exists
        """
        # Check for duplicate ID
        if any(p.position_id == position_id for p in self.positions):
            raise ValueError(f"Position {position_id} already exists")

        # Create position
        pos = Position(
            position_id=position_id,
            entry_time=entry_time,
            entry_price=entry_price,
            size=size,
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata or {},
        )

        self.positions.append(pos)
        return pos

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_time: datetime,
        reason: str = "manual"
    ) -> float:
        """
        Close a position by ID.

        Parameters
        ----------
        position_id : str
            Position ID to close
        exit_price : float
            Exit price
        exit_time : datetime
            Exit timestamp
        reason : str
            Exit reason

        Returns
        -------
        float
            Realized P&L

        Raises
        ------
        ValueError
            If position not found
        """
        pos = self.get_position(position_id)
        if pos is None:
            raise ValueError(f"Position {position_id} not found")

        pnl = pos.close(exit_price, exit_time, reason)
        self.cash += pnl  # Update cash with realized P&L
        return pnl

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID."""
        for pos in self.positions:
            if pos.position_id == position_id:
                return pos
        return None

    def get_active_positions(self) -> List[Position]:
        """Get all active positions."""
        return [p for p in self.positions if p.status == PositionStatus.ACTIVE]

    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions."""
        return [p for p in self.positions if p.status == PositionStatus.CLOSED]

    def update_equity(self, current_price: float, timestamp: Optional[datetime] = None):
        """
        Update equity calculation and record history.

        Parameters
        ----------
        current_price : float
            Current market price
        timestamp : Optional[datetime]
            Current timestamp (for history)
        """
        # Calculate unrealized P&L from active positions
        unrealized_pnl = sum(
            p.calculate_unrealized_pnl(current_price)
            for p in self.get_active_positions()
        )

        # Total equity = cash + unrealized P&L
        total_equity = self.cash + unrealized_pnl

        # Record history
        if timestamp:
            self.equity_history.append({
                'timestamp': timestamp,
                'cash': self.cash,
                'unrealized_pnl': unrealized_pnl,
                'total_equity': total_equity,
                'active_positions': len(self.get_active_positions()),
            })

    def get_equity(self) -> float:
        """Get current equity (latest from history)."""
        if not self.equity_history:
            return self.initial_cash
        return self.equity_history[-1]['total_equity']

    def get_realized_pnl(self) -> float:
        """Get total realized P&L from closed positions."""
        return sum(p.realized_pnl for p in self.get_closed_positions())

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Get total unrealized P&L from active positions."""
        return sum(
            p.calculate_unrealized_pnl(current_price)
            for p in self.get_active_positions()
        )

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert all positions to DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with all positions
        """
        if not self.positions:
            return pd.DataFrame()

        return pd.DataFrame([p.to_dict() for p in self.positions])

    def equity_curve_to_dataframe(self) -> pd.DataFrame:
        """
        Convert equity history to DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with equity history
        """
        if not self.equity_history:
            return pd.DataFrame()

        df = pd.DataFrame(self.equity_history)
        if 'timestamp' in df.columns:
            df = df.set_index('timestamp')
        return df
