"""
TaoGrid Strategy Backtest - 15min K-line Test (Optimized).

This test validates the hypothesis that 15min k-line will reduce trading costs
and improve net returns compared to 1min k-line.

Optimizations from 1min test:
- Timeframe: 1min → 15min (reduce trade frequency)
- Spacing multiplier: 0.1 → 0.15 (wider grid spacing)
- Min return: 0.5% → 1.0% (higher profit target)

Expected improvements:
- Trade count: 1065 → 100-200
- Trading costs: $640 → $60-120
- Net return: 0.11% → 5-8%

Parameters:
- Period: 2025-07-10 to 2025-08-10 (1 month, same as 1min test)
- Timeframe: 15min
- Support: 112,000
- Resistance: 123,000
- Min Return: 1.0%

Usage:
    python run/run_taogrid_15min_test.py
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
TIMEFRAME = "15m"  # Changed from 1m
START = pd.Timestamp("2025-07-10", tz="UTC")
END = pd.Timestamp("2025-08-10", tz="UTC")
SOURCE = "okx"

# Manual S/R Input (same as 1min test)
SUPPORT = 112000.0
RESISTANCE = 123000.0

# Manual Regime Input
REGIME = "NEUTRAL_RANGE"

# Grid Parameters (optimized from 1min)
GRID_CONFIG = {
    # Grid structure
    "grid_layers_buy": 5,
    "grid_layers_sell": 5,
    "weight_k": 0.5,
    # ATR-based spacing (optimized)
    "spacing_multiplier": 0.15,  # Increased from 0.1
    "cushion_multiplier": 0.8,
    "min_return": 0.01,  # Increased from 0.005 (1.0% vs 0.5%)
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
OUTPUT_DIR = Path("run/results_taogrid_15min_test")
SAVE_RESULTS = True


def main():
    """Run TaoGrid 15min backtest."""
    print("=" * 80)
    print("TaoGrid Strategy Backtest - 15min K-line Test (Optimized)")
    print("=" * 80)
    print()

    # Print configuration
    print("Configuration:")
    print("-" * 80)
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME} (optimized from 1m)")
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
    print()
    print("Optimizations from 1min test:")
    print(f"  Spacing Multiplier: 0.1 → {GRID_CONFIG['spacing_multiplier']}")
    print(f"  Min Return: 0.5% → {GRID_CONFIG['min_return']:.1%}")
    print(f"  Expected Trade Count: 1065 → 100-200")
    print(f"  Expected Net Return: 0.11% → 5-8%")
    print()
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
        name="TaoGrid 15min Test",
        description=f"15min backtest {SYMBOL} {SUPPORT:.0f}-{RESISTANCE:.0f}",
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
        print("Backtest Results - 15min K-line Test (Optimized)")
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

        # Comparison with 1min test
        print("Comparison with 1min Test:")
        print("-" * 80)
        print(f"{'Metric':<20} {'1min':<15} {'15min':<15} {'Change':<15}")
        print("-" * 80)

        # Expected 1min values for comparison
        min_1_trades = 1065
        min_1_return = 0.0011  # 0.11%

        current_trades = metrics.get('total_trades', 0)
        current_return = metrics.get('total_return', 0)

        trade_change = ((current_trades - min_1_trades) / min_1_trades * 100) if min_1_trades > 0 else 0
        return_change = ((current_return - min_1_return) / abs(min_1_return) * 100) if min_1_return != 0 else 0

        print(f"{'Total Trades':<20} {min_1_trades:<15} {current_trades:<15} {trade_change:>+.1f}%")
        print(f"{'Total Return':<20} {min_1_return:<15.2%} {current_return:<15.2%} {return_change:>+.1f}%")
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
        print("15min Backtest completed successfully!")
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
