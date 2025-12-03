"""
Example usage of SR Short 4H Resistance Strategy

This script demonstrates how to use the SRShort4HResistance strategy
with backtesting.py.
"""

from __future__ import annotations

import pandas as pd
from backtesting import Backtest

from strategies.sr_short_4h_resistance import SRShort4HResistance

# Example: Load your OHLCV data
# df = pd.read_csv("data/raw/btcusdt_15m.csv", index_col=0, parse_dates=True)
# df.columns = ["Open", "High", "Low", "Close", "Volume"]

# Or use DataManager
# from data import DataManager
# dm = DataManager()
# df = dm.get_data("BTCUSDT", "15m", start=..., end=...)

# Create backtest instance
# bt = Backtest(
#     df,
#     SRShort4HResistance,
#     cash=10000,
#     commission=0.001,  # 0.1%
#     trade_on_close=True,
#     exclusive_orders=False,  # Allow multiple orders
# )

# Run backtest with custom parameters
# stats = bt.run(
#     left_len=90,
#     right_len=10,
#     merge_atr_mult=3.5,
#     break_tol_atr=0.5,
#     min_touches=1,
#     max_retries=3,
#     global_cd=30,
#     price_filter_pct=1.5,
#     min_position_distance_pct=1.5,
#     max_positions=5,
#     risk_per_trade_pct=0.5,
#     leverage=5.0,
#     strategy_sl_percent=2.0,
#     breakeven_ratio=2.33,
#     breakeven_close_pct=30.0,
#     tp1_atr_mult=3.0,
#     tp1_close_pct=40.0,
#     tp2_atr_mult=5.0,
#     tp2_close_pct=40.0,
#     tp3_atr_mult=8.0,
#     tp3_close_pct=20.0,
# )

# Print results
# print(stats)

# Plot results
# bt.plot()

if __name__ == "__main__":
    print("This is an example usage file.")
    print("Uncomment and modify the code above to run a backtest.")

