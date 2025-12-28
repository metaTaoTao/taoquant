"""
Test script for Neutral Grid implementation.

This script validates:
1. Grid price generation (geometric vs arithmetic)
2. Order placement logic
3. Buy/sell pairing (adjacent grids)
4. Re-entry mechanism
5. PnL calculation
"""

import sys
from pathlib import Path

# Add taoquant to path
taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from algorithms.taogrid.neutral_grid_config import NeutralGridConfig
from algorithms.taogrid.neutral_grid import NeutralGridManager


def test_geometric_grid():
    """Test geometric grid generation."""
    print("\n" + "=" * 80)
    print("TEST 1: Geometric Grid Generation (等比网格)")
    print("=" * 80)

    config = NeutralGridConfig(
        lower_price=90000.0,
        upper_price=110000.0,
        grid_count=10,
        mode="geometric",
        total_investment=10000.0,
        initial_position_pct=0.0,  # No initial position for this test
        enable_console_log=False,
    )

    manager = NeutralGridManager(config)
    prices = manager.generate_grid_prices()

    print(f"Generated {len(prices)} price points:")
    for i, p in enumerate(prices):
        print(f"  Grid {i}: ${p:,.2f}")

    # Verify geometric spacing (constant ratio)
    ratios = [prices[i + 1] / prices[i] for i in range(len(prices) - 1)]
    print(f"\nPrice ratios (should be constant):")
    for i, r in enumerate(ratios):
        print(f"  Grid {i} -> {i+1}: {r:.6f}")

    # Check if all ratios are approximately equal
    avg_ratio = sum(ratios) / len(ratios)
    max_deviation = max(abs(r - avg_ratio) for r in ratios)
    print(f"\nAverage ratio: {avg_ratio:.6f}")
    print(f"Max deviation: {max_deviation:.8f}")

    assert max_deviation < 1e-6, "Geometric grid spacing is not constant!"
    print("[PASS] Geometric grid test PASSED")


def test_arithmetic_grid():
    """Test arithmetic grid generation."""
    print("\n" + "=" * 80)
    print("TEST 2: Arithmetic Grid Generation (等差网格)")
    print("=" * 80)

    config = NeutralGridConfig(
        lower_price=90000.0,
        upper_price=110000.0,
        grid_count=10,
        mode="arithmetic",
        total_investment=10000.0,
        initial_position_pct=0.0,
        enable_console_log=False,
    )

    manager = NeutralGridManager(config)
    prices = manager.generate_grid_prices()

    print(f"Generated {len(prices)} price points:")
    for i, p in enumerate(prices):
        print(f"  Grid {i}: ${p:,.2f}")

    # Verify arithmetic spacing (constant difference)
    diffs = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    print(f"\nPrice differences (should be constant):")
    for i, d in enumerate(diffs):
        print(f"  Grid {i} -> {i+1}: ${d:,.2f}")

    # Check if all diffs are approximately equal
    avg_diff = sum(diffs) / len(diffs)
    max_deviation = max(abs(d - avg_diff) for d in diffs)
    print(f"\nAverage diff: ${avg_diff:,.2f}")
    print(f"Max deviation: ${max_deviation:.2f}")

    assert max_deviation < 0.01, "Arithmetic grid spacing is not constant!"
    print("[PASS] Arithmetic grid test PASSED")


def test_grid_setup():
    """Test grid setup and initial order placement."""
    print("\n" + "=" * 80)
    print("TEST 3: Grid Setup and Order Placement")
    print("=" * 80)

    config = NeutralGridConfig(
        lower_price=90000.0,
        upper_price=110000.0,
        grid_count=10,
        mode="geometric",
        total_investment=10000.0,
        initial_position_pct=0.5,  # 50% initial position
        enable_console_log=True,
    )

    manager = NeutralGridManager(config)
    current_price = 100000.0  # Price in the middle

    manager.setup_grid(current_price)

    # Check state
    state = manager.get_current_state()
    stats = manager.get_statistics()

    print(f"\nGrid state after setup:")
    print(f"  Total grids: {len(state['grid_prices'])}")
    print(f"  Pending orders: {len(state['pending_orders'])}")
    print(f"  Initial positions: {len(state['positions'])}")
    print(f"  Total position BTC: {stats['total_position_btc']:.6f}")
    print(f"  Total position USD: ${stats['total_position_value_usd']:,.2f}")

    # Verify buy/sell order placement
    buy_orders = [o for o in state['pending_orders'] if o['direction'] == 'buy']
    sell_orders = [o for o in state['pending_orders'] if o['direction'] == 'sell']

    print(f"\nBuy orders: {len(buy_orders)} (should be below current price)")
    print(f"Sell orders: {len(sell_orders)} (should be above current price)")

    # Check that all buy orders are below current price
    for o in buy_orders:
        assert o['price'] < current_price, f"Buy order at ${o['price']} is not below current price ${current_price}"

    # Check that all sell orders are above current price
    for o in sell_orders:
        assert o['price'] > current_price, f"Sell order at ${o['price']} is not above current price ${current_price}"

    print("[PASS] Grid setup test PASSED")


def test_order_execution():
    """Test order execution and re-entry logic."""
    print("\n" + "=" * 80)
    print("TEST 4: Order Execution and Re-entry")
    print("=" * 80)

    config = NeutralGridConfig(
        lower_price=90000.0,
        upper_price=110000.0,
        grid_count=10,
        mode="geometric",
        total_investment=10000.0,
        initial_position_pct=0.0,  # Start from scratch
        enable_console_log=True,
    )

    manager = NeutralGridManager(config)
    current_price = 100000.0

    manager.setup_grid(current_price)

    print("\n" + "-" * 80)
    print("Simulating price movement and order fills...")
    print("-" * 80)

    # Simulate price drop - should trigger buy order
    print("\n[Simulation] Price drops to $95,000")
    triggered = manager.check_order_triggers(bar_high=100000, bar_low=95000)

    if triggered:
        print(f"[OK] Buy order triggered at grid {triggered.grid_index} @ ${triggered.price:,.2f}")
        manager.on_order_filled(triggered)

        # Check that:
        # 1. Position was added
        # 2. Sell order was placed at next grid
        # 3. Buy order was re-placed at current grid
        state = manager.get_current_state()
        stats = manager.get_statistics()

        print(f"\nState after buy fill:")
        print(f"  Positions: {len(state['positions'])}")
        print(f"  Pending orders: {len(state['pending_orders'])}")
        print(f"  Total buy volume: {stats['total_buy_volume']:.6f} BTC")

        # Find the new sell order
        sell_orders = [o for o in state['pending_orders'] if o['direction'] == 'sell']
        buy_orders = [o for o in state['pending_orders'] if o['direction'] == 'buy']

        print(f"\nOrders after buy fill:")
        print(f"  Buy orders: {len(buy_orders)}")
        print(f"  Sell orders: {len(sell_orders)}")

        # Verify sell order was placed at grid_index + 1
        expected_sell_grid = triggered.grid_index + 1
        sell_at_expected_grid = any(
            o['grid_index'] == expected_sell_grid and o['direction'] == 'sell'
            for o in state['pending_orders']
        )
        assert sell_at_expected_grid, f"Sell order not found at grid {expected_sell_grid}"
        print(f"[OK] Sell order placed at grid {expected_sell_grid} (pairing)")

        # Verify buy order was re-placed at same grid
        buy_at_same_grid = any(
            o['grid_index'] == triggered.grid_index and o['direction'] == 'buy'
            for o in state['pending_orders']
        )
        assert buy_at_same_grid, f"Buy order not re-placed at grid {triggered.grid_index}"
        print(f"[OK] Buy order re-placed at grid {triggered.grid_index} (re-entry)")

        # Simulate price rise - should trigger sell order
        print("\n[Simulation] Price rises to $102,000")
        triggered_sell = manager.check_order_triggers(bar_high=102000, bar_low=95000)

        if triggered_sell and triggered_sell.direction == "sell":
            print(f"[OK] Sell order triggered at grid {triggered_sell.grid_index} @ ${triggered_sell.price:,.2f}")
            manager.on_order_filled(triggered_sell)

            stats = manager.get_statistics()
            print(f"\nState after sell fill:")
            print(f"  Total PnL: ${stats['total_pnl']:,.2f}")
            print(f"  Total fees: ${stats['total_fees']:,.2f}")
            print(f"  Net PnL: ${stats['net_pnl']:,.2f}")
            print(f"  Total trades: {stats['total_trades']}")

            assert stats['total_pnl'] > 0, "PnL should be positive after buy-sell cycle"
            print("[PASS] PnL calculation test PASSED")

    print("[PASS] Order execution test PASSED")


def test_grid_pairing():
    """Test that buy-sell pairing uses adjacent grids."""
    print("\n" + "=" * 80)
    print("TEST 5: Grid Pairing (Adjacent Grids)")
    print("=" * 80)

    config = NeutralGridConfig(
        lower_price=90000.0,
        upper_price=110000.0,
        grid_count=20,
        mode="geometric",
        total_investment=10000.0,
        initial_position_pct=0.0,
        enable_console_log=False,
    )

    manager = NeutralGridManager(config)
    manager.setup_grid(100000.0)

    # Manually trigger a buy at grid 5
    buy_order = next(o for o in manager.pending_orders if o.direction == "buy" and o.grid_index == 5)
    manager.on_order_filled(buy_order)

    # Check that sell order was placed at grid 6 (not grid 5)
    state = manager.get_current_state()
    sell_at_grid_6 = any(
        o['grid_index'] == 6 and o['direction'] == 'sell'
        for o in state['pending_orders']
    )

    print(f"Buy filled at grid 5")
    print(f"Sell order placed at grid 6: {sell_at_grid_6}")

    assert sell_at_grid_6, "Sell order should be at grid_index + 1"

    # Calculate profit per grid
    buy_price = manager.grid_prices[5]
    sell_price = manager.grid_prices[6]
    spacing_pct = (sell_price - buy_price) / buy_price * 100

    print(f"\nPairing:")
    print(f"  Buy at grid 5: ${buy_price:,.2f}")
    print(f"  Sell at grid 6: ${sell_price:,.2f}")
    print(f"  Profit per grid: {spacing_pct:.2f}%")

    print("[PASS] Grid pairing test PASSED")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Neutral Grid Test Suite")
    print("=" * 80)

    try:
        test_geometric_grid()
        test_arithmetic_grid()
        test_grid_setup()
        test_order_execution()
        test_grid_pairing()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED [OK]")
        print("=" * 80 + "\n")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
