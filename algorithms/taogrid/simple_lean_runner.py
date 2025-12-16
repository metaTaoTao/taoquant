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
        data: pd.DataFrame | None = None,
        output_dir: Path | None = None,
        verbose: bool = True,
        progress_every: int = 100,
        collect_equity_detail: bool = True,
    ):
        """Initialize runner with config."""
        self.config = config
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self._data_override = data
        self.output_dir = output_dir
        self.verbose = verbose
        self.progress_every = max(1, int(progress_every))
        self.collect_equity_detail = bool(collect_equity_detail)

        self.algorithm = TaoGridLeanAlgorithm(config)

        # Results tracking
        # To keep optimization runs fast, we allow a lightweight equity curve
        # representation (timestamp + equity only).
        self.equity_curve = []
        self._equity_timestamps: list[datetime] = []
        self._equity_values: list[float] = []
        self.trades = []
        self.orders = []
        self.daily_pnl = []

        # Portfolio state
        self.cash = config.initial_cash
        self.holdings = 0.0  # BTC quantity
        self.total_cost_basis = 0.0  # Total cost basis for unrealized PnL calculation
        # Track margin-style leverage with negative cash allowed (simplified perp model)
        
        # Grid position tracking (FIFO queue for pairing)
        # Each entry: {'size': float, 'price': float, 'level': int, 'timestamp': datetime}
        self.long_positions: list[dict] = []  # FIFO queue of buy orders
        self.short_positions: list[dict] = []  # FIFO queue of sell orders

    def load_data(self) -> pd.DataFrame:
        """Load historical data."""
        if self._data_override is not None:
            data = self._data_override
            if not isinstance(data.index, pd.DatetimeIndex):
                raise ValueError("Provided data must be indexed by DatetimeIndex")
            # Ensure UTC-aware slicing (DataManager returns UTC-aware index)
            start = pd.Timestamp(self.start_date).tz_convert("UTC") if pd.Timestamp(self.start_date).tzinfo else pd.Timestamp(self.start_date, tz="UTC")
            end = pd.Timestamp(self.end_date).tz_convert("UTC") if pd.Timestamp(self.end_date).tzinfo else pd.Timestamp(self.end_date, tz="UTC")
            sliced = data.loc[(data.index >= start) & (data.index < end)]
            if sliced.empty:
                raise ValueError(f"Provided data does not cover requested range: {start} to {end}")
            return sliced

        if self.verbose:
            print("Loading data...")
        data_manager = DataManager()

        data = data_manager.get_klines(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start=self.start_date,
            end=self.end_date,
            source="okx",
        )

        if self.verbose:
            print(f"  Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
        return data

    def run(self) -> dict:
        """Run backtest."""
        if self.verbose:
            print("=" * 80)
            print("TaoGrid Lean Backtest (Simplified Runner)")
            print("=" * 80)
            print()

        # Load data
        data = self.load_data()

        # Pre-compute factor columns (pure functions in analytics/)
        # Used to improve risk-adjusted performance (Sharpe) by:
        # - reducing buys in strong downtrends
        # - sizing up only when mean-reversion signal is stronger
        try:
            from analytics.indicators.regime_factors import (
                calculate_ema,
                calculate_ema_slope,
                rolling_zscore,
                trend_score_from_slope,
            )

            ema = calculate_ema(data["close"], period=int(self.config.trend_ema_period))
            slope = calculate_ema_slope(ema, lookback=int(self.config.trend_slope_lookback))
            data["trend_score"] = trend_score_from_slope(slope, slope_ref=float(self.config.trend_slope_ref))
            data["mr_z"] = rolling_zscore(data["close"], window=int(self.config.mr_z_lookback))
        except Exception:
            # Robust fallback: proceed without factors
            data["trend_score"] = np.nan
            data["mr_z"] = np.nan

        # Breakout risk factor (range boundary risk-off)
        try:
            from analytics.indicators.volatility import calculate_atr
            from analytics.indicators.breakout_risk import compute_breakout_risk
            from analytics.indicators.range_factors import compute_range_position
            from analytics.indicators.vol_regime import calculate_atr_pct, rolling_quantile_score

            atr = calculate_atr(
                data["high"],
                data["low"],
                data["close"],
                period=int(self.config.atr_period),
            )
            br = compute_breakout_risk(
                close=data["close"],
                atr=atr,
                support=float(self.config.support),
                resistance=float(self.config.resistance),
                trend_score=data.get("trend_score"),
                band_atr_mult=float(getattr(self.config, "breakout_band_atr_mult", 1.5)),
                band_pct=float(getattr(self.config, "breakout_band_pct", 0.003)),
                trend_weight=float(getattr(self.config, "breakout_trend_weight", 0.7)),
            )
            data["breakout_risk_down"] = br["breakout_risk_down"]
            data["breakout_risk_up"] = br["breakout_risk_up"]
            data["range_pos"] = compute_range_position(
                close=data["close"],
                support=float(self.config.support),
                resistance=float(self.config.resistance),
            )

            # Volatility regime score (0..1): higher => higher volatility
            atr_pct = calculate_atr_pct(atr=atr, close=data["close"])
            data["vol_score"] = rolling_quantile_score(
                series=atr_pct,
                lookback=int(getattr(self.config, "vol_lookback", 1440)),
                low_q=float(getattr(self.config, "vol_low_q", 0.20)),
                high_q=float(getattr(self.config, "vol_high_q", 0.80)),
            )
        except Exception:
            data["breakout_risk_down"] = 0.0
            data["breakout_risk_up"] = 0.0
            data["range_pos"] = 0.5
            data["vol_score"] = 0.0

        # Funding rate (perp) factor: fetch from OKX public API and align to bar timestamps.
        if getattr(self.config, "enable_funding_factor", True):
            try:
                dm = DataManager()
                funding = dm.get_funding_rates(
                    symbol=self.symbol,
                    start=self.start_date,
                    end=self.end_date,
                    source="okx",
                    use_cache=True,
                    allow_empty=True,
                )
                if funding is None or funding.empty:
                    data["funding_rate"] = 0.0
                    data["minutes_to_funding"] = np.nan
                else:
                    # Align to OHLCV timestamps by forward filling.
                    funding_aligned = funding.reindex(data.index, method="ffill").fillna(0.0)
                    data["funding_rate"] = funding_aligned["funding_rate"].astype(float)

                    # Compute minutes to next funding settlement time (fundingTime schedule).
                    funding_times = funding.index.sort_values()
                    # For each bar ts, find next funding_time >= ts using merge_asof(direction="forward")
                    ts_df = pd.DataFrame({"timestamp": data.index}).sort_values("timestamp")
                    ft_df = pd.DataFrame({"funding_time": funding_times})
                    merged = pd.merge_asof(
                        ts_df,
                        ft_df,
                        left_on="timestamp",
                        right_on="funding_time",
                        direction="forward",
                        allow_exact_matches=True,
                    )
                    mins = (merged["funding_time"] - merged["timestamp"]).dt.total_seconds() / 60.0
                    data["minutes_to_funding"] = mins.values
            except Exception:
                data["funding_rate"] = 0.0
                data["minutes_to_funding"] = np.nan
        else:
            data["funding_rate"] = 0.0
            data["minutes_to_funding"] = np.nan

        # Initialize algorithm with historical data
        if self.verbose:
            print("Initializing algorithm...")
        historical_data = data.head(100)  # Use first 100 bars for ATR calc
        self.algorithm.initialize(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            historical_data=historical_data,
        )

        # Run bar-by-bar
        if self.verbose:
            print("Running backtest...")
        print()

        for i, (timestamp, row) in enumerate(data.iterrows()):
            if self.verbose and i % self.progress_every == 0:
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
                # Factor state (optional)
                'trend_score': row.get('trend_score', np.nan),
                'mr_z': row.get('mr_z', np.nan),
                'breakout_risk_down': row.get('breakout_risk_down', 0.0),
                'breakout_risk_up': row.get('breakout_risk_up', 0.0),
                'range_pos': row.get('range_pos', 0.5),
                'vol_score': row.get('vol_score', 0.0),
                'funding_rate': row.get('funding_rate', 0.0),
                'minutes_to_funding': row.get('minutes_to_funding', np.nan),
            }

            # Prepare portfolio state
            current_equity = self.cash + (self.holdings * row['close'])
            # Calculate unrealized PnL: current value - cost basis
            current_value = self.holdings * row['close']
            unrealized_pnl = current_value - self.total_cost_basis
            portfolio_state = {
                'equity': current_equity,
                'cash': self.cash,
                'holdings': self.holdings,
                'unrealized_pnl': unrealized_pnl,
            }
            
            # Debug logging around shutdown time (first hour only, to avoid spam)
            if (self.verbose and 
                timestamp <= pd.Timestamp("2025-09-26 01:00:00", tz='UTC') and
                (abs(unrealized_pnl) > current_equity * 0.2 or 
                 self.algorithm.grid_manager.risk_level >= 3)):
                unrealized_pnl_pct = (unrealized_pnl / current_equity) if current_equity > 0 else 0.0
                print(f"[DEBUG {timestamp}] equity=${current_equity:,.2f} holdings={self.holdings:.4f} "
                      f"cost_basis=${self.total_cost_basis:,.2f} unrealized_pnl=${unrealized_pnl:,.2f} "
                      f"({unrealized_pnl_pct:.2%}) price=${row['close']:,.2f}")

            # Process with TaoGrid algorithm
            order = self.algorithm.on_data(timestamp, bar_data, portfolio_state)

            # Execute orders (on_data returns order dict directly, or None)
            if order:
                executed = self.execute_order(order, bar_open=row['open'], market_price=row['close'], timestamp=timestamp)

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
            if self.collect_equity_detail:
                self.equity_curve.append({
                    'timestamp': timestamp,
                    'equity': current_equity,
                    'cash': self.cash,
                    'holdings': self.holdings,
                    'holdings_value': self.holdings * row['close'],
                })
            else:
                self._equity_timestamps.append(timestamp)
                self._equity_values.append(float(current_equity))

        if self.verbose:
            print()
            print("  Backtest completed!")
            print()

        # Calculate metrics
        metrics = self.calculate_metrics()

        equity_df = (
            pd.DataFrame(self.equity_curve)
            if self.collect_equity_detail
            else pd.DataFrame({"timestamp": self._equity_timestamps, "equity": self._equity_values})
        )

        return {
            'metrics': metrics,
            'equity_curve': equity_df,
            'trades': pd.DataFrame(self.trades) if self.trades else pd.DataFrame(),
            'orders': pd.DataFrame(self.orders) if self.orders else pd.DataFrame(),
        }

    def execute_order(self, order: dict, bar_open: float, market_price: float, timestamp: datetime) -> bool:
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
        
        # Execution price for LIMIT orders on OHLC bars:
        # - Buy limit: if bar opens below limit, you get filled at open (better); else at limit
        # - Sell limit: if bar opens above limit, you get filled at open (better); else at limit
        # This avoids unrealistic "overpay at limit even when market is far through the price".
        if grid_level_price is None:
            execution_price = market_price
        else:
            if direction == "buy":
                execution_price = min(float(grid_level_price), float(bar_open))
            else:
                execution_price = max(float(grid_level_price), float(bar_open))

        # Apply commission
        # NOTE: For limit orders, slippage should be 0 (or very small)
        # Limit orders execute at the specified price, so no slippage
        commission_rate = float(self.config.maker_fee)
        slippage_rate = 0.0  # 0% - limit orders execute at grid level price, no slippage

        if direction == 'buy':
            # Buy BTC - Add to long positions queue
            cost = size * execution_price
            commission = cost * commission_rate
            slippage = cost * slippage_rate
            total_cost = cost + commission + slippage

            # Leverage / margin constraint (simplified):
            # Allow cash to go negative, but constrain position notional by equity * leverage.
            equity = self.cash + (self.holdings * market_price)
            max_notional = equity * float(self.config.leverage)
            new_notional = abs(self.holdings + size) * market_price
            if equity > 0 and new_notional <= max_notional:
                self.cash -= total_cost
                self.holdings += size
                # Update cost basis for unrealized PnL tracking
                self.total_cost_basis += size * execution_price

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
                    # factor diagnostics
                    'mr_z': float(order.get('mr_z')) if order.get('mr_z') is not None else np.nan,
                    'trend_score': float(order.get('trend_score')) if order.get('trend_score') is not None else np.nan,
                    'breakout_risk_down': float(order.get('breakout_risk_down')) if order.get('breakout_risk_down') is not None else np.nan,
                    'breakout_risk_up': float(order.get('breakout_risk_up')) if order.get('breakout_risk_up') is not None else np.nan,
                    'range_pos': float(order.get('range_pos')) if order.get('range_pos') is not None else np.nan,
                    'funding_rate': float(order.get('funding_rate')) if order.get('funding_rate') is not None else np.nan,
                    'vol_score': float(order.get('vol_score')) if order.get('vol_score') is not None else np.nan,
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
                
                # Track total cost basis reduction for accurate unrealized PnL calculation
                total_cost_basis_reduction = 0.0

                # Match against long positions using grid pairing (buy[i] -> sell[i])
                # Try grid_manager.match_sell_order first for proper grid pairing
                # If that fails, fall back to FIFO matching from long_positions to ensure cost_basis is updated
                remaining_sell_size = size
                matched_trades = []

                while remaining_sell_size > 0.0001:
                    # Use grid_manager to find matching buy position
                    match_result = self.algorithm.grid_manager.match_sell_order(
                        sell_level_index=level,
                        sell_size=remaining_sell_size
                    )
                    
                    if match_result is None:
                        # Grid pairing failed - fall back to FIFO matching from long_positions
                        # This ensures cost_basis is always updated, even if grid pairing logic has issues
                        if not self.long_positions:
                            break  # No positions to match
                        
                        # FIFO: match against first position in queue
                        buy_pos = self.long_positions[0]
                        buy_level_idx = buy_pos['level']
                        buy_price = buy_pos['price']
                        matched_size = min(remaining_sell_size, buy_pos['size'])
                    else:
                        buy_level_idx, buy_price, matched_size = match_result
                        
                        # Find corresponding position in long_positions
                        buy_pos = None
                        for pos in self.long_positions:
                            if pos['level'] == buy_level_idx and abs(pos['price'] - buy_price) < 0.01:
                                buy_pos = pos
                                break
                        
                        if buy_pos is None:
                            # Position not found in long_positions, try FIFO fallback
                            if not self.long_positions:
                                break
                            buy_pos = self.long_positions[0]
                            buy_level_idx = buy_pos['level']
                            buy_price = buy_pos['price']
                            matched_size = min(remaining_sell_size, buy_pos['size'])
                    
                    if buy_pos is None:
                        break
                    
                    buy_size = buy_pos['size']
                    buy_timestamp = buy_pos['timestamp']
                    buy_cost = buy_pos['entry_cost']
                    
                    # Calculate PnL for this matched trade
                    sell_proceeds_portion = (matched_size / size) * net_proceeds
                    sell_cost_portion = (matched_size / size) * (commission + slippage)
                    buy_cost_portion = (matched_size / buy_size) * buy_cost
                    
                    # Track cost basis reduction (based on entry price, not entry_cost which includes fees)
                    # cost_basis tracks the price basis, not the full cost including fees
                    matched_cost_basis = matched_size * buy_price
                    total_cost_basis_reduction += matched_cost_basis
                    
                    trade_pnl = sell_proceeds_portion - buy_cost_portion
                    trade_return_pct = trade_pnl / buy_cost_portion if buy_cost_portion > 0 else 0
                    
                    # Update realized PnL in grid manager for profit buffer
                    self.algorithm.grid_manager.update_realized_pnl(trade_pnl)

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
                
                # Update total cost basis after matching (reduce by matched positions' cost basis)
                self.total_cost_basis -= total_cost_basis_reduction
                # Ensure cost basis doesn't go negative
                self.total_cost_basis = max(0.0, self.total_cost_basis)
                
                # Safety check: if holdings is zero, cost basis should also be zero
                if abs(self.holdings) < 1e-8:
                    self.total_cost_basis = 0.0

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
                    # factor diagnostics
                    'mr_z': float(order.get('mr_z')) if order.get('mr_z') is not None else np.nan,
                    'trend_score': float(order.get('trend_score')) if order.get('trend_score') is not None else np.nan,
                    'breakout_risk_down': float(order.get('breakout_risk_down')) if order.get('breakout_risk_down') is not None else np.nan,
                    'breakout_risk_up': float(order.get('breakout_risk_up')) if order.get('breakout_risk_up') is not None else np.nan,
                    'range_pos': float(order.get('range_pos')) if order.get('range_pos') is not None else np.nan,
                    'funding_rate': float(order.get('funding_rate')) if order.get('funding_rate') is not None else np.nan,
                    'vol_score': float(order.get('vol_score')) if order.get('vol_score') is not None else np.nan,
                })

                return True  # Order executed

        return False  # Order not executed (insufficient cash/holdings)

    def calculate_metrics(self) -> dict:
        """Calculate performance metrics."""
        equity_df = (
            pd.DataFrame(self.equity_curve)
            if self.collect_equity_detail
            else pd.DataFrame({"timestamp": self._equity_timestamps, "equity": self._equity_values})
        )
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        initial_equity = self.config.initial_cash
        final_equity = equity_df['equity'].iloc[-1]
        total_return = (final_equity - initial_equity) / initial_equity

        # Drawdown
        cummax = equity_df['equity'].cummax()
        drawdown = (equity_df['equity'] - cummax) / cummax
        max_drawdown = drawdown.min()

        # Traditional Sharpe/Sortino: annualized using DAILY returns.
        # This avoids distortions from minute-level microstructure noise and incorrect scaling.
        annual_days = int(getattr(self.config, "sharpe_annualization_days", 365))

        equity_ts = equity_df.copy()
        equity_ts["timestamp"] = pd.to_datetime(equity_ts["timestamp"], utc=True)
        equity_ts = equity_ts.set_index("timestamp").sort_index()

        daily_equity = equity_ts["equity"].resample("1D").last().dropna()
        daily_returns = daily_equity.pct_change().dropna()

        if daily_returns.std() > 0:
            sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(annual_days))
        else:
            sharpe = 0.0

        negative_daily = daily_returns[daily_returns < 0]
        downside_std = float(negative_daily.std()) if len(negative_daily) > 0 else float(daily_returns.std())
        if downside_std > 0:
            sortino = float(daily_returns.mean() / downside_std * np.sqrt(annual_days))
        else:
            sortino = 0.0

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
            'sharpe_annualization_days': annual_days,
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
        
        if trades_df.empty and self.verbose:
            print("  Warning: No trades recorded. This may indicate:")
            print("    - Grid pairing logic issue")
            print("    - No buy/sell matches occurred")
            print("    - Need to re-run backtest with fixed logic")

        # Save orders
        if not results['orders'].empty:
            results['orders'].to_csv(output_dir / "orders.csv", index=False)

        if self.verbose:
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
    # Objective: Maximize ROE (per user preference) under 5x leverage and 20% max DD tolerance.
    config = TaoGridLeanConfig(
        name="TaoGrid Optimized - Max ROE (Perp)",
        description="Inventory-aware grid (perp maker fee 0.02%), focus on max ROE",

        # ========== S/R Levels ==========
        support=107000.0,
        resistance=123000.0,
        regime="NEUTRAL_RANGE",

        # ========== Grid Parameters ==========
        # With perp maker fee=0.02% (2x round trip = 0.04%), we can use thinner min_return.
        # Start from a high-ROE sweep winner:
        # - min_return = 0.12% (net)
        # - trading_costs = 0.04% (2 × 0.02% maker_fee, slippage=0)
        # - base_spacing = 0.16%
        # - grid_layers = 40 (denser grid)
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,  # more uniform sizing (less edge-heavy) to improve ROE in mid-range churn
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        # Disable MR+Trend factor for now: it behaved like heavy risk-control and reduced Sharpe
        # in ablation. We keep only breakout risk-off (Option 1).
        enable_mr_trend_factor=False,
        # Breakout risk factor (aggressive sweep winner, Sharpe-ranked, MaxDD<=20%):
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,
        # Range position asymmetry v2 (top-band only) - sweep winner:
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,

        # ========== Risk / Execution ==========
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=50.0,
        # Temporarily disable MM risk zone to test basic trading logic
        # After verifying basic functionality works, re-enable with adjusted thresholds
        enable_mm_risk_zone=False,
    )

    # Run backtest
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
    )
    results = runner.run()

    # Print summary
    runner.print_summary(results)

    # Save results
    output_dir = runner.output_dir or Path("run/results_lean_taogrid")
    runner.save_results(results, output_dir)

    if runner.verbose:
        print()
        print("Next steps:")
        print(f"1. Review metrics in: {output_dir}/metrics.json")
        print(f"2. Analyze trades in: {output_dir}/trades.csv")
        print(f"3. Plot equity curve from: {output_dir}/equity_curve.csv")


if __name__ == "__main__":
    main()
