"""Test live dashboard with real dryRun data."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd

from data import DataManager
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner

# Configuration
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
START = pd.Timestamp("2025-01-19", tz="UTC")
END = pd.Timestamp("2025-01-20", tz="UTC")  # Short run for testing
SUPPORT = 56000.0
RESISTANCE = 72000.0
REGIME = "BULLISH_RANGE"

# Output paths
BASE_DIR = Path(__file__).parent.parent
STATE_DIR = BASE_DIR / "state"
RESULTS_DIR = BASE_DIR / "run" / "results_live_dashboard_test"

print("="*80)
print("Testing Live Dashboard with DryRun Data")
print("="*80)
print(f"Symbol: {SYMBOL}")
print(f"Period: {START} to {END}")
print(f"S/R: ${SUPPORT:,.0f} / ${RESISTANCE:,.0f}")
print(f"Regime: {REGIME}")
print()

# Create config
config = TaoGridLeanConfig(
    support=SUPPORT,
    resistance=RESISTANCE,
    regime=REGIME,
    initial_cash=100000.0,
    leverage=5.0,
    enable_console_log=False,  # Disable console spam
)

# Create runner with live_status enabled
runner = SimpleLeanRunner(
    config=config,
    symbol=SYMBOL,
    timeframe=TIMEFRAME,
    start_date=START,
    end_date=END,
    output_dir=RESULTS_DIR,
    verbose=True,
    collect_equity_detail=True,
    # Enable live status output
    enable_live_status=True,
    live_status_file=STATE_DIR / "dryrun_status.json",
    live_status_update_frequency=10,  # Update every 10 bars (every 10 minutes for 1m data)
)

print("Starting dryRun backtest...")
print(f"Live status will be written to: {STATE_DIR / 'dryrun_status.json'}")
print(f"Update frequency: every 10 bars")
print()

# Run backtest
result = runner.run()

print()
print("="*80)
print("Backtest Complete!")
print("="*80)
print(f"Total Return: {result['total_return']*100:.2f}%")
print(f"Total Trades: {result['total_trades']}")
print(f"Final Equity: ${result['final_equity']:,.2f}")
print()
print(f"Live status file: {STATE_DIR / 'dryrun_status.json'}")
print(f"Results saved to: {RESULTS_DIR}")
print()
print("Next steps:")
print("1. Check the live_status.json file")
print("2. Visit http://127.0.0.1:8000 to see the dashboard")
print("3. Refresh the page to see updated data")
print("="*80)
