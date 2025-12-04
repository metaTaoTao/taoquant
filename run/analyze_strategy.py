"""
Strategy Analysis Script

Analyze why:
1. So few trades were executed
2. Zero-cost position management is not implemented
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from utils.resample import resample_ohlcv
from analytics.indicators.sr_zones import compute_sr_zones

# Load data
print("=" * 80)
print("STRATEGY ANALYSIS")
print("=" * 80)

data_manager = DataManager()
# Use cached data if available, otherwise fetch
try:
    data = data_manager.get_klines(
        symbol="BTCUSDT",
        timeframe="15m",
        start="2025-10-01",
        end="2025-11-30",  # Use cached range
        source="okx",
    )
except Exception as e:
    print(f"⚠️  Error fetching data: {e}")
    print("   Using cached data from previous run...")
    # Try to load from cache directly
    import pickle
    cache_path = Path("data/cache/okx_btcusdt_15m.parquet")
    if cache_path.exists():
        data = pd.read_parquet(cache_path)
        data = data[(data.index >= "2025-10-01") & (data.index <= "2025-11-30")]
    else:
        raise

print(f"\n[Data] Data loaded: {len(data)} bars from {data.index[0]} to {data.index[-1]}")

# Create strategy
config = SRShortConfig(
    name="SR Short 4H",
    description="Short resistance zones on 4H",
    left_len=90,
    right_len=10,
    min_touches=1,
    risk_per_trade_pct=0.5,
    leverage=5.0,
    stop_loss_atr_mult=3.0,
)

strategy = SRShortStrategy(config)

# Run strategy
print("\n[Strategy] Running strategy...")
data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)

print(f"   [OK] Generated {signals['entry'].sum()} entry signals")
print(f"   [OK] Generated {signals['exit'].sum()} exit signals")

# ============================================================================
# Analysis 1: Why so few trades?
# ============================================================================
print("\n" + "=" * 80)
print("ANALYSIS 1: Why so few trades?")
print("=" * 80)

# 1a. Check S/R zones found
print("\n1a. S/R Zones Detection:")
data_4h = resample_ohlcv(data, '4h')
zones_4h = compute_sr_zones(
    data_4h,
    left_len=config.left_len,
    right_len=config.right_len,
    merge_atr_mult=config.merge_atr_mult,
)

# Count unique zones
active_zones = zones_4h[zones_4h['zone_is_broken'] == False]
unique_zones = active_zones.drop_duplicates(subset=['zone_top', 'zone_bottom'])
print(f"   • Total 4H bars: {len(data_4h)}")
print(f"   • Active zones found: {len(unique_zones)}")
print(f"   • Total zone touches: {zones_4h['zone_touches'].sum()}")

# Show zone details
if len(unique_zones) > 0:
    print("\n   Zone Details:")
    for idx, (time, zone) in enumerate(unique_zones.iterrows(), 1):
        print(f"   Zone {idx}: Top={zone['zone_top']:.2f}, Bottom={zone['zone_bottom']:.2f}, "
              f"Touches={zone['zone_touches']}, Broken={zone['zone_is_broken']}")

# 1b. Check 15m touches
print("\n1b. 15m Bar Touches:")
has_zone = data_with_indicators['zone_top'].notna() & data_with_indicators['zone_bottom'].notna()
zone_active = has_zone & (~data_with_indicators['zone_is_broken'].fillna(False).astype(bool))
zone_qualified = zone_active & (data_with_indicators['zone_touches'] >= config.min_touches)

inside_zone = (
    (data_with_indicators['close'] >= data_with_indicators['zone_bottom']) &
    (data_with_indicators['close'] <= data_with_indicators['zone_top'])
)

entry_condition = zone_qualified & inside_zone

print(f"   • 15m bars with zone data: {has_zone.sum()}")
print(f"   • 15m bars with active zones: {zone_active.sum()}")
print(f"   • 15m bars with qualified zones (touches >= {config.min_touches}): {zone_qualified.sum()}")
print(f"   • 15m bars inside zone: {inside_zone.sum()}")
print(f"   • 15m bars meeting entry condition: {entry_condition.sum()}")

# Check signal distribution
if entry_condition.sum() > 0:
    entry_times = data_with_indicators[entry_condition].index
    print(f"\n   Entry Signal Times:")
    for i, time in enumerate(entry_times[:10], 1):  # Show first 10
        zone_top = data_with_indicators.loc[time, 'zone_top']
        zone_bottom = data_with_indicators.loc[time, 'zone_bottom']
        close = data_with_indicators.loc[time, 'close']
        touches = data_with_indicators.loc[time, 'zone_touches']
        print(f"   {i}. {time}: Close={close:.2f} in zone [{zone_bottom:.2f}, {zone_top:.2f}], "
              f"Touches={touches}")
    if len(entry_times) > 10:
        print(f"   ... and {len(entry_times) - 10} more")

# 1c. Check why VectorBT only executed 1 trade
print("\n1c. VectorBT Execution Analysis:")
print(f"   • Entry signals generated: {signals['entry'].sum()}")
print("   • Issue: VectorBT's from_signals may only execute first signal")
print("   • If a position is already open, subsequent entry signals are ignored")
print("   • Need to check if positions are being closed before new entries")

# Check if there are exit signals
if signals['exit'].sum() > 0:
    print(f"   • Exit signals: {signals['exit'].sum()}")
else:
    print("   • [WARNING] No exit signals! Positions only close at SL/TP")
    print("   • Current strategy: exit_signal = False (exits handled by engine)")
    print("   • Engine only has SL (3 * ATR), no TP defined")

# ============================================================================
# Analysis 2: Zero-cost position management
# ============================================================================
print("\n" + "=" * 80)
print("ANALYSIS 2: Zero-cost position management")
print("=" * 80)

print("\n2a. Current Exit Logic:")
print("   • Strategy exit_signal: All False (exits handled by engine)")
print("   • Engine: VectorBT from_signals with SL only")
print(f"   • SL distance: {config.stop_loss_atr_mult} * ATR(200)")
print("   • TP: [NOT IMPLEMENTED]")

print("\n2b. Zero-cost Position Management:")
print("   • Concept: At TP1, close 50% position, move SL to entry (breakeven)")
print("   • Remaining 50% position is 'zero-cost' (no risk)")
print("   • Current implementation: [NOT IMPLEMENTED]")

print("\n2c. Why it's not working:")
print("   • VectorBT's from_signals doesn't support partial exits")
print("   • No TP levels defined in strategy")
print("   • No logic to move SL to breakeven after TP1")
print("   • Need custom position management logic")

# Check current trade
print("\n2d. Current Trade Analysis:")
from utils.paths import get_results_dir
trades_path = get_results_dir() / "SR Short 4H_BTCUSDT_15m_trades.csv"
if trades_path.exists():
    trades_df = pd.read_csv(trades_path)
    if len(trades_df) > 0:
        trade = trades_df.iloc[0]
        # Handle different column names
        entry_time_col = 'entry_time' if 'entry_time' in trade.index else 'Entry Timestamp'
        exit_time_col = 'exit_time' if 'exit_time' in trade.index else 'Exit Timestamp'
        entry_price_col = 'entry_price' if 'entry_price' in trade.index else 'Avg. Entry Price'
        exit_price_col = 'exit_price' if 'exit_price' in trade.index else 'Avg. Exit Price'
        return_pct_col = 'return_pct' if 'return_pct' in trade.index else 'Return'
        
        entry_time = pd.to_datetime(trade[entry_time_col])
        exit_time = pd.to_datetime(trade[exit_time_col])
        entry_price = trade[entry_price_col]
        exit_price = trade[exit_price_col]
        return_pct = trade[return_pct_col]
    
    print(f"   • Entry: {entry_time} @ {entry_price:.2f}")
    print(f"   • Exit: {exit_time} @ {exit_price:.2f}")
    print(f"   • Return: {return_pct*100:.2f}%")
    print(f"   • Duration: {exit_time - entry_time}")
    
    # Calculate what TP1 would have been
    atr_at_entry = data_with_indicators.loc[entry_time, 'atr'] if entry_time in data_with_indicators.index else None
    if atr_at_entry and not pd.isna(atr_at_entry):
        # For short: TP1 = entry - 1 * ATR (price goes down)
        tp1_price = entry_price - (1.0 * atr_at_entry)
        tp1_pct = ((entry_price - tp1_price) / entry_price) * 100
        print(f"\n   • If TP1 = entry - 1*ATR:")
        print(f"     TP1 price: {tp1_price:.2f}")
        print(f"     TP1 return: {tp1_pct:.2f}%")
        print(f"     Would have hit TP1: {'Yes' if exit_price <= tp1_price else 'No'}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

print("\n1. To increase trade frequency:")
print("   a. Reduce left_len/right_len to find more zones")
print("   b. Reduce min_touches requirement")
print("   c. Implement position filtering to allow multiple positions")
print("   d. Check if VectorBT is ignoring signals when position is open")

print("\n2. To implement zero-cost position management:")
print("   a. Add TP1/TP2 levels to strategy config")
print("   b. Implement partial exit logic (close 50% at TP1)")
print("   c. Move SL to breakeven after TP1")
print("   d. Use custom position management or switch to event-driven engine")
print("   e. Consider using VectorBT's order-based approach for more control")

print("\n" + "=" * 80)

