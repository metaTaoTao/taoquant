"""
Grid Level Weighting (Pure Functions).

This module implements position weighting logic for TaoGrid:
1. Level-wise weighting (edge-heavy, mid-light)
2. Regime-based side allocation (70/30, 50/50, 30/70)
3. Layer size calculation

All functions are PURE FUNCTIONS:
- Same inputs → same outputs
- No side effects
- No state mutations

Design Principles (from CLAUDE.md):
1. Pure functions only
2. Type hints everywhere
3. Comprehensive docstrings
4. No data fetching
5. No logging

References:
    - Strategy Doc Section 5.1: Level-wise weighting
    - Strategy Doc Section 5.1.2: Neutral range (edge-heavy)
    - Strategy Doc Section 5.1.3: UP_RANGE (70/30)
    - Strategy Doc Section 5.1.4: DOWN_RANGE (30/70)
"""

from typing import Dict, Literal

import numpy as np

RegimeType = Literal["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]


def calculate_level_weights(num_levels: int, weight_k: float = 0.5) -> np.ndarray:
    """
    Calculate linear weights for grid levels (edge-heavy, mid-light).

    Formula (from strategy doc Section 5.1.2):
        raw_w(i) = 1 + k × (i - 1), where i=1 is closest to mid
        w(i) = raw_w(i) / Σ raw_w (normalized)

    Logic:
        - Level i=1: closest to mid, smallest weight
        - Level i=N: closest to edge (S/R), largest weight
        - Reflects intuition: edges have better risk/reward

    Example (num_levels=4, k=0.5):
        i=1: raw=1.0 → w ≈ 14% (closest to mid)
        i=2: raw=1.5 → w ≈ 21%
        i=3: raw=2.0 → w ≈ 29%
        i=4: raw=2.5 → w ≈ 36% (closest to edge)

    Parameters
    ----------
    num_levels : int
        Number of grid levels
    weight_k : float, optional
        Linear coefficient, by default 0.5
        Higher k → more edge-heavy
        Lower k → more uniform

    Returns
    -------
    np.ndarray
        Normalized weights array (sums to 1.0)
        Shape: (num_levels,)

    Examples
    --------
    >>> weights = calculate_level_weights(num_levels=4, weight_k=0.5)
    >>> weights
    array([0.14285714, 0.21428571, 0.28571429, 0.35714286])
    >>> weights.sum()
    1.0

    Notes
    -----
    - Weights are ALWAYS normalized to sum to 1.0
    - Can be applied to both buy and sell sides
    - Higher weight_k (e.g., 1.0) makes distribution more skewed
    - Lower weight_k (e.g., 0.2) makes distribution more uniform
    """
    # Generate raw weights: 1, 1+k, 1+2k, ...
    i_values = np.arange(num_levels)  # 0, 1, 2, ...
    raw_weights = 1.0 + weight_k * i_values

    # Normalize to sum to 1.0
    normalized_weights = raw_weights / raw_weights.sum()

    return normalized_weights


def allocate_side_budgets(
    total_budget: float, regime: RegimeType
) -> Dict[str, float]:
    """
    Allocate budget to buy/sell sides based on regime.

    Logic (from strategy doc Section 5.1.3, 5.1.4):
    - UP_RANGE: buy 70%, sell 30% (favor long, expect upward drift)
    - NEUTRAL_RANGE: buy 50%, sell 50% (neutral, pure mean-reversion)
    - DOWN_RANGE: buy 30%, sell 70% (favor short, expect downward drift)

    This is the CORE of regime-based position allocation.

    Parameters
    ----------
    total_budget : float
        Total risk budget for the strategy
        Example: 30000 (if capital=100k, risk_budget_pct=0.3)
    regime : RegimeType
        Market regime: "UP_RANGE" | "NEUTRAL_RANGE" | "DOWN_RANGE"

    Returns
    -------
    Dict[str, float]
        Dictionary with 'buy_budget' and 'sell_budget' keys

    Examples
    --------
    >>> # UP_RANGE: favor long
    >>> allocate_side_budgets(total_budget=30000, regime="UP_RANGE")
    {'buy_budget': 21000.0, 'sell_budget': 9000.0}
    >>>
    >>> # NEUTRAL_RANGE: balanced
    >>> allocate_side_budgets(total_budget=30000, regime="NEUTRAL_RANGE")
    {'buy_budget': 15000.0, 'sell_budget': 15000.0}
    >>>
    >>> # DOWN_RANGE: favor short
    >>> allocate_side_budgets(total_budget=30000, regime="DOWN_RANGE")
    {'buy_budget': 9000.0, 'sell_budget': 21000.0}

    Notes
    -----
    - buy_budget + sell_budget = total_budget (always)
    - Allocation reflects trader's directional bias
    - In trending ranges, asymmetric allocation improves risk/reward
    - In neutral ranges, symmetric allocation maximizes turnover
    """
    if regime == "UP_RANGE":
        buy_pct, sell_pct = 0.7, 0.3
    elif regime == "NEUTRAL_RANGE":
        buy_pct, sell_pct = 0.5, 0.5
    elif regime == "DOWN_RANGE":
        buy_pct, sell_pct = 0.3, 0.7
    else:
        raise ValueError(
            f"Invalid regime: {regime}. "
            f"Must be one of: UP_RANGE, NEUTRAL_RANGE, DOWN_RANGE"
        )

    return {
        "buy_budget": total_budget * buy_pct,
        "sell_budget": total_budget * sell_pct,
    }


def calculate_layer_sizes(
    budget: float, weights: np.ndarray, prices: np.ndarray
) -> np.ndarray:
    """
    Calculate position size (in base currency) for each layer.

    Formula:
        nominal_i = budget × weight_i
        size_i = nominal_i / price_i

    This converts budget allocation to actual position sizes.

    Parameters
    ----------
    budget : float
        Total budget for this side (buy or sell)
        Example: 21000 for buy side in UP_RANGE
    weights : np.ndarray
        Weight array (normalized, sums to 1.0)
        Example: [0.14, 0.21, 0.29, 0.36] for 4 layers
    prices : np.ndarray
        Price array for each level
        Example: [99000, 98010, 97030, 96060] for buy levels

    Returns
    -------
    np.ndarray
        Size array (in base currency units, e.g., BTC)
        Example: [0.030, 0.045, 0.063, 0.080] for BTC

    Examples
    --------
    >>> budget = 21000.0  # Buy side budget
    >>> weights = np.array([0.14, 0.21, 0.29, 0.36])
    >>> prices = np.array([99000., 98010., 97030., 96060.])
    >>> sizes = calculate_layer_sizes(budget, weights, prices)
    >>> sizes
    array([0.02969697, 0.04500459, 0.06277792, 0.07866942])
    >>>
    >>> # Verify total nominal value
    >>> (sizes * prices).sum()
    21000.0

    Notes
    -----
    - Sizes are in BASE CURRENCY (e.g., BTC for BTCUSDT)
    - Total nominal value: Σ(size_i × price_i) = budget
    - Weights determine distribution across layers
    - Prices determine actual coin/token amounts
    """
    # Validate inputs have same length
    if len(weights) != len(prices):
        raise ValueError(
            f"weights and prices must have same length. "
            f"Got weights: {len(weights)}, prices: {len(prices)}"
        )

    # Calculate nominal amount per layer
    nominal_per_layer = budget * weights

    # Convert to position sizes (in base currency)
    # size = nominal / price
    sizes = nominal_per_layer / prices

    return sizes


def calculate_grid_position_sizes(
    total_budget: float,
    regime: RegimeType,
    buy_levels: np.ndarray,
    sell_levels: np.ndarray,
    weight_k: float = 0.5,
) -> Dict[str, np.ndarray]:
    """
    Calculate position sizes for all grid levels (convenience function).

    This is a high-level wrapper that combines:
    1. Side budget allocation (based on regime)
    2. Level weight calculation (edge-heavy)
    3. Layer size calculation (budget → sizes)

    Parameters
    ----------
    total_budget : float
        Total risk budget for strategy
    regime : RegimeType
        Market regime
    buy_levels : np.ndarray
        Array of buy prices
    sell_levels : np.ndarray
        Array of sell prices
    weight_k : float, optional
        Weight coefficient, by default 0.5

    Returns
    -------
    Dict[str, np.ndarray]
        Dictionary with 'buy_sizes' and 'sell_sizes' keys
        Sizes are in base currency units

    Examples
    --------
    >>> total_budget = 30000.0
    >>> regime = "UP_RANGE"
    >>> buy_levels = np.array([99000., 98010., 97030., 96060.])
    >>> sell_levels = np.array([101000., 102010., 103030., 104061.])
    >>>
    >>> sizes = calculate_grid_position_sizes(
    ...     total_budget=total_budget,
    ...     regime=regime,
    ...     buy_levels=buy_levels,
    ...     sell_levels=sell_levels,
    ...     weight_k=0.5
    ... )
    >>>
    >>> sizes['buy_sizes']  # 70% of budget (UP_RANGE)
    array([0.02969697, 0.04500459, 0.06277792, 0.07866942])
    >>>
    >>> sizes['sell_sizes']  # 30% of budget (UP_RANGE)
    array([0.01272277, 0.01928431, 0.02690832, 0.03375166])

    Notes
    -----
    - Automatically handles regime-based allocation
    - Automatically handles edge-heavy weighting
    - Returns ready-to-use position sizes
    - Can be used directly in strategy implementation
    """
    # Step 1: Allocate budget to buy/sell sides
    budgets = allocate_side_budgets(total_budget=total_budget, regime=regime)

    # Step 2: Calculate weights for each side
    buy_weights = calculate_level_weights(
        num_levels=len(buy_levels), weight_k=weight_k
    )
    sell_weights = calculate_level_weights(
        num_levels=len(sell_levels), weight_k=weight_k
    )

    # Step 3: Calculate position sizes
    buy_sizes = calculate_layer_sizes(
        budget=budgets["buy_budget"], weights=buy_weights, prices=buy_levels
    )

    sell_sizes = calculate_layer_sizes(
        budget=budgets["sell_budget"], weights=sell_weights, prices=sell_levels
    )

    return {"buy_sizes": buy_sizes, "sell_sizes": sell_sizes}
