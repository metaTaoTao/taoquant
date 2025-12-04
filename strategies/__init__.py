"""
Strategies package initialization.

New architecture: All strategies extend BaseStrategy and implement
three pure functions: compute_indicators, generate_signals, calculate_position_size
"""

from __future__ import annotations

from .base_strategy import BaseStrategy, StrategyConfig
from .signal_based.sr_short import SRShortStrategy, SRShortConfig

__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "SRShortStrategy",
    "SRShortConfig",
]
