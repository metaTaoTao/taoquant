"""
Run Neutral Grid Backtest with ATR-based Spacing.

This script:
1. Fetches historical data
2. Calculates ATR-based spacing
3. Auto-calculates grid count based on spacing
4. Runs neutral grid backtest
5. Generates performance report
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

# Add taoquant to path
taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from data import DataManager
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing
from algorithms.taogrid.neutral_grid_config import NeutralGridConfig
from algorithms.taogrid.neutral_grid import NeutralGridManager


def calculate_auto_grid_count(
    lower_price: float,
    upper_price: float,
    spacing_pct: float,
) -> int:
    """
    Auto-calculate grid count based on spacing.

    Logic:
    - Total range = upper - lower
    - Each grid covers spacing_pct of price
    - Use geometric progression: count = log(upper/lower) / log(1 + spacing)

    Parameters
    ----------
    lower_price : float
        Grid lower bound
    upper_price : float
        Grid upper bound
    spacing_pct : float
        Grid spacing percentage (e.g., 0.01 for 1%)

    Returns
    -------
    int
        Recommended grid count
    """
    # Geometric grid count formula
    # Each level: P[i+1] = P[i] * (1 + spacing)
    # P[n] = P[0] * (1 + spacing)^n
    # n = log(P[n] / P[0]) / log(1 + spacing)

    ratio = upper_price / lower_price
    grid_count = int(np.log(ratio) / np.log(1 + spacing_pct))

    # Ensure at least 2 grids
    grid_count = max(2, grid_count)

    # Cap at reasonable maximum
    grid_count = min(200, grid_count)

    return grid_count


def run_backtest(
    symbol: str = "BTCUSDT",
    support: float = 80000.0,
    resistance: float = 94000.0,
    leverage: float = 10.0,
    initial_cash: float = 10000.0,
    start_date: str = "2025-10-01",
    end_date: str = "2025-12-26",
    timeframe: str = "15m",
    source: str = "okx",
):
    """
    Run neutral grid backtest with ATR-based spacing.

    Parameters
    ----------
    symbol : str
        Trading symbol
    support : float
        Grid lower bound (support level)
    resistance : float
        Grid upper bound (resistance level)
    leverage : float
        Leverage multiplier
    initial_cash : float
        Initial capital (USD)
    start_date : str
        Backtest start date
    end_date : str
        Backtest end date
    timeframe : str
        Data timeframe
    source : str
        Data source
    """
    print("\n" + "=" * 80)
    print("Neutral Grid Backtest with ATR-Based Spacing")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Support: ${support:,.0f}")
    print(f"Resistance: ${resistance:,.0f}")
    print(f"Leverage: {leverage}x")
    print(f"Initial Cash: ${initial_cash:,.0f}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Timeframe: {timeframe}")
    print("")

    # ========================================================================
    # Step 1: Load Data
    # ========================================================================
    print("Step 1: Loading historical data...")
    data_manager = DataManager()

    data = data_manager.get_klines(
        symbol=symbol,
        timeframe=timeframe,
        start=pd.Timestamp(start_date, tz="UTC"),
        end=pd.Timestamp(end_date, tz="UTC"),
        source=source,
    )

    print(f"Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    print(f"Price range: ${data['close'].min():,.0f} - ${data['close'].max():,.0f}")
    print("")

    # ========================================================================
    # Step 2: Calculate ATR and Spacing
    # ========================================================================
    print("Step 2: Calculating ATR-based spacing...")

    # Calculate ATR
    atr = calculate_atr(
        data['high'],
        data['low'],
        data['close'],
        period=14
    )

    avg_atr = atr.mean()
    current_atr = atr.iloc[-1]

    print(f"ATR (14-period):")
    print(f"  Current: ${current_atr:,.2f}")
    print(f"  Average: ${avg_atr:,.2f}")
    print(f"  Min: ${atr.min():,.2f}")
    print(f"  Max: ${atr.max():,.2f}")
    print("")

    # Calculate spacing using your formula
    spacing_series = calculate_grid_spacing(
        atr=atr,
        min_return=0.005,        # 0.5% minimum net return
        maker_fee=0.0002,        # 0.02% maker fee
        slippage=0.0,            # 0% for limit orders
        volatility_k=0.6,        # Volatility factor
        use_limit_orders=True,
    )

    avg_spacing = spacing_series.mean()
    current_spacing = spacing_series.iloc[-1]

    print(f"Grid Spacing (ATR-based):")
    print(f"  Current: {current_spacing:.4%}")
    print(f"  Average: {avg_spacing:.4%}")
    print(f"  Min: {spacing_series.min():.4%}")
    print(f"  Max: {spacing_series.max():.4%}")
    print("")

    # ========================================================================
    # Step 3: Auto-calculate Grid Count
    # ========================================================================
    print("Step 3: Auto-calculating grid count...")

    grid_count = calculate_auto_grid_count(
        lower_price=support,
        upper_price=resistance,
        spacing_pct=avg_spacing,
    )

    print(f"Auto-calculated grid count: {grid_count}")
    print(f"  Based on:")
    print(f"    Range: ${support:,.0f} - ${resistance:,.0f} ({(resistance-support)/support:.1%})")
    print(f"    Avg spacing: {avg_spacing:.4%}")
    print(f"    Formula: log(R/S) / log(1 + spacing) = {grid_count}")
    print("")

    # ========================================================================
    # Step 4: Setup Grid
    # ========================================================================
    print("Step 4: Setting up neutral grid...")

    # Find current price at start
    start_price = data['close'].iloc[0]

    # Verify price is within range
    if start_price < support or start_price > resistance:
        print(f"[WARNING] Start price ${start_price:,.0f} is outside grid range!")
        print(f"  Grid range: ${support:,.0f} - ${resistance:,.0f}")
        print(f"  This backtest may not work correctly.")
        print("")

    config = NeutralGridConfig(
        lower_price=support,
        upper_price=resistance,
        grid_count=grid_count,
        mode="geometric",  # Use geometric spacing (like your ATR formula)
        total_investment=initial_cash * leverage,  # Total capital with leverage
        initial_position_pct=0.5,  # 50% initial position
        leverage=leverage,
        maker_fee=0.0002,
        min_order_size_usd=5.0,
        enable_console_log=False,  # Disable detailed logs for backtest
    )

    manager = NeutralGridManager(config)
    manager.setup_grid(current_price=start_price)

    print(f"Grid initialized at ${start_price:,.2f}")
    print(f"  Grid count: {grid_count}")
    print(f"  Grid prices: ${manager.grid_prices[0]:,.0f} to ${manager.grid_prices[-1]:,.0f}")
    print(f"  Pending orders: {len(manager.pending_orders)}")
    print(f"  Initial positions: {len(manager.positions)}")
    print("")

    # ========================================================================
    # Step 5: Run Backtest
    # ========================================================================
    print("Step 5: Running backtest...")

    # Track equity over time
    equity_history = []
    timestamp_history = []

    # Simulate bar-by-bar
    for i, (timestamp, row) in enumerate(data.iterrows()):
        bar_high = row['high']
        bar_low = row['low']
        bar_close = row['close']

        # CRITICAL FIX: Process ALL triggered orders in this bar
        # Not just one! A bar can trigger multiple limit orders
        max_fills_per_bar = 100  # Safety limit
        fills_this_bar = 0

        while fills_this_bar < max_fills_per_bar:
            # Check for order triggers
            triggered = manager.check_order_triggers(
                bar_high=bar_high,
                bar_low=bar_low,
                bar_index=i,
            )

            if not triggered:
                break  # No more orders to fill

            # Handle fill
            manager.on_order_filled(
                triggered,
                fill_price=triggered.price,  # Use limit price
                fill_time=timestamp,
            )
            fills_this_bar += 1

        # Calculate current equity
        # Equity = Cash + Position Value
        stats = manager.get_statistics()
        position_value = stats['total_position_btc'] * bar_close
        cash_used = stats['total_position_value_usd']  # Initial cost
        unrealized_pnl = position_value - cash_used
        equity = initial_cash + stats['net_pnl'] + unrealized_pnl

        equity_history.append(equity)
        timestamp_history.append(timestamp)

        # Progress update every 10%
        if i % (len(data) // 10) == 0:
            progress = (i + 1) / len(data) * 100
            print(f"  Progress: {progress:.0f}% | Equity: ${equity:,.0f} | Trades: {stats['total_trades']}")

    print(f"  Progress: 100% | Backtest complete!")
    print("")

    # ========================================================================
    # Step 6: Generate Report
    # ========================================================================
    print("=" * 80)
    print("Backtest Results")
    print("=" * 80)

    stats = manager.get_statistics()

    # Final equity
    final_equity = equity_history[-1]
    total_return = (final_equity - initial_cash) / initial_cash

    print(f"\nPerformance:")
    print(f"  Initial Capital: ${initial_cash:,.2f}")
    print(f"  Final Equity: ${final_equity:,.2f}")
    print(f"  Total Return: {total_return:+.2%} (${final_equity - initial_cash:+,.2f})")
    print(f"  Realized PnL: ${stats['total_pnl']:,.2f}")
    print(f"  Total Fees: ${stats['total_fees']:,.2f}")
    print(f"  Net PnL: ${stats['net_pnl']:,.2f}")

    print(f"\nTrading Activity:")
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Buy Volume: {stats['total_buy_volume']:.6f} BTC")
    print(f"  Sell Volume: {stats['total_sell_volume']:.6f} BTC")
    print(f"  Avg Trade Size: {stats['total_buy_volume'] / max(1, stats['total_trades'] / 2):.6f} BTC")

    print(f"\nCurrent State:")
    print(f"  Open Positions: {stats['positions_count']}")
    print(f"  Position Value: ${stats['total_position_value_usd']:,.2f}")
    print(f"  Position Size: {stats['total_position_btc']:.6f} BTC")
    print(f"  Pending Orders: {stats['pending_orders_count']}")

    # Calculate risk metrics
    equity_series = pd.Series(equity_history, index=timestamp_history)
    drawdown = (equity_series - equity_series.cummax()) / equity_series.cummax()
    max_drawdown = drawdown.min()

    # Calculate returns
    returns = equity_series.pct_change().dropna()
    sharpe_ratio = returns.mean() / returns.std() * np.sqrt(365 * 24 * 4) if returns.std() > 0 else 0

    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown: {max_drawdown:.2%}")
    print(f"  Sharpe Ratio: {sharpe_ratio:.2f}")
    print(f"  Win Rate: {stats['total_trades'] / max(1, len(data) * 2):.2%}")

    print(f"\nGrid Configuration:")
    print(f"  Mode: {stats['grid_mode']}")
    print(f"  Grid Count: {stats['grid_count']}")
    print(f"  Price Range: ${support:,.0f} - ${resistance:,.0f}")
    print(f"  Avg Spacing: {avg_spacing:.4%}")
    print(f"  Leverage: {leverage}x")

    print("\n" + "=" * 80 + "\n")

    return {
        'stats': stats,
        'equity_history': equity_series,
        'final_equity': final_equity,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
    }


if __name__ == "__main__":
    # Run backtest with user's parameters
    result = run_backtest(
        symbol="BTCUSDT",
        support=80000.0,
        resistance=94000.0,
        leverage=10.0,
        initial_cash=10000.0,
        start_date="2025-10-01",
        end_date="2025-12-26",
        timeframe="15m",
        source="okx",
    )
