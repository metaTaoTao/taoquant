"""
Position Manager Module

Manages position lifecycle, tracking, and exit execution.
Separates position management logic from strategy signal generation.
"""

from execution.position_manager.models import (
    Position,
    OrderAction,
    PositionSide,
)
from execution.position_manager.exit_rules import (
    ExitRules,
    StopLossRule,
    TakeProfitRule,
    ZeroCostRule,
    TrailingStopRule,
)
from execution.position_manager.position_manager import PositionManager

__all__ = [
    'Position',
    'OrderAction',
    'PositionSide',
    'ExitRules',
    'StopLossRule',
    'TakeProfitRule',
    'ZeroCostRule',
    'TrailingStopRule',
    'PositionManager',
]
