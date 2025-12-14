"""
Simplified Lean Runner for TaoGrid (No QC Account Required).

This runs TaoGrid algorithm using our own data and generates results locally.

Usage:
    python algorithms/taogrid/simple_lean_runner.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone
import json

# Add project root
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np

# Import TaoGrid components
from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig

# Import taoquant data
from data import DataManager


class SimpleLeanRunner:
    """Simplified Lean backtest runner using our own data."""

    def __init__(
        self,
        config: TaoGridLeanConfig,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ):
        """Initialize runner with config."""
        self.config = config
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date

        self.algorithm = TaoGridLeanAlgorithm(config)

        # Results tracking
        self.equity_curve = []
        self.trades = []
        self.orders = []
        self.daily_pnl = []

        # Portfolio state
        self.cash = config.initial_cash
        self.holdings = 0.0  # BTC quantity
        
        # Grid position tracking (FIFO queue for pairing)
        # Each entry: {'size': float, 'price': float, 'level': int, 'timestamp': datetime}
        self.long_positions: list[dict] = []  # FIFO queue of buy orders
        self.short_positions: list[dict] = []  # FIFO queue of sell orders

    def load_data(self) -> pd.DataFrame:
        """Load historical data."""
        print("Loading data...")
        data_manager = DataManager()

        data = data_manager.get_klines(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start=self.start_date,
            end=self.end_date,
            source="okx",
        )

        print(f"  Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
        return data

    def run(self) -> dict:
        """Run backtest."""
        print("=" * 80)
        print("TaoGrid Lean Backtest (Simplified Runner)")
        print("=" * 80)
        print()

        # Load data
        data = self.load_data()

        # Initialize algorithm with historical data
        print("Initializing algorithm...")
        historical_data = data.head(100)  # Use first 100 bars for ATR calc
        self.algorithm.initialize(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            historical_data=historical_data,
        )

        # Run bar-by-bar
        print("Running backtest...")
        print()

        for i, (timestamp, row) in enumerate(data.iterrows()):
            if i % 100 == 0:
                print(f"  Processing bar {i}/{len(data)} ({i/len(data)*100:.1f}%)", end="\r")

            # Set current bar index for limit order trigger checking
            self.algorithm._current_bar_index = i

            # Prepare bar data
            bar_data = {
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
            }

            # Prepare portfolio state
            current_equity = self.cash + (self.holdings * row['close'])
            portfolio_state = {
                'equity': current_equity,
                'cash': self.cash,
                'holdings': self.holdings,
            }

            # Process with TaoGrid algorithm
            order = self.algorithm.on_data(timestamp, bar_data, portfolio_state)

            # Execute orders (on_data returns order dict directly, or None)
            if order:
                executed = self.execute_order(order, row['close'], timestamp)

                # Update grid manager inventory if order was executed
                if executed:
                    # For buy orders, add to grid manager positions first
                    if order['direction'] == 'buy':
                        self.algorithm.grid_manager.add_buy_position(
                            buy_level_index=order['level'],
                            size=order['quantity'],
                            buy_price=order['price']
                        )
                    
                    # Call on_order_filled to update grid state and place new limit orders
                    self.algorithm.on_order_filled(order)
                    
                    # For sell orders, match against grid positions using grid pairing
                    if order['direction'] == 'sell':
                        match_result = self.algorithm.grid_manager.match_sell_order(
                            sell_level_index=order['level'],
                            sell_size=order['quantity']
                        )
                        # match_result is used for trade recording in execute_order

            # Record equity
            self.equity_curve.append({
                'timestamp': timestamp,
                'equity': current_equity,
                'cash': self.cash,
                'holdings': self.holdings,
                'holdings_value': self.holdings * row['close'],
            })

        print()
        print("  Backtest completed!")
        print()

        # Calculate metrics
        metrics = self.calculate_metrics()

        return {
            'metrics': metrics,
            'equity_curve': pd.DataFrame(self.equity_curve),
            'trades': pd.DataFrame(self.trades) if self.trades else pd.DataFrame(),
            'orders': pd.DataFrame(self.orders) if self.orders else pd.DataFrame(),
        }

    def execute_order(self, order: dict, market_price: float, timestamp: datetime) -> bool:
        """
        Execute an order with grid-level pairing (FIFO).

        Grid pairing logic:
        - Buy orders: Add to long_positions queue
        - Sell orders: Match against long_positions (FIFO), record trades
        
        Note: For grid strategy, we execute at GRID LEVEL PRICE, not market price.
        This ensures grid spacing is respected.

        Parameters
        ----------
        order : dict
            Order dict with 'price' (grid level price) and 'level' (grid level index)
        market_price : float
            Current market price (for reference, but we use grid level price)
        timestamp : datetime
            Order timestamp

        Returns
        -------
        bool
            True if order was executed, False otherwise
        """
        direction = order['direction']
        size = order['quantity']
        level = order.get('level', -1)  # Grid level index
        grid_level_price = order.get('price')  # Grid level price (trigger price)
        
        # Use grid level price for execution (not market price)
        # This ensures we respect grid spacing
        execution_price = grid_level_price if grid_level_price else market_price

        # Apply commission
        # NOTE: For limit orders, slippage should be 0 (or very small)
        # Limit orders execute at the specified price, so no slippage
        commission_rate = 0.001  # 0.1%
        slippage_rate = 0.0  # 0% - limit orders execute at grid level price, no slippage

        if direction == 'buy':
            # Buy BTC - Add to long positions queue
            cost = size * execution_price
            commission = cost * commission_rate
            slippage = cost * slippage_rate
            total_cost = cost + commission + slippage

            if total_cost <= self.cash:
                self.cash -= total_cost
                self.holdings += size

                # Add to long positions queue (FIFO)
                self.long_positions.append({
                    'size': size,
                    'price': execution_price,  # Grid level price
                    'level': level,
                    'timestamp': timestamp,
                    'entry_cost': total_cost,
                })

                self.orders.append({
                    'timestamp': timestamp,
                    'direction': 'buy',
                    'size': size,
                    'price': execution_price,  # Grid level price
                    'level': level,
                    'market_price': market_price,  # For reference
                    'cost': total_cost,
                    'commission': commission,
                    'slippage': slippage,
                })

                return True  # Order executed

        elif direction == 'sell':
            # Sell BTC - Match against long positions using GRID PAIRING
            if size <= self.holdings:
                proceeds = size * execution_price
                commission = proceeds * commission_rate
                slippage = proceeds * slippage_rate
                net_proceeds = proceeds - commission - slippage

                self.cash += net_proceeds
                self.holdings -= size

                # Match against long positions using grid pairing (buy[i] -> sell[i])
                # Use grid_manager.match_sell_order for proper grid pairing
                remaining_sell_size = size
                matched_trades = []

                while remaining_sell_size > 0.0001:
                    # Use grid_manager to find matching buy position
                    match_result = self.algorithm.grid_manager.match_sell_order(
                        sell_level_index=level,
                        sell_size=remaining_sell_size
                    )
                    
                    if match_result is None:
                        break  # No more matching positions
                    
                    buy_level_idx, buy_price, matched_size = match_result
                    
                    # Find corresponding position in long_positions
                    buy_pos = None
                    for pos in self.long_positions:
                        if pos['level'] == buy_level_idx and abs(pos['price'] - buy_price) < 0.01:
                            buy_pos = pos
                            break
                    
                    if buy_pos is None:
                        # Position not found in long_positions, skip
                        break
                    
                    buy_size = buy_pos['size']
                    buy_timestamp = buy_pos['timestamp']
                    buy_cost = buy_pos['entry_cost']
                    
                    # Calculate PnL for this matched trade
                    sell_proceeds_portion = (matched_size / size) * net_proceeds
                    sell_cost_portion = (matched_size / size) * (commission + slippage)
                    buy_cost_portion = (matched_size / buy_size) * buy_cost
                    
                    trade_pnl = sell_proceeds_portion - buy_cost_portion
                    trade_return_pct = trade_pnl / buy_cost_portion if buy_cost_portion > 0 else 0

                    # Record matched trade
                    matched_trades.append({
                        'entry_timestamp': buy_timestamp,
                        'exit_timestamp': timestamp,
                        'entry_price': buy_price,  # Grid level price at entry
                        'exit_price': execution_price,  # Grid level price at exit
                        'entry_level': buy_level_idx,
                        'exit_level': level,
                        'size': matched_size,
                        'pnl': trade_pnl,
                        'return_pct': trade_return_pct,
                        'holding_period': (timestamp - buy_timestamp).total_seconds() / 3600,  # hours
                    })

                    # Update positions
                    remaining_sell_size -= matched_size
                    buy_pos['size'] -= matched_size
                    buy_pos['entry_cost'] -= buy_cost_portion

                    # Remove position if fully matched
                    if buy_pos['size'] < 0.0001:
                        self.long_positions.remove(buy_pos)

                # Record all matched trades
                self.trades.extend(matched_trades)

                self.orders.append({
                    'timestamp': timestamp,
                    'direction': 'sell',
                    'size': size,
                    'price': execution_price,  # Grid level price
                    'level': level,
                    'market_price': market_price,  # For reference
                    'proceeds': net_proceeds,
                    'commission': commission,
                    'slippage': slippage,
                    'matched_trades': len(matched_trades),
                })

                return True  # Order executed

        return False  # Order not executed (insufficient cash/holdings)

    def calculate_metrics(self) -> dict:
        """Calculate performance metrics."""
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        initial_equity = self.config.initial_cash
        final_equity = equity_df['equity'].iloc[-1]
        total_return = (final_equity - initial_equity) / initial_equity

        # Drawdown
        cummax = equity_df['equity'].cummax()
        drawdown = (equity_df['equity'] - cummax) / cummax
        max_drawdown = drawdown.min()

        # Returns
        returns = equity_df['equity'].pct_change().dropna()
        sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

        # Downside deviation
        negative_returns = returns[returns < 0]
        downside_std = negative_returns.std() if len(negative_returns) > 0 else returns.std()
        sortino = returns.mean() / downside_std * np.sqrt(252) if downside_std > 0 else 0

        # Trade statistics
        if not trades_df.empty:
            total_trades = len(trades_df)
            winning_trades = (trades_df['pnl'] > 0).sum()
            losing_trades = (trades_df['pnl'] < 0).sum()
            win_rate = winning_trades / total_trades if total_trades > 0 else 0

            wins = trades_df[trades_df['pnl'] > 0]
            losses = trades_df[trades_df['pnl'] < 0]

            avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
            avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0

            gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
            gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # Grid-specific metrics
            avg_holding_period = trades_df['holding_period'].mean() if 'holding_period' in trades_df.columns else 0.0
            avg_return_per_trade = trades_df['return_pct'].mean() if 'return_pct' in trades_df.columns else 0.0
        else:
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            avg_holding_period = 0.0
            avg_return_per_trade = 0.0

        return {
            'total_return': total_return,
            'total_pnl': final_equity - initial_equity,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'final_equity': final_equity,
            'avg_holding_period_hours': avg_holding_period,
            'avg_return_per_trade': avg_return_per_trade,
        }

    def save_results(self, results: dict, output_dir: Path):
        """Save results to files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save metrics
        with open(output_dir / "metrics.json", "w") as f:
            # Convert numpy types to Python types
            metrics = {}
            for k, v in results['metrics'].items():
                if isinstance(v, (np.integer, np.floating)):
                    metrics[k] = float(v)
                else:
                    metrics[k] = v
            json.dump(metrics, f, indent=2)

        # Save equity curve
        results['equity_curve'].to_csv(output_dir / "equity_curve.csv", index=False)

        # Save trades (with proper column ordering)
        # Always save trades.csv, even if empty (for consistency)
        trades_df = results['trades']
        if not trades_df.empty:
            # Ensure all expected columns exist
            expected_cols = ['entry_timestamp', 'exit_timestamp', 'entry_price', 'exit_price', 
                           'entry_level', 'exit_level', 'size', 'pnl', 'return_pct', 'holding_period']
            # Reorder columns if they exist
            available_cols = [col for col in expected_cols if col in trades_df.columns]
            other_cols = [col for col in trades_df.columns if col not in expected_cols]
            trades_df = trades_df[available_cols + other_cols]
        else:
            # Create empty DataFrame with expected columns
            trades_df = pd.DataFrame(columns=[
                'entry_timestamp', 'exit_timestamp', 'entry_price', 'exit_price',
                'entry_level', 'exit_level', 'size', 'pnl', 'return_pct', 'holding_period'
            ])
        
        trades_df.to_csv(output_dir / "trades.csv", index=False)
        
        if trades_df.empty:
            print(f"  Warning: No trades recorded. This may indicate:")
            print(f"    - Grid pairing logic issue")
            print(f"    - No buy/sell matches occurred")
            print(f"    - Need to re-run backtest with fixed logic")

        # Save orders
        if not results['orders'].empty:
            results['orders'].to_csv(output_dir / "orders.csv", index=False)

        print(f"Results saved to: {output_dir}")

    def print_summary(self, results: dict):
        """Print results summary."""
        metrics = results['metrics']

        print("=" * 80)
        print("BACKTEST RESULTS")
        print("=" * 80)
        print()
        print("Performance:")
        print(f"  Total Return:    {metrics['total_return']:.2%}")
        print(f"  Total PnL:       ${metrics['total_pnl']:,.2f}")
        print(f"  Final Equity:    ${metrics['final_equity']:,.2f}")
        print(f"  Max Drawdown:    {metrics['max_drawdown']:.2%}")
        print(f"  Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")
        print(f"  Sortino Ratio:   {metrics['sortino_ratio']:.2f}")
        print()
        print("Trading:")
        print(f"  Total Trades:    {metrics['total_trades']}")
        print(f"  Winning Trades:  {metrics['winning_trades']}")
        print(f"  Losing Trades:   {metrics['losing_trades']}")
        print(f"  Win Rate:        {metrics['win_rate']:.2%}")
        print(f"  Profit Factor:   {metrics['profit_factor']:.2f}")
        if metrics['avg_win'] != 0:
            print(f"  Average Win:     ${metrics['avg_win']:,.2f}")
        if metrics['avg_loss'] != 0:
            print(f"  Average Loss:    ${metrics['avg_loss']:,.2f}")
        print()
        print("Grid Metrics:")
        if metrics.get('avg_holding_period_hours', 0) > 0:
            print(f"  Avg Holding Period: {metrics['avg_holding_period_hours']:.1f} hours")
        if metrics.get('avg_return_per_trade', 0) != 0:
            print(f"  Avg Return/Trade:   {metrics['avg_return_per_trade']:.2%}")
        print("=" * 80)


def main():
    """Main entry point."""
    # Create configuration
    config = TaoGridLeanConfig(
        name="TaoGrid Optimized - Traditional Grid",
        description="Traditional grid with free sell + optimized parameters",

        # ========== S/R Levels (Based on actual price range) ==========
        # Historical price analysis (2025-07-10 to 2025-08-10):
        # Price range: ~$115k - $120k (5k range)
        # Main action: $116k - $118k (2k range)
        support=115000.0,   # Set below actual low for safety margin
        resistance=120000.0,  # Set above actual high for safety margin
        regime="NEUTRAL_RANGE",

        # ========== Grid Parameters (Optimized for Turnover) ==========
        # Goal: Maximize turnover while maintaining profitability
        # Formula: spacing = (min_return + 2×fee) × spacing_multiplier
        #
        # Analysis:
        # - min_return = 0.5%
        # - trading_costs = 0.2% (2 × 0.1% maker_fee, slippage=0 for limit orders)
        # - base_spacing = 0.7%
        # - spacing_multiplier = 1.0 → final spacing = 0.7%
        #
        # In $5k range with 0.7% spacing:
        # - Max layers possible = $5k / ($117k × 0.7%) ≈ 6 layers
        # - We'll request 10 layers, system will generate what fits
        grid_layers_buy=10,
        grid_layers_sell=10,
        weight_k=0.5,

        # CRITICAL: spacing_multiplier >= 1.0 (now enforced by validation)
        spacing_multiplier=1.0,  # Use standard spacing (no expansion)
        min_return=0.005,  # 0.5% - net profit target per trade
        # Expected final spacing: 0.7% (base) × 1.0 = 0.7%
        # Net profit per trade: 0.7% - 0.2% (costs) = 0.5% ✓

        # Risk parameters - Traditional grid allocation
        # Grid strategies work best with higher capital allocation
        risk_budget_pct=0.6,      # 60% of capital in grid (increased from 30%)
        enable_throttling=False,  # Disable for traditional grid (maximize turnover)

        # Backtest parameters
        initial_cash=100000.0,
        leverage=1.0,  # Start with 1x, can increase later
    )

    # Run backtest
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 7, 10, tzinfo=timezone.utc),
        end_date=datetime(2025, 8, 10, tzinfo=timezone.utc),
    )
    results = runner.run()

    # Print summary
    runner.print_summary(results)

    # Save results
    output_dir = Path("run/results_lean_taogrid")
    runner.save_results(results, output_dir)

    print()
    print("Next steps:")
    print("1. Review metrics in: run/results_lean_taogrid/metrics.json")
    print("2. Analyze trades in: run/results_lean_taogrid/trades.csv")
    print("3. Plot equity curve from: run/results_lean_taogrid/equity_curve.csv")


if __name__ == "__main__":
    main()
