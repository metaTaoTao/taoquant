"""
Data models for Signal Processor.

Defines entry signals and signal metadata.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import pandas as pd


class SignalType(str, Enum):
    """Signal types."""
    NORMAL = 'normal'  # Regular entry
    TWO_B = '2b'  # 2B reversal entry


@dataclass
class EntrySignal:
    """
    Entry signal specification.

    Represents WHERE and HOW to enter positions.
    """
    # Signal DataFrame: boolean series indicating entry points
    signals: pd.Series  # Boolean series (True = enter)

    # Side: 'long' or 'short'
    side: str

    # Signal type (normal or 2B reversal)
    signal_type: pd.Series = None  # Series of SignalType (aligned with signals)

    # Zone info for position tracking (optional)
    zone_keys: pd.Series = None  # Series of tuples (zone_bottom, zone_top)

    # Risk multiplier for different signal types (optional)
    risk_multipliers: pd.Series = None  # Series of floats (e.g., 4.0 for 2B trades)

    # Metadata for each signal
    metadata: pd.DataFrame = None  # DataFrame with additional info per signal

    def __post_init__(self):
        """Initialize defaults."""
        if self.signal_type is None:
            self.signal_type = pd.Series(
                SignalType.NORMAL,
                index=self.signals.index,
                dtype='object'
            )
        if self.risk_multipliers is None:
            self.risk_multipliers = pd.Series(
                1.0,
                index=self.signals.index,
                dtype=float
            )
