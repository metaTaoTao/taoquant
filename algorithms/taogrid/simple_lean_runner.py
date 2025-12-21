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
        # Execution-model knobs (default keeps legacy behavior)
        max_fills_per_bar: int = 1,
        # --- "保换手 + 异常分钟抑制买入爆发" ---
        active_buy_levels: int | None = None,         # 常态同时挂出的买单层数 N（例如 6）
        cooldown_minutes: int = 0,                    # 异常后冷却分钟数（例如 2）
        abnormal_buy_fills_trigger: int = 0,          # 异常触发：当分钟买入成交次数 >= 2
        abnormal_total_fills_trigger: int = 0,        # 异常触发：当分钟总成交次数 >= 3
        abnormal_buy_notional_frac_equity: float = 0.0,  # 异常触发：当分钟新增买入 notional >= x * equity（例如 0.03）
        abnormal_range_mult_spacing: float = 0.0,     # 异常触发：振幅 >= k * spacing（例如 4）
        cooldown_active_buy_levels: int = 0,          # 冷却期仅保留的买单层数（例如 2）
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
        self.max_fills_per_bar = max(1, int(max_fills_per_bar))
        self.active_buy_levels = None if active_buy_levels is None else max(0, int(active_buy_levels))
        self.cooldown_minutes = max(0, int(cooldown_minutes))
        self.abnormal_buy_fills_trigger = max(0, int(abnormal_buy_fills_trigger))
        self.abnormal_total_fills_trigger = max(0, int(abnormal_total_fills_trigger))
        self.abnormal_buy_notional_frac_equity = float(abnormal_buy_notional_frac_equity)
        self.abnormal_range_mult_spacing = float(abnormal_range_mult_spacing)
        self.cooldown_active_buy_levels = max(0, int(cooldown_active_buy_levels))
        # internal cooldown state
        self._buy_cooldown_until: datetime | None = None
        self._spacing_pct_est: float | None = None
        self._last_mid_shift_bar_index: int = -10**9

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
        # Position books (separate long/short to support hedge overlay)
        self.long_holdings = 0.0   # BTC quantity (>=0)
        self.short_holdings = 0.0  # BTC quantity (>=0)
        # Backward-compatible net holdings view (long - short)
        self.holdings = 0.0
        # Long/short cost basis:
        # - For long: sum(size * entry_price)
        # - For short: sum(size * entry_price) for open shorts (used for unrealized PnL)
        self.total_cost_basis = 0.0  # long cost basis
        self.total_short_entry_value = 0.0  # short entry value for open shorts
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

    def _ensure_spacing_estimate(self) -> None:
        """Estimate grid spacing pct from current grid levels (best-effort)."""
        if self._spacing_pct_est is not None:
            return
        gm = self.algorithm.grid_manager
        if gm.buy_levels is None or gm.sell_levels is None:
            return
        if len(gm.buy_levels) == 0 or len(gm.sell_levels) == 0:
            return
        i = 0
        buy = float(gm.buy_levels[i])
        sell = float(gm.sell_levels[i])
        if buy > 0 and sell > 0:
            self._spacing_pct_est = max(0.0, (sell / buy) - 1.0)

    def _apply_active_buy_levels_filter(self, current_price: float, keep_levels: int) -> None:
        """
        Keep only the nearest `keep_levels` BUY pending orders (below current price).

        This is an execution-layer risk control: reduce simultaneous exposure to many buy levels
        while keeping SELL orders intact to preserve de-inventory / churn.
        """
        if keep_levels <= 0:
            return

        gm = self.algorithm.grid_manager
        pending = gm.pending_limit_orders
        if not pending:
            return

        # IMPORTANT:
        # Do NOT delete orders from pending_limit_orders; that would permanently remove them and kill turnover.
        # Instead, flip their `placed` flag (enable/disable) so they can be re-enabled later.

        buy_orders = [o for o in pending if o.get("direction") == "buy"]
        if not buy_orders:
            return

        # Eligible BUY orders for placement are those below/at current price (true limit order)
        eligible = [o for o in buy_orders if float(o.get("price", 0.0)) <= float(current_price)]
        if len(eligible) <= keep_levels:
            # Enable all eligible, disable ineligible (above market)
            for o in buy_orders:
                o["placed"] = float(o.get("price", 0.0)) <= float(current_price)
                if not o["placed"]:
                    o["triggered"] = False
            return

        # Sort eligible by distance to current price (closest first), keep top N
        eligible_sorted = sorted(eligible, key=lambda o: abs(float(current_price) - float(o.get("price", 0.0))))
        keep_ids = {(o.get("direction"), o.get("level_index")) for o in eligible_sorted[:keep_levels]}

        # Enable kept orders; disable the rest (and clear triggered state)
        for o in buy_orders:
            oid = (o.get("direction"), o.get("level_index"))
            is_eligible = float(o.get("price", 0.0)) <= float(current_price)
            o["placed"] = bool(is_eligible and oid in keep_ids)
            if not o["placed"]:
                o["triggered"] = False

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

        # Estimate spacing once grid is ready
        self._ensure_spacing_estimate()

        for i, (timestamp, row) in enumerate(data.iterrows()):
            if self.verbose and i % self.progress_every == 0:
                print(f"  Processing bar {i}/{len(data)} ({i/len(data)*100:.1f}%)", end="\r")
            
            # Periodic filled_levels summary log (every 1000 bars)
            if i > 0 and i % 1000 == 0 and getattr(self.algorithm.config, "enable_console_log", False):
                filled_levels = self.algorithm.grid_manager.filled_levels
                filled_count = len(filled_levels)
                filled_keys = list(filled_levels.keys())[:10]  # Show first 10
                pending_orders_count = len(self.algorithm.grid_manager.pending_limit_orders)
                buy_positions_count = sum(len(positions) for positions in self.algorithm.grid_manager.buy_positions.values())
                print(f"\n[FILLED_LEVELS_SUMMARY] Bar {i} @ {timestamp}: filled_levels={filled_count}, pending_orders={pending_orders_count}, buy_positions={buy_positions_count}, samples={filled_keys}")

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

            # Optional: Mid shift (recenter grid) when market stays in upper/lower band AND we are flat.
            # Designed to capture "high-band oscillation" alpha in long-only mode.
            # Safety: only recenter when flat (no holdings + no open buy_positions) to avoid breaking pairing.
            if getattr(self.config, "enable_mid_shift", False) and int(getattr(self.config, "mid_shift_threshold", 0)) > 0:
                cooldown = int(getattr(self.config, "mid_shift_threshold", 0))
                if (i - self._last_mid_shift_bar_index) >= cooldown:
                    rp = float(row.get("range_pos", 0.5))
                    trigger = float(getattr(self.config, "mid_shift_range_pos_trigger", 0.15))
                    flat_thr = float(getattr(self.config, "mid_shift_flat_holdings_btc", 0.0005))
                    is_flat = (abs(float(self.long_holdings)) <= flat_thr) and (abs(float(self.short_holdings)) <= flat_thr)
                    no_positions = sum(len(v) for v in self.algorithm.grid_manager.buy_positions.values()) == 0
                    if is_flat and no_positions and abs(rp - 0.5) >= trigger:
                        window = data.loc[:timestamp].tail(100)
                        if len(window) >= 50:
                            self.algorithm.grid_manager.setup_grid(window)
                            # Reset spacing estimate (grid changed)
                            self._spacing_pct_est = None
                            self._ensure_spacing_estimate()
                            self._last_mid_shift_bar_index = i
                            if self.verbose:
                                print(
                                    f"\n[MID_SHIFT] Bar {i} @ {timestamp}: recentered grid "
                                    f"(range_pos={rp:.2f}, price={float(row['close']):,.0f})"
                                )

            # Prepare portfolio state (separate long/short books)
            price = float(row["close"])
            current_equity = self.cash + (self.long_holdings * price) - (self.short_holdings * price)
            # Calculate unrealized PnL for a simplified perp model:
            # - Long PnL: (long_value - long_cost_basis)
            # - Short PnL: (short_entry_value - short_value)
            long_value = float(self.long_holdings) * price
            short_value = float(self.short_holdings) * price
            unrealized_pnl = (long_value - float(self.total_cost_basis)) + (float(self.total_short_entry_value) - short_value)
            portfolio_state = {
                'equity': current_equity,
                'cash': self.cash,
                # keep net holdings for legacy code paths
                'holdings': float(self.long_holdings) - float(self.short_holdings),
                'long_holdings': float(self.long_holdings),
                'short_holdings': float(self.short_holdings),
                'unrealized_pnl': unrealized_pnl,
            }

            # Execution-layer policy: active BUY levels + abnormal-minute cooldown
            in_cooldown = self._buy_cooldown_until is not None and timestamp < self._buy_cooldown_until
            if self.active_buy_levels is not None and self.active_buy_levels > 0:
                keep_n = self.cooldown_active_buy_levels if in_cooldown and self.cooldown_active_buy_levels > 0 else self.active_buy_levels
                self._apply_active_buy_levels_filter(current_price=float(row["close"]), keep_levels=int(keep_n))

            # Abnormal range trigger (optional): use spacing estimate
            bar_range_pct = (float(row["high"]) - float(row["low"])) / float(row["close"]) if float(row["close"]) > 0 else 0.0
            spacing_pct = float(self._spacing_pct_est) if self._spacing_pct_est is not None else 0.0
            range_abnormal = (
                self.abnormal_range_mult_spacing > 0
                and spacing_pct > 0
                and bar_range_pct >= float(self.abnormal_range_mult_spacing) * spacing_pct
            )
            if range_abnormal and self.cooldown_minutes > 0 and not in_cooldown:
                self._buy_cooldown_until = timestamp + pd.Timedelta(minutes=int(self.cooldown_minutes))
                in_cooldown = True
            
            # Debug logging around shutdown time (first hour only, to avoid spam)
            if (self.verbose and 
                timestamp <= pd.Timestamp("2025-09-26 01:00:00", tz='UTC') and
                (abs(unrealized_pnl) > current_equity * 0.2 or 
                 self.algorithm.grid_manager.risk_level >= 3)):
                unrealized_pnl_pct = (unrealized_pnl / current_equity) if current_equity > 0 else 0.0
                net_holdings = float(self.long_holdings) - float(self.short_holdings)
                print(
                    f"[DEBUG {timestamp}] equity=${current_equity:,.2f} "
                    f"long={self.long_holdings:.4f} short={self.short_holdings:.4f} net={net_holdings:.4f} "
                      f"cost_basis=${self.total_cost_basis:,.2f} unrealized_pnl=${unrealized_pnl:,.2f} "
                    f"({unrealized_pnl_pct:.2%}) price=${row['close']:,.2f}"
                )

            # Process with TaoGrid algorithm (allow multiple fills per bar, bounded)
            fills_this_bar = 0
            buy_fills_this_bar = 0
            buy_notional_added_this_bar = 0.0
            # Abnormal trigger notional threshold is defined in equity terms (NOT multiplied by leverage)
            buy_notional_abnormal_threshold = (
                max(0.0, float(self.abnormal_buy_notional_frac_equity)) * float(current_equity)
                if self.abnormal_buy_notional_frac_equity > 0 and float(current_equity) > 0
                else None
            )

            while fills_this_bar < self.max_fills_per_bar:
                order = self.algorithm.on_data(timestamp, bar_data, portfolio_state)
                if not order:
                    break

                # If in cooldown, do not allow new BUY executions (SELL is allowed)
                if in_cooldown and order["direction"] == "buy":
                    self.algorithm.grid_manager.reset_triggered_orders()
                    break

                # Log order received
                if getattr(self.config, "enable_console_log", False):
                    print(
                        f"[ORDER_EXECUTE] Received {order['direction'].upper()} "
                        f"L{order['level']+1} @ ${order['price']:,.0f}, size={order['quantity']:.4f} BTC"
                    )

                executed = self.execute_order(order, bar_open=row['open'], market_price=row['close'], timestamp=timestamp)

                if executed:
                    fills_this_bar += 1
                    if order["direction"] == "buy":
                        buy_fills_this_bar += 1
                        # Market orders have price=None; use current close as proxy notional.
                        px = float(order["price"]) if order.get("price") is not None else float(row["close"])
                        buy_notional_added_this_bar += float(order["quantity"]) * px

                    if getattr(self.config, "enable_console_log", False):
                        print(f"[ORDER_EXECUTE] {order['direction'].upper()} L{order['level']+1} EXECUTED successfully")

                    # Update grid state and place new limit orders
                    self.algorithm.on_order_filled(order)

                    # Keep grid_manager state consistent for trade recording
                    if order['direction'] == 'sell' and order.get("leg") is None:
                        _ = self.algorithm.grid_manager.match_sell_order(
                            sell_level_index=order['level'],
                            sell_size=order['quantity']
                        )

                    # Refresh portfolio_state for possible next fill in the same bar
                    price = float(row["close"])
                    self.holdings = float(self.long_holdings) - float(self.short_holdings)
                    current_equity = self.cash + (self.long_holdings * price) - (self.short_holdings * price)
                    long_value = float(self.long_holdings) * price
                    short_value = float(self.short_holdings) * price
                    unrealized_pnl = (long_value - float(self.total_cost_basis)) + (float(self.total_short_entry_value) - short_value)
                    portfolio_state = {
                        'equity': current_equity,
                        'cash': self.cash,
                        'holdings': float(self.long_holdings) - float(self.short_holdings),
                        'long_holdings': float(self.long_holdings),
                        'short_holdings': float(self.short_holdings),
                        'unrealized_pnl': unrealized_pnl,
                    }

                    # Check abnormal-minute triggers and enter cooldown (BUY only)
                    if self.cooldown_minutes > 0 and not in_cooldown:
                        abnormal_by_count = (
                            (self.abnormal_buy_fills_trigger > 0 and buy_fills_this_bar >= self.abnormal_buy_fills_trigger)
                            or (self.abnormal_total_fills_trigger > 0 and fills_this_bar >= self.abnormal_total_fills_trigger)
                        )
                        abnormal_by_notional = (
                            buy_notional_abnormal_threshold is not None
                            and buy_notional_added_this_bar >= float(buy_notional_abnormal_threshold)
                        )
                        if abnormal_by_count or abnormal_by_notional or range_abnormal:
                            self._buy_cooldown_until = timestamp + pd.Timedelta(minutes=int(self.cooldown_minutes))
                            in_cooldown = True
                            # Apply stricter buy-level filter immediately for remainder of this bar
                            if self.active_buy_levels is not None and self.cooldown_active_buy_levels > 0:
                                self._apply_active_buy_levels_filter(
                                    current_price=float(row["close"]),
                                    keep_levels=int(self.cooldown_active_buy_levels),
                                )
                else:
                    # Release trigger so it can be evaluated next bar
                    self.algorithm.grid_manager.reset_triggered_orders()
                    if getattr(self.config, "enable_console_log", False):
                        print(f"[ORDER_EXECUTE] {order['direction'].upper()} L{order['level']+1} FAILED to execute")
                    break

            # Record equity
            if self.collect_equity_detail:
                self.equity_curve.append({
                    'timestamp': timestamp,
                    'equity': current_equity,
                    'cash': self.cash,
                    'holdings': float(self.long_holdings) - float(self.short_holdings),
                    'holdings_value': (float(self.long_holdings) - float(self.short_holdings)) * float(row['close']),
                    'unrealized_pnl': unrealized_pnl,  # CRITICAL: Add for risk control diagnosis
                    'long_holdings': float(self.long_holdings),
                    'short_holdings': float(self.short_holdings),
                    'cost_basis': float(self.total_cost_basis),
                    'grid_enabled': self.algorithm.grid_manager.grid_enabled,
                    'risk_level': self.algorithm.grid_manager.risk_level,
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
        leg = order.get("leg")
        
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

        if leg == "short_open" and direction == "sell":
            # OPEN SHORT (sell to open)
            proceeds = size * execution_price
            commission = proceeds * commission_rate
            slippage = proceeds * slippage_rate
            net_proceeds = proceeds - commission - slippage

            # Margin constraint (gross exposure): (long_notional + short_notional) <= equity * leverage
            equity = self.cash + (float(self.long_holdings) * float(market_price)) - (float(self.short_holdings) * float(market_price))
            max_notional = equity * float(self.config.leverage)
            new_gross_notional = (float(self.long_holdings) * float(market_price)) + ((float(self.short_holdings) + float(size)) * float(market_price))
            if equity > 0 and new_gross_notional <= max_notional:
                self.cash += net_proceeds
                self.short_holdings += float(size)
                self.holdings = float(self.long_holdings) - float(self.short_holdings)
                self.total_short_entry_value += size * execution_price
                self.short_positions.append({
                    "size": size,
                    "price": execution_price,
                    "level": level,
                    "timestamp": timestamp,
                    "entry_proceeds": net_proceeds,
                })
                self.orders.append({
                    "timestamp": timestamp,
                    "direction": "sell",
                    "size": size,
                    "price": execution_price,
                    "level": level,
                    "market_price": market_price,
                    "proceeds": net_proceeds,
                    "commission": commission,
                    "slippage": slippage,
                    "leg": "short_open",
                })
                return True
            return False

        if leg == "short_cover" and direction == "buy":
            # COVER SHORT (buy to close)
            if float(self.short_holdings) <= 1e-12:
                return False
            cover_size = min(float(size), float(self.short_holdings))

            cost = cover_size * execution_price
            commission = cost * commission_rate
            slippage = cost * slippage_rate
            total_cost = cost + commission + slippage

            # Allow margin-style cover (cash can go negative), constrained by gross exposure <= equity * leverage.
            equity = self.cash + (float(self.long_holdings) * float(market_price)) - (float(self.short_holdings) * float(market_price))
            max_notional = equity * float(self.config.leverage)
            new_gross_notional = (float(self.long_holdings) * float(market_price)) + (max(0.0, float(self.short_holdings) - float(cover_size)) * float(market_price))
            if not (equity > 0 and new_gross_notional <= max_notional):
                return False

            self.cash -= total_cost
            self.short_holdings = max(0.0, float(self.short_holdings) - float(cover_size))
            self.holdings = float(self.long_holdings) - float(self.short_holdings)

            remaining = cover_size
            total_entry_value_reduction = 0.0
            matched_trades = []
            while remaining > 0.0001 and self.short_positions:
                pos = self.short_positions[0]
                pos_size = float(pos["size"])
                matched = min(remaining, pos_size)
                sell_price = float(pos["price"])
                sell_ts = pos["timestamp"]
                entry_proceeds = float(pos.get("entry_proceeds", matched * sell_price))

                entry_proceeds_portion = (matched / pos_size) * entry_proceeds if pos_size > 0 else 0.0
                exit_cost_portion = (matched / cover_size) * total_cost if cover_size > 0 else 0.0

                pnl = entry_proceeds_portion - exit_cost_portion
                # return based on short notional at entry
                denom = matched * sell_price if sell_price > 0 else 0.0
                ret = pnl / denom if denom > 0 else 0.0

                matched_trades.append({
                    "entry_timestamp": sell_ts,
                    "exit_timestamp": timestamp,
                    "entry_price": sell_price,
                    "exit_price": execution_price,
                    "entry_level": int(pos.get("level", -1)),
                    "exit_level": level,
                    "size": matched,
                    "pnl": pnl,
                    "return_pct": ret,
                    "holding_period": (timestamp - sell_ts).total_seconds() / 3600,
                    "direction": "short",
                })

                total_entry_value_reduction += matched * sell_price

                pos["size"] -= matched
                pos["entry_proceeds"] = entry_proceeds - entry_proceeds_portion
                remaining -= matched
                if pos["size"] < 0.0001:
                    self.short_positions.pop(0)

            self.total_short_entry_value = max(0.0, float(self.total_short_entry_value) - total_entry_value_reduction)
            self.trades.extend(matched_trades)

            self.orders.append({
                "timestamp": timestamp,
                "direction": "buy",
                "size": cover_size,
                "price": execution_price,
                "level": level,
                "market_price": market_price,
                "cost": total_cost,
                "commission": commission,
                "slippage": slippage,
                "matched_trades": len(matched_trades),
                "leg": "short_cover",
            })
            return True

        if direction == 'buy':
            # Buy BTC - Add to long positions queue
            cost = size * execution_price
            commission = cost * commission_rate
            slippage = cost * slippage_rate
            total_cost = cost + commission + slippage

            # Leverage / margin constraint (simplified):
            # Allow cash to go negative, but constrain gross exposure by equity * leverage.
            equity = self.cash + (float(self.long_holdings) * float(market_price)) - (float(self.short_holdings) * float(market_price))
            max_notional = equity * float(self.config.leverage)
            new_gross_notional = ((float(self.long_holdings) + float(size)) * float(market_price)) + (float(self.short_holdings) * float(market_price))
            if equity > 0 and new_gross_notional <= max_notional:
                self.cash -= total_cost
                self.long_holdings += float(size)
                self.holdings = float(self.long_holdings) - float(self.short_holdings)
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
                
                # Log buy execution
                if getattr(self.config, "enable_console_log", False):
                    print(f"[BUY_EXECUTED] L{level+1} @ ${execution_price:,.0f}, size={size:.4f} BTC, long={self.long_holdings:.4f}, short={self.short_holdings:.4f}, net={self.holdings:.4f}, long_positions_count={len(self.long_positions)}, cost_basis=${self.total_cost_basis:,.0f}")

                # Record buy order to orders list
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
                    'leg': leg,
                    # factor diagnostics
                    'mr_z': float(order.get('mr_z')) if order.get('mr_z') is not None else np.nan,
                    'trend_score': float(order.get('trend_score')) if order.get('trend_score') is not None else np.nan,
                    'breakout_risk_down': float(order.get('breakout_risk_down')) if order.get('breakout_risk_down') is not None else np.nan,
                    'breakout_risk_up': float(order.get('breakout_risk_up')) if order.get('breakout_risk_up') is not None else np.nan,
                    'range_pos': float(order.get('range_pos')) if order.get('range_pos') is not None else np.nan,
                    'funding_rate': float(order.get('funding_rate')) if order.get('funding_rate') is not None else np.nan,
                    'vol_score': float(order.get('vol_score')) if order.get('vol_score') is not None else np.nan,
                })

                return True  # Order executed successfully
            else:
                # Log buy rejection
                if getattr(self.config, "enable_console_log", False):
                    print(f"[BUY_REJECTED] L{level+1} @ ${execution_price:,.0f}, size={size:.4f} BTC - leverage constraint: new_notional=${new_notional:,.0f} > max_notional=${max_notional:,.0f} (equity=${equity:,.0f}, leverage={self.config.leverage}x)")

                return False  # Order NOT executed (rejected due to leverage constraint)

        elif direction == 'sell':
            # Sell BTC - Match against long positions using GRID PAIRING
            if float(size) <= float(self.long_holdings):
                proceeds = size * execution_price
                commission = proceeds * commission_rate
                slippage = proceeds * slippage_rate
                net_proceeds = proceeds - commission - slippage

                self.cash += net_proceeds
                self.long_holdings = max(0.0, float(self.long_holdings) - float(size))
                self.holdings = float(self.long_holdings) - float(self.short_holdings)
                
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
                        # DEBUG: Log why grid pairing failed
                        if True:  # Always log for debugging
                            # Show what buy positions exist
                            buy_positions_summary = []
                            for buy_idx, positions in self.algorithm.grid_manager.buy_positions.items():
                                for pos in positions:
                                    target = pos.get('target_sell_level', -1)
                                    buy_positions_summary.append(f"Buy[{buy_idx}]→Sell[{target}]")

                            if not hasattr(self, '_match_failures'):
                                self._match_failures = []
                            self._match_failures.append({
                                'timestamp': timestamp,
                                'sell_level': level,
                                'available_buy_positions': buy_positions_summary[:10],  # First 10
                                'total_buy_positions': sum(len(p) for p in self.algorithm.grid_manager.buy_positions.values())
                            })

                        if getattr(self.config, "enable_console_log", False):
                            print(f"[SELL_MATCH_FIFO] Grid pairing failed for SELL L{level+1}, falling back to FIFO (remaining_size={remaining_sell_size:.4f}, long_positions_count={len(self.long_positions)})")
                        if not self.long_positions:
                            if getattr(self.config, "enable_console_log", False):
                                print("[SELL_MATCH_FIFO] No long positions available for FIFO matching")
                            break  # No positions to match
                        
                        # FIFO: match against first position in queue
                        buy_pos = self.long_positions[0]
                        buy_level_idx = buy_pos['level']
                        buy_price = buy_pos['price']
                        matched_size = min(remaining_sell_size, buy_pos['size'])
                        
                        if getattr(self.config, "enable_console_log", False):
                            print(f"[SELL_MATCH_FIFO] FIFO match: SELL L{level+1} matched with BUY L{buy_level_idx+1} @ ${buy_price:,.0f}, matched_size={matched_size:.4f}")
                        
                        # FIFO: match against first position in queue
                        buy_pos = self.long_positions[0]
                        buy_level_idx = buy_pos['level']
                        buy_price = buy_pos['price']
                        matched_size = min(remaining_sell_size, buy_pos['size'])
                    else:
                        buy_level_idx, buy_price, matched_size = match_result
                        
                        # Find corresponding position in long_positions
                        # Note: execution_price may differ from grid_level_price due to favorable fills
                        # (e.g., buy limit at $98,834 but bar opened at $98,800 -> filled at $98,800)
                        # So we use a reasonable tolerance (~0.1% or $100 for BTC prices)
                        buy_pos = None
                        price_tolerance = max(100.0, buy_price * 0.001)  # 0.1% or $100, whichever is larger
                        for pos in self.long_positions:
                            if pos['level'] == buy_level_idx and abs(pos['price'] - buy_price) < price_tolerance:
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
                    # Note: we keep this for diagnostics parity, but it is not used in PnL
                    # (PnL is computed using net_proceeds and buy_cost_portion).
                    # sell_cost_portion = (matched_size / size) * (commission + slippage)
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
                    
                    # Log matched trade
                    if getattr(self.config, "enable_console_log", False):
                        print(f"[TRADE_MATCHED] BUY L{buy_level_idx+1} @ ${buy_price:,.0f} -> SELL L{level+1} @ ${execution_price:,.0f}, size={matched_size:.4f} BTC, PnL=${trade_pnl:,.2f} ({trade_return_pct:.2%}), holding={trade_pnl/buy_price if buy_price > 0 else 0:.1f}h")

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
                
                # Safety check: if long holdings is zero, long cost basis should also be zero
                if abs(float(self.long_holdings)) < 1e-8:
                    self.total_cost_basis = 0.0

                # Record all matched trades
                self.trades.extend(matched_trades)
                
                # Log trade recording and sell execution
                if getattr(self.config, "enable_console_log", False):
                    print(f"[SELL_EXECUTED] L{level+1} @ ${execution_price:,.0f}, size={size:.4f} BTC, long={self.long_holdings:.4f}, short={self.short_holdings:.4f}, net={self.holdings:.4f}, long_positions_count={len(self.long_positions)}, cost_basis=${self.total_cost_basis:,.0f}")
                    print(f"[TRADE_RECORD] SELL L{level+1} @ ${execution_price:,.0f} - recorded {len(matched_trades)} matched trades (total trades now: {len(self.trades)})")
                    if len(matched_trades) == 0:
                        print(f"[WARNING] SELL L{level+1} executed but no trades recorded! This should not happen.")

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
                    'leg': leg,
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

        # Initialize ratios to avoid unbound locals
        sharpe = 0.0
        sortino = 0.0

        # Annualized return (CAGR-style, based on backtest span)
        annual_return = 0.0
        if len(daily_equity) >= 2:
            span_days = (daily_equity.index[-1] - daily_equity.index[0]).days
            if span_days > 0 and daily_equity.iloc[0] > 0:
                years = span_days / float(annual_days)
                if years > 0:
                    annual_return = float((daily_equity.iloc[-1] / daily_equity.iloc[0]) ** (1.0 / years) - 1.0)

        # Ulcer Index (drawdown depth + duration): sqrt(mean(drawdown_pct^2))
        # Use daily equity for stability.
        ulcer_index = 0.0
        if len(daily_equity) >= 2:
            dd = (daily_equity.cummax() - daily_equity) / daily_equity.cummax()  # 0..1
            dd_pct = (dd * 100.0).astype(float)
            ulcer_index = float(np.sqrt(np.mean(np.square(dd_pct)))) if len(dd_pct) > 0 else 0.0

        # Calmar ratio = annual_return / |max_drawdown|
        calmar = 0.0
        if max_drawdown < 0:
            calmar = float(annual_return / abs(float(max_drawdown))) if abs(float(max_drawdown)) > 1e-12 else 0.0

        # Sharpe / |MaxDD| (simple risk-adjusted stability ratio)
        # NOTE: compute AFTER sharpe is computed below (sharpe is initialized to 0.0 above).
        sharpe_to_dd = 0.0

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

        if max_drawdown < 0:
            sharpe_to_dd = float(sharpe / abs(float(max_drawdown))) if abs(float(max_drawdown)) > 1e-12 else 0.0

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
            'annual_return': annual_return,
            'total_pnl': final_equity - initial_equity,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': calmar,
            'sharpe_to_dd': sharpe_to_dd,
            'ulcer_index': ulcer_index,
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
        if 'annual_return' in metrics:
            print(f"  Annual Return:   {metrics['annual_return']:.2%}")
        print(f"  Total PnL:       ${metrics['total_pnl']:,.2f}")
        print(f"  Final Equity:    ${metrics['final_equity']:,.2f}")
        print(f"  Max Drawdown:    {metrics['max_drawdown']:.2%}")
        print(f"  Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")
        print(f"  Sortino Ratio:   {metrics['sortino_ratio']:.2f}")
        if 'calmar_ratio' in metrics:
            print(f"  Calmar Ratio:    {metrics['calmar_ratio']:.2f}")
        if 'sharpe_to_dd' in metrics:
            print(f"  Sharpe/|MaxDD|:  {metrics['sharpe_to_dd']:.2f}")
        if 'ulcer_index' in metrics:
            print(f"  Ulcer Index:     {metrics['ulcer_index']:.2f}")
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
    # STAGE 1: Extended Backtest Validation (6 months, 5x leverage, all risk controls enabled)
    # Objective: Verify strategy robustness across different market conditions
    config = TaoGridLeanConfig(
        name="TaoGrid Stage 1 - Extended Validation",
        description="6-month backtest with full risk controls (5x leverage, all factors enabled)",

        # ========== S/R Levels ==========
        # Test period: 2024-12-30 to 2025-01-20
        support=90000.0,
        resistance=108000.0,
        regime="NEUTRAL_RANGE",  # CONTROL TEST: Neutral strategy

        # ========== Grid Parameters ==========
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,  # Mild volatility adjustment (multiplicative formula: 0.1-0.3 for ranging)
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,

        # ========== STAGE 1: ENABLE ALL RISK CONTROLS ==========
        # MR+Trend factor: Enable to test downtrend protection
        enable_mr_trend_factor=True,
        mr_z_lookback=240,
        mr_z_ref=2.0,
        mr_min_mult=1.0,
        trend_ema_period=120,
        trend_slope_lookback=60,
        trend_slope_ref=0.001,
        trend_block_threshold=0.80,
        trend_buy_k=0.40,
        trend_buy_floor=0.50,

        # Breakout risk factor
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,

        # Range position asymmetry v2
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,

        # Funding factor
        enable_funding_factor=True,

        # Volatility regime factor
        enable_vol_regime_factor=True,

        # ========== Risk / Execution ==========
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=5.0,  # REDUCED FROM 50x TO 5x (conservative)

        # ========== MM RISK ZONE: ENABLE FOR FULL PROTECTION ==========
        enable_mm_risk_zone=True,
        mm_risk_level1_buy_mult=0.2,
        mm_risk_level1_sell_mult=3.0,
        mm_risk_inventory_penalty=0.5,
        mm_risk_level2_buy_mult=0.1,
        mm_risk_level2_sell_mult=4.0,
        mm_risk_level3_atr_mult=2.0,
        mm_risk_level3_buy_mult=0.05,
        mm_risk_level3_sell_mult=5.0,
        max_risk_atr_mult=3.0,
        max_risk_loss_pct=0.30,
        max_risk_inventory_pct=0.80,
        enable_profit_buffer=True,
        profit_buffer_ratio=0.5,

        # Disable console log to speed up backtest
        enable_console_log=False,
    )

    # Run backtest - CONTROL TEST: Same period, NEUTRAL_RANGE
    print("=" * 80)
    print("CONTROL TEST: Neutral Range (50/50)")
    print("=" * 80)
    print(f"Period: ~22 days (2024-12-30 to 2025-01-20)")
    print(f"Market Condition: Same market as BULLISH test")
    print(f"Support/Resistance: $90,000 - $108,000")
    print(f"Regime: NEUTRAL_RANGE (50% buy, 50% sell)")
    print(f"Leverage: 5x")
    print(f"Risk Controls: ALL ENABLED")
    print(f"  - MM Risk Zone: ENABLED")
    print(f"  - MR+Trend Factor: ENABLED")
    print(f"  - Breakout Risk: ENABLED")
    print(f"  - Funding Factor: ENABLED")
    print(f"  - Vol Regime: ENABLED")
    print("=" * 80)
    print()

    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2024, 12, 30, tzinfo=timezone.utc),
        end_date=datetime(2025, 1, 20, tzinfo=timezone.utc),
        verbose=True,
        progress_every=5000,  # Progress update every 5k bars
        output_dir=Path("run/results_neutral_controlled"),  # Separate dir for NEUTRAL test
    )
    results = runner.run()

    # Print summary
    runner.print_summary(results)

    # DEBUG: Analyze match failures
    if hasattr(runner, '_match_failures') and runner._match_failures:
        print()
        print("=" * 80)
        print("MATCH FAILURE ANALYSIS")
        print("=" * 80)
        print(f"Total match failures: {len(runner._match_failures)}")
        print()

        # Analyze first 10 failures
        print("First 10 match failures:")
        for i, failure in enumerate(runner._match_failures[:10]):
            print(f"\n{i+1}. Timestamp: {failure['timestamp']}")
            print(f"   Sell Level: {failure['sell_level']}")
            print(f"   Total buy positions: {failure['total_buy_positions']}")
            print(f"   Available: {', '.join(failure['available_buy_positions']) if failure['available_buy_positions'] else 'NONE'}")

        # Count failures by sell level
        from collections import Counter
        sell_level_failures = Counter(f['sell_level'] for f in runner._match_failures)
        print("\n\nMatch failures by sell level:")
        for level, count in sell_level_failures.most_common(10):
            print(f"  Level {level}: {count} failures")

        # Analyze pattern - are there buy positions but wrong target_sell_level?
        failures_with_positions = [f for f in runner._match_failures if f['total_buy_positions'] > 0]
        failures_without_positions = [f for f in runner._match_failures if f['total_buy_positions'] == 0]

        print(f"\n\nMatch failures WITH buy positions available: {len(failures_with_positions)} ({len(failures_with_positions)/len(runner._match_failures)*100:.1f}%)")
        print(f"Match failures WITHOUT any buy positions: {len(failures_without_positions)} ({len(failures_without_positions)/len(runner._match_failures)*100:.1f}%)")

        print("=" * 80)

    # Save results to separate directory for controlled test
    output_dir = runner.output_dir or Path("run/results_neutral_controlled")
    runner.save_results(results, output_dir)

    print()
    print("=" * 80)
    print("STAGE 1 VALIDATION CHECKLIST")
    print("=" * 80)
    print("Review the following metrics:")
    print(f"  1. Sharpe Ratio > 2.0? (Current: {results['metrics']['sharpe_ratio']:.2f})")
    print(f"  2. Max Drawdown < 20%? (Current: {results['metrics']['max_drawdown']:.2%})")
    print(f"  3. Avg Return/Trade > 0? (Current: {results['metrics']['avg_return_per_trade']:.4%})")
    print(f"  4. Win Rate > 60%? (Current: {results['metrics']['win_rate']:.2%})")

    # Calculate profit factor as proxy for profit/loss ratio
    win_rate = results['metrics']['win_rate']
    avg_win = results['metrics']['avg_win']
    avg_loss = abs(results['metrics']['avg_loss'])
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    print(f"  5. Profit/Loss Ratio > 1.5? (Current: {profit_loss_ratio:.2f})")
    print()
    print("Results saved to:")
    print(f"  - Metrics: {output_dir}/metrics.json")
    print(f"  - Trades: {output_dir}/trades.csv")
    print(f"  - Equity: {output_dir}/equity_curve.csv")
    print()

    # Quick pass/fail assessment
    all_passed = (
        results['metrics']['sharpe_ratio'] > 2.0 and
        results['metrics']['max_drawdown'] > -0.20 and
        results['metrics']['avg_return_per_trade'] > 0 and
        results['metrics']['win_rate'] > 0.60 and
        profit_loss_ratio > 1.5
    )

    if all_passed:
        print("[PASS] STAGE 1 PASSED - All validation criteria met!")
        print("   Next: Proceed to Stage 2 (Fix live code)")
    else:
        print("[FAIL] STAGE 1 FAILED - Some criteria not met")
        print("   Action: Review trades.csv and optimize parameters, or reconsider strategy")
    print("=" * 80)


if __name__ == "__main__":
    main()
