from __future__ import annotations

import math
from typing import Tuple


def is_cooldown(atr_short: float, atr_long: float, ratio_threshold: float) -> bool:
    if atr_long <= 0 or not math.isfinite(atr_long):
        return False
    if not math.isfinite(atr_short):
        return False
    return (atr_short / atr_long) < ratio_threshold


def midline_rebalance(
    price: float,
    midline: float,
    band_pct: float,
    net_position: float,
    exposure_thresh: float,
    max_position: float,
) -> float:
    if not math.isfinite(price) or not math.isfinite(midline):
        return 0.0
    if midline == 0:
        return 0.0
    if abs(price - midline) / abs(midline) > band_pct:
        return 0.0
    limit = exposure_thresh * max_position
    if abs(net_position) <= limit:
        return 0.0
    target = math.copysign(limit, net_position)
    return net_position - target


def update_breakout_state(
    close: float,
    support: float,
    resistance: float,
    epsilon: float,
    atr_short: float,
    atr_long: float,
    ratio_threshold: float,
    below_count: int,
    above_count: int,
) -> Tuple[int, int, bool]:
    breakout = False
    if math.isfinite(support) and close < support - epsilon:
        below_count += 1
    else:
        below_count = 0

    if math.isfinite(resistance) and close > resistance + epsilon:
        above_count += 1
    else:
        above_count = 0

    if (below_count >= 2 or above_count >= 2) and atr_long > 0 and math.isfinite(atr_short):
        if atr_short / atr_long >= ratio_threshold:
            breakout = True
    return below_count, above_count, breakout
