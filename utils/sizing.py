from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np


def geometric_grid(
    base_price: float,
    gap_pct: float,
    support: float,
    resistance: float,
    max_levels_side: int,
) -> Tuple[List[float], List[float]]:
    """Generate geometric grid prices within [support, resistance]."""
    buy_prices: List[float] = []
    sell_prices: List[float] = []

    price = base_price
    for _ in range(max_levels_side):
        price *= 1.0 - gap_pct
        if price <= support or not math.isfinite(price):
            break
        buy_prices.append(price)

    price = base_price
    for _ in range(max_levels_side):
        price *= 1.0 + gap_pct
        if price >= resistance or not math.isfinite(price):
            break
        sell_prices.append(price)

    return buy_prices, sell_prices


def edge_weights(
    prices: Sequence[float],
    support: float,
    resistance: float,
    side: str,
    alpha: float,
    hit_counts: Dict[float, int] | None = None,
    decay_k: float = 2.0,
) -> List[float]:
    """Compute edge-biased weights with optional hit-count decay."""
    width = resistance - support
    if width <= 0:
        return [0.0] * len(prices)

    weights: List[float] = []
    hit_counts = hit_counts or {}

    for price in prices:
        if side == "long":
            raw = ((resistance - price) / width) ** alpha
        else:
            raw = ((price - support) / width) ** alpha
        hits = hit_counts.get(price, 0)
        decayed = raw * math.exp(-(hits) / max(decay_k, 1e-6))
        weights.append(max(decayed, 0.0))

    return weights


def normalize_weights(weights: Sequence[float]) -> List[float]:
    total = float(np.sum(weights))
    if total <= 0:
        return [0.0 for _ in weights]
    return [float(w) / total for w in weights]


def allocate_quantities(
    prices: Sequence[float],
    weights: Sequence[float],
    total_qty: float,
) -> List[float]:
    """Allocate quantities per price level based on weights."""
    norm = normalize_weights(weights)
    return [total_qty * w for w in norm]


def update_hit_counts(hit_counts: Dict[float, int], price: float, size: float) -> None:
    """Increment hit-count for given price level."""
    if not math.isfinite(price):
        return
    hit_counts[price] = hit_counts.get(price, 0) + int(abs(size) > 0)


def decay_hit_counts(hit_counts: Dict[float, int], window: Iterable[float]) -> Dict[float, int]:
    """Return a dict containing only hit counts for prices in window."""
    window_set = set(window)
    return {price: count for price, count in hit_counts.items() if price in window_set}
