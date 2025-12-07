"""
Signal Processor Module.

Converts strategy signals + exit rules into executable orders.
Bridges the gap between pure strategy logic and execution engine.
"""

from execution.signal_processor.signal_processor import SignalProcessor
from execution.signal_processor.models import EntrySignal, SignalType

__all__ = [
    'SignalProcessor',
    'EntrySignal',
    'SignalType',
]
