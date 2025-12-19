"""
Quick verification test for BUY order recording fix.
Runs a short backtest (2 days) to verify BUY orders are recorded.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig

# Short test config
config = TaoGridLeanConfig(
    name="BUY Order Fix Test",
    description="Quick test to verify BUY orders are recorded",
    support=107000.0,
    resistance=123000.0,
    regime="NEUTRAL_RANGE",
    grid_layers_buy=40,
    grid_layers_sell=40,
    weight_k=0.0,
    spacing_multiplier=1.0,
    min_return=0.0012,
    maker_fee=0.0002,
    inventory_skew_k=0.5,
    inventory_capacity_threshold_pct=1.0,
    enable_mr_trend_factor=False,
    enable_breakout_risk_factor=True,
    breakout_band_atr_mult=1.0,
    breakout_band_pct=0.008,
    breakout_trend_weight=0.7,
    breakout_buy_k=2.0,
    breakout_buy_floor=0.5,
    breakout_block_threshold=0.9,
    enable_range_pos_asymmetry_v2=True,
    range_top_band_start=0.45,
    range_buy_k=0.2,
    range_buy_floor=0.2,
    range_sell_k=1.5,
    range_sell_cap=1.5,
    risk_budget_pct=1.0,
    enable_throttling=True,
    initial_cash=100000.0,
    leverage=50.0,
    enable_mm_risk_zone=False,
    enable_console_log=False,  # Disable logs for speed
)

# Run short backtest (2 days only)
runner = SimpleLeanRunner(
    config=config,
    symbol="BTCUSDT",
    timeframe="1m",
    start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
    end_date=datetime(2025, 9, 28, tzinfo=timezone.utc),  # Only 2 days
    verbose=True,
)

print("Running short backtest to verify BUY order recording...")
results = runner.run()

# Check results
import pandas as pd
orders_df = pd.DataFrame(runner.orders)

print("\n" + "=" * 80)
print("VERIFICATION RESULTS")
print("=" * 80)

if orders_df.empty:
    print("ERROR: No orders recorded!")
else:
    buy_count = (orders_df['direction'] == 'buy').sum()
    sell_count = (orders_df['direction'] == 'sell').sum()

    print(f"\nTotal orders: {len(orders_df)}")
    print(f"  - BUY orders: {buy_count}")
    print(f"  - SELL orders: {sell_count}")

    if buy_count > 0 and sell_count > 0:
        print("\n[SUCCESS] Both BUY and SELL orders are being recorded!")

        # Show sample orders
        print("\nSample BUY orders:")
        buy_orders = orders_df[orders_df['direction'] == 'buy'].head(3)
        for idx, row in buy_orders.iterrows():
            print(f"  [{row['timestamp']}] BUY L{row['level']+1} @ ${row['price']:,.0f}, size={row['size']:.4f} BTC, cost=${row['cost']:,.2f}")

        print("\nSample SELL orders:")
        sell_orders = orders_df[orders_df['direction'] == 'sell'].head(3)
        for idx, row in sell_orders.iterrows():
            proceeds_col = 'proceeds' if 'proceeds' in row else 'cost'
            proceeds = row[proceeds_col] if proceeds_col in row else 0
            print(f"  [{row['timestamp']}] SELL L{row['level']+1} @ ${row['price']:,.0f}, size={row['size']:.4f} BTC, proceeds=${proceeds:,.2f}")

        # Check for required columns
        required_cols = ['timestamp', 'direction', 'size', 'price', 'level', 'market_price', 'commission', 'slippage']
        missing_cols = [col for col in required_cols if col not in orders_df.columns]
        if missing_cols:
            print(f"\n[WARNING] Missing columns: {missing_cols}")
        else:
            print("\n[OK] All required columns present")

    elif buy_count == 0:
        print("\n[FAILED] No BUY orders recorded (fix did not work)")
    elif sell_count == 0:
        print("\n[FAILED] No SELL orders recorded (regression)")

print("\n" + "=" * 80)
