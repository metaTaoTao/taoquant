"""
Debug position tracking to understand why multiple entries are allowed.
"""

import pandas as pd
import sys
sys.path.insert(0, 'D:/Projects/PythonProjects/taoquant')

from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from execution.engines.base import BacktestConfig
from pathlib import Path

print("=" * 80)
print("POSITION TRACKING DEBUG")
print("=" * 80)

# Initialize
data_manager = DataManager()

# Load data
data = data_manager.get_klines(
    symbol="BTCUSDT",
    timeframe="15m",
    start=pd.Timestamp("2025-07-01", tz="UTC"),
    end=pd.Timestamp("2025-10-01", tz="UTC"),
    source="okx"
)

print(f"\n[Data Loaded]")
print(f"Period: {data.index[0]} to {data.index[-1]}")
print(f"Total bars: {len(data)}")

# Initialize strategy
strategy = SRShortStrategy(SRShortConfig(
    name="SR Short 4H",
    description="Short-only support/resistance zone strategy with multi-timeframe analysis (4H zones, 15m execution)",
    htf_timeframe="4h",
    htf_lookback=300,
    left_len=90,
    right_len=10,
    merge_atr_mult=3.5,
    min_touches=1,
    max_retries=3,
    price_filter_pct=1.5,
    min_position_distance_pct=1.5,
    risk_per_trade_pct=0.5,
    leverage=5.0,
    stop_loss_atr_mult=3.0,
    tp1_rr_ratio=2.33,
    tp1_exit_pct=0.3,
    trailing_offset_atr_mult=2.0,
    trailing_stop_atr_mult=5.0,
))

# Compute indicators
print(f"\n[Computing Indicators]")
data_with_indicators = strategy.compute_indicators(data)

# Generate signals
print(f"\n[Generating Signals]")
signals = strategy.generate_signals(data_with_indicators)

print(f"  Signals columns: {signals.columns.tolist()}")
print(f"  Signals shape: {signals.shape}")
print(f"  Signals head:")
print(signals.head())

# Calculate position sizes
print(f"\n[Calculating Position Sizes]")
backtest_config = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,
    slippage=0.0005,
    leverage=5.0,
)

# Mock equity series (start with initial cash)
equity = pd.Series(backtest_config.initial_cash, index=data_with_indicators.index)

position_sizes = strategy.calculate_position_size(
    data=data_with_indicators,
    equity=equity,
    base_size=1.0
)

# Now manually trace through the order generation
print(f"\n[Manual Order Generation Trace]")
print("=" * 80)

# Extract signals
entry_condition = signals['entry']
direction = signals['direction']

# Initialize tracking
orders = pd.Series(0.0, index=data_with_indicators.index)
order_types = pd.Series('', index=data_with_indicators.index)
positions = []
used_zones = set()

# Iterate through each bar
for i in range(len(data_with_indicators)):
    current_time = data_with_indicators.index[i]
    current_price = data_with_indicators['close'].iloc[i]
    current_atr = data_with_indicators['atr'].iloc[i]

    # Check for exits first (process existing positions)
    positions_to_remove = []

    for pos_idx, pos in enumerate(positions):
        # Calculate exit prices
        sl_price = pos['entry_price'] + (pos['entry_atr'] * strategy.config.stop_loss_atr_mult)
        # TP1 uses R:R ratio: if stop is 3 ATR and R:R is 2.33, then TP1 is 2.33 * 3 ATR = 6.99 ATR
        tp1_distance = pos['entry_atr'] * strategy.config.stop_loss_atr_mult * strategy.config.tp1_rr_ratio
        tp1_price = pos['entry_price'] - tp1_distance

        # Update highest profit for trailing stop
        if current_price < pos['highest_profit_price']:
            pos['highest_profit_price'] = current_price

        # Check TP1 (only if not already hit)
        if not pos['tp1_hit'] and current_price <= tp1_price:
            tp1_size = pos['entry_size'] * strategy.config.tp1_exit_pct
            orders.iloc[i] = tp1_size
            order_types.iloc[i] = 'TP1'
            pos['tp1_hit'] = True

            print(f"\n[{current_time}] TP1 HIT")
            print(f"  Price: ${current_price:,.2f}, TP1: ${tp1_price:,.2f}")
            print(f"  Closing: {tp1_size:.4f} BTC (30%)")
            print(f"  Remaining: {pos['entry_size'] * 0.7:.4f} BTC (70%)")
            print(f"  Positions list: {len(positions)} positions")
            continue

        # Check TP2 (trailing stop, only if TP1 hit)
        if pos['tp1_hit']:
            # Calculate trailing stop
            entry_atr = pos['entry_atr']
            trailing_stop_distance = entry_atr * strategy.config.trailing_stop_atr_mult
            trailing_offset = entry_atr * strategy.config.trailing_offset_atr_mult

            new_trailing_stop = pos['highest_profit_price'] + trailing_stop_distance - trailing_offset

            if pos['trailing_stop_price'] is None:
                pos['trailing_stop_price'] = new_trailing_stop
            else:
                pos['trailing_stop_price'] = max(pos['trailing_stop_price'], new_trailing_stop)

            if current_price >= pos['trailing_stop_price']:
                orders.iloc[i] = 1.0  # Close 100%
                order_types.iloc[i] = 'TP2'
                positions_to_remove.append(pos_idx)

                print(f"\n[{current_time}] TP2 HIT (Trailing Stop)")
                print(f"  Price: ${current_price:,.2f}, Trailing Stop: ${pos['trailing_stop_price']:,.2f}")
                print(f"  Closing: 1.0 (100% of remaining)")
                print(f"  Adding to positions_to_remove: index {pos_idx}")
                continue

        # Check SL (only if TP1 not hit)
        if not pos['tp1_hit']:
            if current_price >= sl_price:
                orders.iloc[i] = 1.0  # Close 100%
                order_types.iloc[i] = 'SL'
                positions_to_remove.append(pos_idx)

                print(f"\n[{current_time}] SL HIT")
                print(f"  Price: ${current_price:,.2f}, SL: ${sl_price:,.2f}")
                print(f"  Closing: 1.0 (100%)")
                print(f"  Adding to positions_to_remove: index {pos_idx}")
                continue

    # Remove exited positions
    if positions_to_remove:
        print(f"\n[{current_time}] REMOVING POSITIONS")
        print(f"  Before: {len(positions)} positions")
        print(f"  Removing indices: {positions_to_remove}")

        for pos_idx in reversed(positions_to_remove):
            pos = positions[pos_idx]
            if 'zone_key' in pos:
                used_zones.discard(pos['zone_key'])
                print(f"  Clearing zone_key: {pos['zone_key']}")
            positions.pop(pos_idx)

        print(f"  After: {len(positions)} positions")

    # Check for new entries
    if entry_condition.iloc[i]:
        zone_bottom_val = data_with_indicators['zone_bottom'].iloc[i] if 'zone_bottom' in data_with_indicators.columns else None
        zone_top_val = data_with_indicators['zone_top'].iloc[i] if 'zone_top' in data_with_indicators.columns else None

        print(f"\n[{current_time}] ENTRY CONDITION MET")
        print(f"  Price: ${current_price:,.2f}")
        print(f"  Zone: ${zone_bottom_val:,.2f} - ${zone_top_val:,.2f}")
        print(f"  Current positions: {len(positions)}")

        if len(positions) == 0:
            if pd.notna(zone_bottom_val) and pd.notna(zone_top_val):
                zone_key = (float(zone_bottom_val), float(zone_top_val))

                print(f"  Zone key: {zone_key}")
                print(f"  Used zones: {used_zones}")

                if zone_key not in used_zones:
                    entry_size = -1.0

                    positions.append({
                        'entry_idx': i,
                        'entry_price': current_price,
                        'entry_atr': current_atr,
                        'entry_size': abs(entry_size),
                        'tp1_hit': False,
                        'highest_profit_price': current_price,
                        'trailing_stop_price': None,
                        'zone_key': zone_key,
                    })

                    used_zones.add(zone_key)

                    orders.iloc[i] = entry_size
                    order_types.iloc[i] = 'ENTRY'

                    print(f"  [ENTRY ALLOWED] Position opened")
                    print(f"  Positions list now: {len(positions)} positions")
                else:
                    print(f"  [ENTRY BLOCKED] Zone already used")
            else:
                print(f"  [ENTRY BLOCKED] Zone data is NaN")
        else:
            print(f"  [ENTRY BLOCKED] Existing position(s): {len(positions)}")
            for idx, pos in enumerate(positions):
                print(f"    Position {idx}: Entry @ ${pos['entry_price']:,.2f}, TP1 hit: {pos['tp1_hit']}")

# Force close check
print(f"\n[End of Backtest]")
print(f"Positions remaining: {len(positions)}")
if positions:
    print(f"[WARNING] Force close would execute for {len(positions)} position(s):")
    for idx, pos in enumerate(positions):
        print(f"  Position {idx}: Entry @ ${pos['entry_price']:,.2f}, Size: {pos['entry_size']:.4f} BTC")
else:
    print(f"[OK] No positions remaining")

# Summary of orders
print(f"\n[Orders Summary]")
orders_df = pd.DataFrame({
    'timestamp': data_with_indicators.index,
    'price': data_with_indicators['close'],
    'orders': orders,
    'order_types': order_types
})

# Filter only actual orders (non-zero)
actual_orders = orders_df[(orders_df['orders'] != 0.0) & (orders_df['order_types'] != '')]
print(f"\nTotal orders: {len(actual_orders)}")
print("\nOrder details:")
print(actual_orders[['timestamp', 'price', 'orders', 'order_types']].to_string())

print("\n" + "=" * 80)
