"""
Debug neutral grid to find position matching issue.
"""

import sys
from pathlib import Path
import pandas as pd

taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from data import DataManager
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing
from algorithms.taogrid.neutral_grid_config import NeutralGridConfig
from algorithms.taogrid.neutral_grid import NeutralGridManager

# Simple test with just 10 grids
config = NeutralGridConfig(
    lower_price=85000.0,
    upper_price=95000.0,
    grid_count=10,
    mode="geometric",
    total_investment=10000.0,
    initial_position_pct=0.0,  # No initial position for clarity
    leverage=1.0,  # No leverage for clarity
    enable_console_log=True,  # Enable logs
)

manager = NeutralGridManager(config)
manager.setup_grid(current_price=90000.0)

print("\n" + "=" * 80)
print("Initial State")
print("=" * 80)
print(f"Grid prices: {[f'${p:,.0f}' for p in manager.grid_prices]}")
print(f"Pending orders: {len(manager.pending_orders)}")

# Simulate some price movements
print("\n" + "=" * 80)
print("Simulation")
print("=" * 80)

# Price drops - trigger buy
print("\n1. Price drops to $87,000 (should trigger buy)")
triggered = manager.check_order_triggers(bar_high=90000, bar_low=87000)
if triggered:
    print(f"   Triggered: {triggered.direction} at grid {triggered.grid_index} @ ${triggered.price:,.2f}")
    manager.on_order_filled(triggered)
    print(f"   Positions: {len(manager.positions)}")
    print(f"   Pending orders: {len(manager.pending_orders)}")

    # Check position details
    for pos in manager.positions:
        print(f"     Position: grid {pos.grid_index}, size {pos.size:.6f}, paired_grid {pos.paired_grid_index}")

# Price rises - trigger sell
print("\n2. Price rises to $90,500 (should trigger sell)")
triggered = manager.check_order_triggers(bar_high=90500, bar_low=87000)
if triggered:
    print(f"   Triggered: {triggered.direction} at grid {triggered.grid_index} @ ${triggered.price:,.2f}")
    manager.on_order_filled(triggered)
    print(f"   Positions: {len(manager.positions)}")
    print(f"   Pending orders: {len(manager.pending_orders)}")

# Check final state
print("\n" + "=" * 80)
print("Final State")
print("=" * 80)
stats = manager.get_statistics()
print(f"Buy volume: {stats['total_buy_volume']:.6f} BTC")
print(f"Sell volume: {stats['total_sell_volume']:.6f} BTC")
print(f"Net position: {stats['total_buy_volume'] - stats['total_sell_volume']:.6f} BTC")
print(f"Actual position: {stats['total_position_btc']:.6f} BTC")
print(f"Position count: {stats['positions_count']}")

if abs((stats['total_buy_volume'] - stats['total_sell_volume']) - stats['total_position_btc']) > 0.001:
    print("\n[ERROR] Position mismatch detected!")
    print("Positions:")
    for pos in manager.positions:
        print(f"  Grid {pos.grid_index}: size {pos.size:.6f}, paired_grid {pos.paired_grid_index}")
