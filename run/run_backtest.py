"""
Simple backtest script for TaoQuant (New Clean Architecture).

This is the ONLY file users need to modify for basic backtests.
All complexity is hidden in the orchestration layer.

Usage:
    python run/run_backtest.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd

# Data
from data import DataManager

# Strategy
from strategies.signal_based.sr_short import SRShortConfig, SRShortStrategy

# Execution
from execution.engines.base import BacktestConfig
from execution.engines.vectorbt_engine import VectorBTEngine

# Orchestration
from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig

# =============================================================================
# CONFIGURATION - Modify this section only
# =============================================================================

# Data parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-7-01", tz="UTC")
END = pd.Timestamp("2025-10-01", tz="UTC")
SOURCE = "okx"  # 'okx', 'binance', or 'csv'

# Strategy parameters
STRATEGY_CONFIG = SRShortConfig(
    name="SR Short 4H",
    description="Short-only strategy based on 4H resistance zones",
    # Zone detection (optimized for more signals)
    left_len=30,  # Reduced from 90: 30*4h = 120h = 5 days lookback (more sensitive)
    right_len=5,  # Reduced from 10: 5*4h = 20h confirmation (faster confirmation)
    merge_atr_mult=3.5,
    # Entry filters
    min_touches=1,
    max_retries=3,
    # Risk management
    risk_per_trade_pct=0.5,  # 0.5% risk per trade
    leverage=5.0,
    stop_loss_atr_mult=3.0,
)

# Backtest parameters
BACKTEST_CONFIG = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,  # 0.1%
    slippage=0.0005,   # 0.05%
    leverage=5.0,
)

# Output - use unified results directory
from utils.paths import get_results_dir
OUTPUT_DIR = get_results_dir()

# =============================================================================
# EXECUTION - No need to modify below
# =============================================================================

if __name__ == "__main__":
    # Initialize components
    data_manager = DataManager()
    strategy = SRShortStrategy(STRATEGY_CONFIG)
    engine = VectorBTEngine()
    runner = BacktestRunner(data_manager)

    # Run backtest
    result = runner.run(BacktestRunConfig(
        # Data
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=START,
        end=END,
        source=SOURCE,
        # Strategy
        strategy=strategy,
        # Execution
        engine=engine,
        backtest_config=BACKTEST_CONFIG,
        # Output
        output_dir=OUTPUT_DIR,
        save_results=True,
        save_trades=True,
        save_equity=True,
        save_metrics=True,
        save_plot=True,  # Generate interactive plot
    ))

    print("\n[Success] Backtest completed successfully!")
    print(f"[Results] Results saved to: {OUTPUT_DIR}")
    print(f"[Metrics] Total Return: {result.metrics['total_return']:.2%}")
    print(f"[Metrics] Max Drawdown: {result.metrics['max_drawdown']:.2%}")
    print(f"[Metrics] Sharpe Ratio: {result.metrics['sharpe_ratio']:.2f}")
    print(f"[Metrics] Win Rate: {result.metrics['win_rate']:.2%}")
