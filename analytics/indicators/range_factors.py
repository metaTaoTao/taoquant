"""
Range factors for grid / market-making strategies.

All functions are pure (no I/O, no side effects).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_range_position(
    close: pd.Series,
    support: float,
    resistance: float,
) -> pd.Series:
    """
    Compute normalized position within a fixed range: (close - support) / (resistance - support).

    Returns values clipped to [0, 1].
    """
    if support >= resistance:
        raise ValueError("support must be < resistance")
    width = float(resistance - support)
    pos = (close.astype(float) - float(support)) / width
    return pos.clip(lower=0.0, upper=1.0)


def range_asymmetry_multipliers(
    range_pos: pd.Series,
    buy_k: float = 0.6,
    sell_k: float = 0.6,
    buy_floor: float = 0.4,
    sell_floor: float = 0.4,
) -> pd.DataFrame:
    """
    Convert range position into buy/sell multipliers.

    Intuition:
      - Near bottom (pos~0): increase buy, decrease sell.
      - Near top (pos~1): decrease buy, increase sell.

    buy_mult = max(buy_floor, 1 - buy_k * pos)
    sell_mult = max(sell_floor, 1 - sell_k * (1 - pos))

    Parameters
    ----------
    range_pos : pd.Series
        0..1 range position.
    buy_k, sell_k : float
        Strength of asymmetry.
    buy_floor, sell_floor : float
        Floors to keep churn alive.
    """
    if buy_k < 0 or sell_k < 0:
        raise ValueError("buy_k and sell_k must be >= 0")
    if not (0.0 <= buy_floor <= 1.0) or not (0.0 <= sell_floor <= 1.0):
        raise ValueError("floors must be in [0, 1]")

    rp = range_pos.astype(float).clip(lower=0.0, upper=1.0).fillna(0.5)
    buy_mult = np.maximum(float(buy_floor), 1.0 - float(buy_k) * rp)
    sell_mult = np.maximum(float(sell_floor), 1.0 - float(sell_k) * (1.0 - rp))
    return pd.DataFrame({"buy_mult": buy_mult, "sell_mult": sell_mult}, index=range_pos.index)


