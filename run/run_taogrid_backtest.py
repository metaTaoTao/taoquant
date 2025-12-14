"""
TaoGrid Strategy Backtest Script (MVP - Sprint 1).

This script demonstrates how to use the TaoGrid strategy with manual S/R
and Regime inputs. The trader specifies Support, Resistance, and Regime,
while the algorithm handles grid generation, spacing, and position sizing.

Core Philosophy:
    TaoGrid = Trader Judgment + Algorithmic Execution

Usage:
    python run/run_taogrid_backtest.py

Implementation Status:
    Sprint 1 (MVP): Static grid + manual inputs
    Sprint 2 (Future): DGT (mid shift) + throttling
    Sprint 3 (Future): Auto regime detection (optional)

References:
    - Strategy Doc: docs/TaoGrid 网格策略.pdf
    - Implementation Plan: docs/strategies/taogrid_implementation_plan_v2.md
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
# CONFIGURATION - Trader Manual Inputs
# =============================================================================

# =============================================================================
# Data Parameters
# =============================================================================
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"  # MVP: Use K-line data (tick data in future)
START = pd.Timestamp("2025-10-01", tz="UTC")
END = pd.Timestamp("2025-12-01", tz="UTC")
SOURCE = "okx"  # 'okx', 'binance', or 'csv'

# =============================================================================
# Manual S/R Input (Trader Specifies)
# =============================================================================
# These levels should be based on trader's technical analysis
# Adjusted for actual Oct-Nov 2025 price range (104k-126k)
SUPPORT = 104000.0  # Lower bound (where we want to buy)
RESISTANCE = 126000.0  # Upper bound (where we want to sell)

# =============================================================================
# Manual Regime Input (Trader Specifies)
# =============================================================================
# Trader's view of market regime:
# - "UP_RANGE": Bullish range (buy 70%, sell 30%)
# - "NEUTRAL_RANGE": Neutral range (buy 50%, sell 50%)
# - "DOWN_RANGE": Bearish range (buy 30%, sell 70%)
REGIME = "NEUTRAL_RANGE"

# =============================================================================
# Grid Parameters (Algorithm Handles)
# =============================================================================
# These are the algorithmic parameters
# Can be adjusted based on market conditions
GRID_CONFIG = {
    # Grid structure
    "grid_layers_buy": 5,  # Number of buy grid layers
    "grid_layers_sell": 5,  # Number of sell grid layers
    "weight_k": 0.5,  # Weight coefficient (edge-heavy)
    # ATR-based spacing
    "spacing_multiplier": 0.1,  # Scale down ATR spacing (0.1 = 10% of ATR spacing)
    "cushion_multiplier": 0.8,  # Volatility cushion (avoid false breakouts)
    "min_return": 0.005,  # Minimum return per grid (0.5%)
    "maker_fee": 0.001,  # Maker fee (0.1%)
    "volatility_k": 0.6,  # Volatility safety factor
    # ATR calculation
    "atr_period": 14,  # ATR period
}

# =============================================================================
# Risk Parameters
# =============================================================================
RISK_CONFIG = {
    # Global risk budget
    "risk_budget_pct": 0.3,  # Total risk budget (30% of capital)
    # Inventory limits
    "max_long_units": 10.0,  # Max long exposure units
    "max_short_units": 10.0,  # Max short exposure units
    # Daily limits
    "daily_loss_limit": 2000.0,  # Daily loss limit (absolute amount)
}

# =============================================================================
# DGT Parameters (Disabled in MVP)
# =============================================================================
DGT_CONFIG = {
    "enable_mid_shift": False,  # 🔴 Set to True in Sprint 2 to enable DGT
    "mid_shift_threshold": 20,  # Bars needed to trigger mid-shift
}

# =============================================================================
# Backtest Engine Parameters
# =============================================================================
BACKTEST_CONFIG = BacktestConfig(
    initial_cash=100000.0,  # Starting capital
    commission=0.001,  # 0.1% commission (maker fee)
    slippage=0.0005,  # 0.05% slippage
    leverage=1.0,  # No leverage in MVP (1x)
)

# =============================================================================
# Output Parameters
# =============================================================================
OUTPUT_DIR = Path("run/results_taogrid_mvp")
SAVE_RESULTS = True

# =============================================================================
# Main Execution
# =============================================================================


def main():
    """Run TaoGrid backtest."""
    print("=" * 80)
    print("TaoGrid Strategy Backtest (MVP - Sprint 1)")
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
    print(f"Range: ${RESISTANCE - SUPPORT:,.0f}")
    print()
    print(f"Regime: {REGIME}")
    print(f"Grid Layers: {GRID_CONFIG['grid_layers_buy']} buy, {GRID_CONFIG['grid_layers_sell']} sell")
    print(f"Risk Budget: {RISK_CONFIG['risk_budget_pct']:.1%}")
    print(f"DGT Enabled: {DGT_CONFIG['enable_mid_shift']}")
    print("-" * 80)
    print()

    # Create strategy configuration
    strategy_config = TaoGridConfig(
        name="TaoGrid MVP",
        description=f"Manual grid {SYMBOL} {SUPPORT:.0f}-{RESISTANCE:.0f}",
        # Manual inputs (core)
        support=SUPPORT,
        resistance=RESISTANCE,
        regime=REGIME,
        # Grid parameters
        **GRID_CONFIG,
        # Risk parameters
        **RISK_CONFIG,
        # DGT parameters
        **DGT_CONFIG,
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
        print("Backtest Results")
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
        print(f"Best Trade: {metrics.get('best_trade', 0):.2%}")
        print(f"Worst Trade: {metrics.get('worst_trade', 0):.2%}")
        print("-" * 80)
        print()

        # Exposure statistics
        print("Exposure Statistics:")
        print("-" * 80)
        print(f"Exposure Time: {metrics.get('exposure_time', 0):.2%}")
        print(f"Average Trade Duration: {metrics.get('avg_trade_duration_hours', 0):.1f} hours")
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
            print(f"  - metrics.json")
            print(f"  - config.json")
            print()

        print("=" * 80)
        print("Backtest completed successfully!")
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
