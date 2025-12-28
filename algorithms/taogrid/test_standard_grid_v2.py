"""
Test Standard Grid V2 - Verify Exchange-Compliant Behavior.
"""

import sys
from pathlib import Path
from datetime import datetime

taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from algorithms.taogrid.standard_grid_v2 import StandardGridV2


def test_basic_behavior():
    """Test basic grid behavior with simple price movements."""
    print("\n" + "=" * 80)
    print("TEST: Basic Grid Behavior (10 grids, $85k-$95k)")
    print("=" * 80)

    # Create grid
    grid = StandardGridV2(
        lower_price=85000.0,
        upper_price=95000.0,
        grid_count=10,
        mode="geometric",
        total_investment=10000.0,
        leverage=1.0,
    )

    # Initialize at $90k
    grid.initialize_grid(current_price=90000.0)

    stats = grid.get_statistics()
    print(f"\nAfter initialization:")
    print(f"  Active buy orders: {stats['active_buy_orders']}")
    print(f"  Active sell orders: {stats['active_sell_orders']}")

    # Simulate price movements
    print("\n" + "-" * 80)
    print("Simulation: Price movements")
    print("-" * 80)

    # 1. Price drops to $87k - should trigger buy
    print("\n1. Price drops to $87,000")
    filled = grid.check_and_fill_orders(
        bar_high=90000,
        bar_low=87000,
        timestamp=datetime.now(),
    )
    print(f"   Filled: {len(filled)} orders")

    # 2. Price rises to $91k - should trigger sell
    print("\n2. Price rises to $91,000")
    filled = grid.check_and_fill_orders(
        bar_high=91000,
        bar_low=87000,
        timestamp=datetime.now(),
    )
    print(f"   Filled: {len(filled)} orders")

    # 3. Price drops again to $88k - should trigger re-entry buy
    print("\n3. Price drops to $88,000")
    filled = grid.check_and_fill_orders(
        bar_high=91000,
        bar_low=88000,
        timestamp=datetime.now(),
    )
    print(f"   Filled: {len(filled)} orders")

    # Final statistics
    print("\n" + "=" * 80)
    print("Final Statistics")
    print("=" * 80)

    stats = grid.get_statistics()
    print(f"Total PnL: ${stats['total_pnl']:,.2f}")
    print(f"Total Fees: ${stats['total_fees']:,.2f}")
    print(f"Net PnL: ${stats['net_pnl']:,.2f}")
    print(f"Total Trades: {stats['total_trades']}")
    print(f"Buy Volume: {stats['total_buy_volume']:.6f} BTC")
    print(f"Sell Volume: {stats['total_sell_volume']:.6f} BTC")
    print(f"Net Position: {stats['net_position_btc']:.6f} BTC")
    print(f"Active Buy Orders: {stats['active_buy_orders']}")
    print(f"Active Sell Orders: {stats['active_sell_orders']}")

    # Verify key invariant: Buy Volume - Sell Volume = Net Position
    assert abs(stats['total_buy_volume'] - stats['total_sell_volume'] - stats['net_position_btc']) < 1e-6, \
        "Position mismatch!"

    print("\n[PASS] Position accounting is correct!")
    print("=" * 80 + "\n")


def test_one_order_per_grid():
    """Test that each grid level has max 1 order."""
    print("\n" + "=" * 80)
    print("TEST: One Order Per Grid Enforcement")
    print("=" * 80)

    grid = StandardGridV2(
        lower_price=80000.0,
        upper_price=100000.0,
        grid_count=20,
        mode="geometric",
        total_investment=10000.0,
    )

    grid.initialize_grid(current_price=90000.0)

    # Check each grid has at most 1 order
    for g in grid.grid_levels:
        has_both = g.has_buy_order() and g.has_sell_order()
        assert not has_both, f"Grid {g.index} has BOTH buy and sell orders!"

    print("[PASS] Each grid has at most 1 order")

    # Simulate some trades
    for _ in range(10):
        grid.check_and_fill_orders(
            bar_high=95000,
            bar_low=85000,
            timestamp=datetime.now(),
        )

    # Check again
    for g in grid.grid_levels:
        has_both = g.has_buy_order() and g.has_sell_order()
        assert not has_both, f"Grid {g.index} has BOTH buy and sell orders after trading!"

    print("[PASS] Invariant maintained after 10 bars of trading")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    test_basic_behavior()
    test_one_order_per_grid()

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80 + "\n")
