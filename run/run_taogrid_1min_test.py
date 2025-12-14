"""
TaoGrid Strategy Backtest - 1min K-line Test.

Parameters:
- Period: 2025-07-10 to 2025-08-10 (1 month)
- Timeframe: 1min
- Support: 112,000
- Resistance: 123,000
- Min Return: 0.5%

Usage:
    python run/run_taogrid_1min_test.py
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

# TaoGrid Strategy
from strategies.signal_based.taogrid_strategy import (
    TaoGridConfig,
    TaoGridStrategy,
)

# Execution
from execution.engines.base import BacktestConfig
from execution.engines.vectorbt_engine import VectorBTEngine

# Orchestration
from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig

# =============================================================================
# CONFIGURATION
# =============================================================================

# Data Parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
START = pd.Timestamp("2025-07-10", tz="UTC")
END = pd.Timestamp("2025-08-10", tz="UTC")
SOURCE = "okx"

# Manual S/R Input
SUPPORT = 112000.0
RESISTANCE = 123000.0

# Manual Regime Input
REGIME = "NEUTRAL_RANGE"

# Grid Parameters
GRID_CONFIG = {
    # Grid structure
    "grid_layers_buy": 5,
    "grid_layers_sell": 5,
    "weight_k": 0.5,
    # ATR-based spacing
    "spacing_multiplier": 0.1,
    "cushion_multiplier": 0.8,
    "min_return": 0.005,  # 0.5% as specified
    "maker_fee": 0.001,
    "volatility_k": 0.6,
    # ATR calculation
    "atr_period": 14,
}

# Risk Parameters
RISK_CONFIG = {
    # Global risk budget
    "risk_budget_pct": 0.3,
    # Inventory limits
    "max_long_units": 10.0,
    "max_short_units": 10.0,
    # Daily limits
    "daily_loss_limit": 2000.0,
}

# DGT Parameters
DGT_CONFIG = {
    "enable_mid_shift": False,  # Disabled due to known bug
    "mid_shift_threshold": 20,
}

# Throttling Parameters
THROTTLING_CONFIG = {
    "enable_throttling": True,
    # Inventory throttle
    "inventory_threshold": 0.9,
    # Profit lock
    "profit_target_pct": 0.5,
    "profit_reduction": 0.5,
    # Volatility throttle
    "volatility_threshold": 2.0,
    "volatility_reduction": 0.5,
}

# Backtest Engine Parameters
BACKTEST_CONFIG = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,  # 0.1%
    slippage=0.0005,  # 0.05%
    leverage=1.0,  # No leverage
)

# Output Parameters
OUTPUT_DIR = Path("run/results_taogrid_1min_test")
SAVE_RESULTS = True


def main():
    """Run TaoGrid 1min backtest."""
    print("=" * 80)
    print("TaoGrid Strategy Backtest - 1min K-line Test")
    print("=" * 80)
    print()

    # Print configuration
    print("Configuration:")
    print("-" * 80)
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Period: {START.date()} to {END.date()}")
    print(f"Source: {SOURCE}")
    print()
    print(f"Support: ${SUPPORT:,.0f}")
    print(f"Resistance: ${RESISTANCE:,.0f}")
    print(f"Mid: ${(SUPPORT + RESISTANCE) / 2:,.0f}")
    print(f"Range: ${RESISTANCE - SUPPORT:,.0f} ({(RESISTANCE - SUPPORT) / ((SUPPORT + RESISTANCE) / 2) * 100:.1f}%)")
    print()
    print(f"Regime: {REGIME}")
    print(f"Grid Layers: {GRID_CONFIG['grid_layers_buy']} buy, {GRID_CONFIG['grid_layers_sell']} sell")
    print(f"Min Return: {GRID_CONFIG['min_return']:.1%}")
    print(f"Risk Budget: {RISK_CONFIG['risk_budget_pct']:.1%}")
    print()
    print("Sprint 2 Features:")
    print(f"  DGT Enabled: {DGT_CONFIG['enable_mid_shift']}")
    print(f"  Throttling Enabled: {THROTTLING_CONFIG['enable_throttling']}")
    print(f"  Inventory Threshold: {THROTTLING_CONFIG['inventory_threshold']:.0%}")
    print(f"  Profit Target: {THROTTLING_CONFIG['profit_target_pct']:.0%}")
    print(f"  Volatility Threshold: {THROTTLING_CONFIG['volatility_threshold']:.1f}x")
    print("-" * 80)
    print()

    # Create strategy configuration
    strategy_config = TaoGridConfig(
        name="TaoGrid 1min Test",
        description=f"1min backtest {SYMBOL} {SUPPORT:.0f}-{RESISTANCE:.0f}",
        # Manual inputs
        support=SUPPORT,
        resistance=RESISTANCE,
        regime=REGIME,
        # Grid parameters
        **GRID_CONFIG,
        # Risk parameters
        **RISK_CONFIG,
        # DGT parameters
        **DGT_CONFIG,
        # Throttling parameters
        **THROTTLING_CONFIG,
    )

    # Print grid info
    print("Grid Configuration:")
    print("-" * 80)
    strategy = TaoGridStrategy(strategy_config)
    grid_info = strategy.get_grid_info()
    for key, value in grid_info.items():
        print(f"{key}: {value}")
    print("-" * 80)
    print()

    # Initialize components
    data_manager = DataManager()
    engine = VectorBTEngine()
    runner = BacktestRunner(data_manager)

    # Run backtest
    print("Running backtest...")
    print()

    try:
        result = runner.run(
            BacktestRunConfig(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                start=START,
                end=END,
                source=SOURCE,
                strategy=strategy,
                engine=engine,
                backtest_config=BACKTEST_CONFIG,
                output_dir=OUTPUT_DIR,
                save_results=SAVE_RESULTS,
            )
        )

        # Print results
        print()
        print("=" * 80)
        print("Backtest Results - 1min K-line Test")
        print("=" * 80)
        print()

        # Key metrics
        metrics = result.metrics
        print("Performance Metrics:")
        print("-" * 80)
        print(f"Total Return: {metrics.get('total_return', 0):.2%}")
        print(f"Annualized Return: {metrics.get('annualized_return', 0):.2%}")
        print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        print(f"Sortino Ratio: {metrics.get('sortino_ratio', 0):.2f}")
        print(f"Max Drawdown: {metrics.get('max_drawdown', 0):.2%}")
        print(f"Win Rate: {metrics.get('win_rate', 0):.2%}")
        print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print("-" * 80)
        print()

        # Trading statistics
        print("Trading Statistics:")
        print("-" * 80)
        print(f"Total Trades: {metrics.get('total_trades', 0)}")
        print(f"Winning Trades: {metrics.get('winning_trades', 0)}")
        print(f"Losing Trades: {metrics.get('losing_trades', 0)}")
        print(f"Average Trade: {metrics.get('avg_trade', 0):.2%}")
        print(f"Average Win: {metrics.get('avg_win', 0):.2%}")
        print(f"Average Loss: {metrics.get('avg_loss', 0):.2%}")
        print("-" * 80)
        print()

        # Output information
        if SAVE_RESULTS:
            print("Results saved to:")
            print(f"  {OUTPUT_DIR}")
            print()
            print("Files:")
            print(f"  - equity_curve.csv")
            print(f"  - trades.csv")
            print(f"  - orders.csv")
            print(f"  - metrics.json")
            print()

        print("=" * 80)
        print("1min Backtest completed successfully!")
        print("=" * 80)

    except Exception as e:
        print()
        print("=" * 80)
        print("ERROR: Backtest failed!")
        print("=" * 80)
        print()
        print(f"Error message: {e}")
        print()
        import traceback

        traceback.print_exc()
        print()
        print("=" * 80)
        raise


if __name__ == "__main__":
    main()
