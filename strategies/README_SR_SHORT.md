# SR Short 4H Resistance Strategy

A multi-timeframe short-only strategy that detects resistance zones on 4H timeframe and executes trades on lower timeframes.

## Overview

This strategy replicates the Pine Script "SR空单策略v1" logic:

1. **Multi-timeframe detection**: Resamples input data to 4H for zone detection
2. **Resistance zones**: Uses pivot highs (leftLen=90, rightLen=10) to identify resistance zones
3. **Zone merging**: Merges nearby zones based on ATR tolerance
4. **Signal types**: 
   - Standard touch: Price touches zone and closes bearish
   - 2B fakeout: Price breaks above zone but closes back down
5. **Multiple positions**: Tracks multiple concurrent virtual trades independently
6. **Risk management**: 
   - Risk-based position sizing
   - Break-even logic (partial close + move SL to entry)
   - Three-stage profit taking (TP1/TP2/TP3)

## Usage

```python
from backtesting import Backtest
from strategies.sr_short_4h_resistance import SRShort4HResistance
import pandas as pd

# Load your OHLCV data (15m or lower timeframe)
df = pd.read_csv("data/raw/btcusdt_15m.csv", index_col=0, parse_dates=True)
df.columns = ["Open", "High", "Low", "Close", "Volume"]

# Create backtest
bt = Backtest(
    df,
    SRShort4HResistance,
    cash=10000,
    commission=0.001,  # 0.1%
    trade_on_close=True,
    exclusive_orders=False,
)

# Run with default parameters
stats = bt.run()

# Or customize parameters
stats = bt.run(
    left_len=90,
    right_len=10,
    merge_atr_mult=3.5,
    break_tol_atr=0.5,
    min_touches=1,
    max_retries=3,
    global_cd=30,
    price_filter_pct=1.5,
    min_position_distance_pct=1.5,
    max_positions=5,
    risk_per_trade_pct=0.5,
    leverage=5.0,
    strategy_sl_percent=2.0,
    breakeven_ratio=2.33,
    breakeven_close_pct=30.0,
    tp1_atr_mult=3.0,
    tp1_close_pct=40.0,
    tp2_atr_mult=5.0,
    tp2_close_pct=40.0,
    tp3_atr_mult=8.0,
    tp3_close_pct=20.0,
)

# View results
print(stats)
bt.plot()
```

## Parameters

### Zone Detection
- `left_len` (90): Left lookback for pivot detection
- `right_len` (10): Right confirmation for pivot detection
- `merge_atr_mult` (3.5): ATR multiplier for zone merging tolerance
- `break_tol_atr` (0.5): ATR multiplier for zone break tolerance
- `min_touches` (1): Minimum touches required for zone to generate signals
- `max_retries` (3): Maximum failed attempts per zone before disabling

### Signal Filtering
- `global_cd` (30): Time cooldown between signals (bars)
- `price_filter_pct` (1.5): Minimum price movement % since last signal
- `min_position_distance_pct` (1.5): Minimum distance % between positions
- `max_positions` (5): Maximum concurrent positions

### Position Sizing
- `risk_per_trade_pct` (0.5): Risk % per trade of equity
- `leverage` (5.0): Maximum leverage multiplier
- `strategy_sl_percent` (2.0): Stop loss % above zone top

### Exit Strategy
- `breakeven_ratio` (2.33): Profit ratio to trigger break-even
- `breakeven_close_pct` (30.0): % to close at break-even
- `tp1_atr_mult` (3.0): TP1 ATR multiplier
- `tp1_close_pct` (40.0): TP1 close %
- `tp2_atr_mult` (5.0): TP2 ATR multiplier
- `tp2_close_pct` (40.0): TP2 close %
- `tp3_atr_mult` (8.0): TP3 ATR multiplier
- `tp3_close_pct` (20.0): TP3 close %

**Note**: TP1% + TP2% + TP3% must equal 100%

## Implementation Details

### Multi-timeframe Handling
- Input data is resampled to 4H using `resample_ohlcv()`
- Pivot highs and zones are detected on 4H timeframe
- Signals are generated when 4H bars touch zones
- Entries/exits execute on the original timeframe bars

### Virtual Trade Tracking
- Each signal creates a `VirtualTrade` object
- Trades are tracked independently with their own SL/TP levels
- The strategy aggregates virtual trades into a single backtesting.py position
- Position size is adjusted to match total remaining quantity of active trades

### Exit Logic
1. **Stop Loss**: Triggered when price hits SL (original or moved to entry after BE)
2. **Break-even**: When price reaches breakeven_price, close 30% and move SL to entry
3. **TP1**: After break-even, close 40% of remaining at TP1
4. **TP2**: After TP1, close 40% of remaining at TP2
5. **TP3**: After TP2, close remaining 20% at TP3

## Limitations

- backtesting.py only supports one position at a time, so multiple virtual trades are aggregated
- Zone detection happens on 4H bars, which may cause slight delays in signal generation
- Pivot detection requires sufficient historical data (left_len + right_len bars)

## Files

- `strategies/sr_short_4h_resistance.py`: Main strategy implementation
- `strategies/example_sr_short_usage.py`: Example usage script

