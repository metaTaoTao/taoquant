"""
Data models for Position Manager.

Pure data classes with no business logic.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from datetime import datetime


class PositionSide(str, Enum):
    """Position direction."""
    LONG = 'long'
    SHORT = 'short'


class OrderType(str, Enum):
    """Order types for tracking."""
    ENTRY = 'ENTRY'
    TP1 = 'TP1'
    TP2 = 'TP2'
    SL = 'SL'
    TRAILING_STOP = 'TRAILING_STOP'
    FORCE_CLOSE = 'FORCE_CLOSE'


@dataclass
class Position:
    """
    Position state container.

    Tracks all necessary state for managing a single position.
    Immutable by convention (modify through PositionManager methods).
    """
    # Identification
    position_id: str
    entry_idx: int
    entry_time: datetime

    # Entry details
    entry_price: float
    entry_atr: float
    side: PositionSide
    entry_size: float  # Signal size (not BTC amount)

    # Exit tracking
    tp1_hit: bool = False
    remaining_size: float = None  # After partial exits

    # Trailing stop state
    best_price: float = None  # Best price seen (for trailing)
    trailing_stop_price: Optional[float] = None

    # Metadata
    zone_key: Optional[tuple] = None
    is_2b_trade: bool = False
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Initialize computed fields."""
        if self.remaining_size is None:
            self.remaining_size = self.entry_size
        if self.best_price is None:
            self.best_price = self.entry_price

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.side == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.side == PositionSide.SHORT


@dataclass
class OrderAction:
    """
    Order action to be executed.

    Represents an exit order with all necessary information.
    """
    order_type: OrderType
    position_id: str
    exit_fraction: float  # Fraction of remaining position (0.0-1.0)
    price: float
    bar_idx: int
    reason: str = ''

    # Position metadata (for Signal Processor to track zones and 2B reversals)
    zone_key: Optional[tuple] = None
    is_2b_trade: bool = False
    entry_price: Optional[float] = None
    entry_atr: Optional[float] = None

    def __post_init__(self):
        """Validate order action."""
        if not (0.0 <= self.exit_fraction <= 1.0):
            raise ValueError(f"exit_fraction must be in [0, 1], got {self.exit_fraction}")
