"""
Signal-based trading strategies.

These strategies generate entry/exit signals based on technical analysis.
"""

from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig

__all__ = [
    "SRShortStrategy",
    "SRShortConfig",
]
