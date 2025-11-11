"""
Strategies package initialization.
"""

from __future__ import annotations

from .sma_cross import SmaCrossStrategy
from .tdxh_dip import TDXHDipStrategy
from .sr_guard import SRGuardRailStrategy

STRATEGY_REGISTRY = {
    "sma_cross": SmaCrossStrategy,
    "tdxh": TDXHDipStrategy,
    "sr_guard": SRGuardRailStrategy,
}

__all__ = ["SmaCrossStrategy", "TDXHDipStrategy", "SRGuardRailStrategy", "STRATEGY_REGISTRY"]

