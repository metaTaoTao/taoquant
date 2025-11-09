"""
Strategies package initialization.
"""

from __future__ import annotations

from .sma_cross import SmaCrossStrategy
from .tdxh_dip import TDXHDipStrategy

STRATEGY_REGISTRY = {
    "sma_cross": SmaCrossStrategy,
    "tdxh": TDXHDipStrategy,
}

__all__ = ["SmaCrossStrategy", "TDXHDipStrategy", "STRATEGY_REGISTRY"]

