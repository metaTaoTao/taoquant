"""
Strategies package initialization.
"""

from __future__ import annotations

from .sma_cross import SmaCrossStrategy
from .tdxh_dip import TDXHDipStrategy
from .sr_guard import SRGuardRailStrategy
from .structure_weighted_grid import StructureWeightedGrid

STRATEGY_REGISTRY = {
    "sma_cross": SmaCrossStrategy,
    "tdxh": TDXHDipStrategy,
    "sr_guard": SRGuardRailStrategy,
    "sr_grid": StructureWeightedGrid,
}

__all__ = [
    "SmaCrossStrategy",
    "TDXHDipStrategy",
    "SRGuardRailStrategy",
    "StructureWeightedGrid",
    "STRATEGY_REGISTRY",
]

