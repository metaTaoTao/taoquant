"""
Bitget Live Trading Runner.

This module provides real-time execution of TaoGrid strategy on Bitget exchange.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.live_logger import LiveLogger
from data.sources.bitget_sdk import BitgetSDKDataSource
from execution.engines.bitget_engine import BitgetExecutionEngine


class BitgetLiveRunner:
    """Bitget live trading runner."""

    def __init__(
        self,
        config: TaoGridLeanConfig,
        symbol: str,
        bitget_api_key: str,
        bitget_api_secret: str,
        bitget_passphrase: str,
        subaccount_uid: Optional[str] = None,
        dry_run: bool = False,
        log_dir: str = "logs/bitget_live",
        execution_model: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Bitget live runner.

        Parameters
        ----------
        config : TaoGridLeanConfig
            Strategy configuration
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        bitget_api_key : str
            Bitget API key
        bitget_api_secret : str
            Bitget API secret
        bitget_passphrase : str
            Bitget API passphrase
        subaccount_uid : str, optional
            Subaccount UID
        dry_run : bool
            If True, don't place actual orders
        log_dir : str
            Log directory
        """
        self.config = config
        self.symbol = symbol
        self.dry_run = dry_run
        self.subaccount_uid = subaccount_uid
        self.execution_model: Dict[str, Any] = execution_model or {}

        # Execution-model knobs (default matches SimpleLeanRunner)
        self.max_fills_per_bar = max(1, int(self.execution_model.get("max_fills_per_bar", 1)))
        abl = self.execution_model.get("active_buy_levels", None)
        self.active_buy_levels: Optional[int] = None if abl is None else max(0, int(abl))
        self.cooldown_minutes = max(0, int(self.execution_model.get("cooldown_minutes", 0)))
        self.abnormal_buy_fills_trigger = max(0, int(self.execution_model.get("abnormal_buy_fills_trigger", 0)))
        self.abnormal_total_fills_trigger = max(0, int(self.execution_model.get("abnormal_total_fills_trigger", 0)))
        self.abnormal_buy_notional_frac_equity = float(self.execution_model.get("abnormal_buy_notional_frac_equity", 0.0))
        self.abnormal_range_mult_spacing = float(self.execution_model.get("abnormal_range_mult_spacing", 0.0))
        self.cooldown_active_buy_levels = max(0, int(self.execution_model.get("cooldown_active_buy_levels", 0)))
        self._buy_cooldown_until: Optional[datetime] = None
        self._fills_this_bar: int = 0
        self._buy_fills_this_bar: int = 0
        self._buy_notional_added_this_bar: float = 0.0

        # Initialize logger
        self.logger = LiveLogger(log_dir=log_dir, name=f"bitget_live_{symbol}")

        # Initialize data source
        self.data_source = BitgetSDKDataSource(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            debug=True,
        )

        # Initialize execution engine
        self.execution_engine = BitgetExecutionEngine(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            subaccount_uid=subaccount_uid,
            debug=True,
        )

        # Initialize algorithm
        self.algorithm = TaoGridLeanAlgorithm(config)

        # Track last processed bar timestamp
        self.last_bar_timestamp: Optional[datetime] = None

        # Track pending orders (order_id -> order_info)
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        # Live bar index (monotonic) used by algorithm time-based guards
        self._bar_index: int = 0
        # Deterministic client order id prefix for idempotency / recovery
        self._client_oid_prefix: str = f"taogrid_{self.symbol}_"
        # Rolling bars window for factor computation
        self._recent_bars: Optional[pd.DataFrame] = None
        self._recent_bars_maxlen: int = 3000
        self._last_factor_state: Dict[str, Any] = {}

        # Initialize strategy
        self._initialize_strategy()
        # Bootstrap exchange grid: ensure resting limit orders exist (backtest-consistent)
        self._bootstrap_exchange_grid()

    def _in_cooldown(self, now_ts: datetime) -> bool:
        if self._buy_cooldown_until is None:
            return False
        try:
            return pd.Timestamp(now_ts) < pd.Timestamp(self._buy_cooldown_until)
        except Exception:
            return False

    def _estimate_spacing_pct(self) -> float:
        """
        Estimate grid spacing pct from generated levels.
        We use sell[0] / buy[0] - 1 when available.
        """
        gm = self.algorithm.grid_manager
        if gm.buy_levels is None or gm.sell_levels is None:
            return 0.0
        if len(gm.buy_levels) == 0 or len(gm.sell_levels) == 0:
            return 0.0
        try:
            b0 = float(gm.buy_levels[0])
            s0 = float(gm.sell_levels[0])
            if b0 > 0 and s0 > 0:
                return max(0.0, s0 / b0 - 1.0)
        except Exception:
            return 0.0
        return 0.0

    def _maybe_enter_cooldown(self, bar_ts: datetime, bar_high: float, bar_low: float, equity: float, close_px: float) -> None:
        """
        Match SimpleLeanRunner abnormal-minute cooldown idea:
        enter cooldown when fills/notional/range amplitude spikes, then reduce active buy levels.
        """
        if self.cooldown_minutes <= 0:
            return
        if self._in_cooldown(bar_ts):
            return

        abnormal = False
        if self.abnormal_buy_fills_trigger > 0 and self._buy_fills_this_bar >= self.abnormal_buy_fills_trigger:
            abnormal = True
        if self.abnormal_total_fills_trigger > 0 and self._fills_this_bar >= self.abnormal_total_fills_trigger:
            abnormal = True
        if self.abnormal_buy_notional_frac_equity > 0 and equity > 0:
            if self._buy_notional_added_this_bar >= self.abnormal_buy_notional_frac_equity * float(equity):
                abnormal = True
        if self.abnormal_range_mult_spacing > 0:
            sp = self._estimate_spacing_pct()
            spacing_abs = float(close_px) * float(sp)
            if spacing_abs > 0 and (float(bar_high) - float(bar_low)) >= float(self.abnormal_range_mult_spacing) * spacing_abs:
                abnormal = True

        if abnormal:
            self._buy_cooldown_until = pd.Timestamp(bar_ts) + pd.Timedelta(minutes=int(self.cooldown_minutes))
            self.logger.log_warning(
                f"[COOLDOWN] triggered until {self._buy_cooldown_until} "
                f"(fills={self._fills_this_bar}, buy_fills={self._buy_fills_this_bar}, "
                f"buy_notional={self._buy_notional_added_this_bar:.2f})"
            )

    def _initialize_strategy(self):
        """Initialize strategy with historical data."""
        self.logger.log_info("=" * 80)
        self.logger.log_info("Initializing TaoGrid Strategy")
        self.logger.log_info("=" * 80)

        # Get historical data for grid setup (use 1m to match backtest)
        # Use 30 days to get more stable ATR calculation
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        self.logger.log_info(f"Fetching historical data from {start_date} to {end_date}...")
        self.logger.log_info("Using 1m timeframe to match backtest")

        try:
            historical_data = self.data_source.get_klines(
                symbol=self.symbol,
                timeframe="1m",  # Match backtest timeframe
                start=start_date,
                end=end_date,
            )

            if historical_data.empty:
                raise ValueError("No historical data retrieved")

            self.logger.log_info(f"Retrieved {len(historical_data)} bars")

            # Initialize algorithm
            self.algorithm.initialize(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
                historical_data=historical_data,
            )

            self.logger.log_info("Strategy initialized successfully")
            self.logger.log_info("=" * 80)

        except Exception as e:
            self.logger.log_error(f"Failed to initialize strategy: {e}", exc_info=True)
            raise

    def _bootstrap_exchange_grid(self) -> None:
        """
        Ensure exchange open orders reflect the algorithm's pending grid orders.

        Backtest assumption: grid limit orders are already resting and get filled by price.
        Live must therefore place those limit orders on the exchange and react on fills.
        """
        if self.dry_run:
            self.logger.log_info("[DRY_RUN] Skip bootstrap order placement.")
            return

        # Current BitgetExecutionEngine is spot (defaultType=spot). Short overlay requires contracts.
        if bool(getattr(self.config, "enable_short_in_bearish", False)):
            self.logger.log_warning(
                "enable_short_in_bearish=True but Bitget engine is spot. "
                "Short overlay requires contract execution; disabling short for live."
            )
            self.config.enable_short_in_bearish = False

        cancelled = self.execution_engine.cancel_all_orders(
            symbol=self.symbol,
            client_oid_prefix=self._client_oid_prefix,
        )
        if cancelled > 0:
            self.logger.log_info(
                f"Cancelled {cancelled} previous TaoGrid orders (prefix={self._client_oid_prefix})"
            )

        # Seed internal ledger from current exchange holdings (restart-safe baseline).
        try:
            latest = self.data_source.get_latest_bar(self.symbol, "1m")
            last_px = float(latest["close"]) if latest else float(self.config.support)
            positions = self.execution_engine.get_positions(self.symbol)
            exch_holdings = 0.0
            for pos in positions:
                if pos.get("symbol") == self.symbol or pos.get("currency") == self.symbol.replace("USDT", ""):
                    exch_holdings = float(pos.get("quantity", 0.0) or 0.0)
                    break
            if exch_holdings > float(getattr(self.config, "short_flat_holdings_btc", 0.0005)):
                # Put the whole inventory into ledger at mark-to-market cost (conservative, avoids fake unrealized pnl).
                gm = self.algorithm.grid_manager
                if gm.buy_levels is not None and len(gm.buy_levels) > 0:
                    # choose nearest buy level index for pairing
                    diffs = [abs(float(p) - last_px) for p in gm.buy_levels]
                    idx = int(diffs.index(min(diffs)))
                else:
                    idx = 0
                gm.buy_positions.setdefault(idx, []).append(
                    {"size": float(exch_holdings), "buy_price": float(last_px), "target_sell_level": int(idx)}
                )
                # Seed inventory tracker exposure too
                gm.inventory_tracker.update(long_size=float(exch_holdings), grid_level="seed")
                self.logger.log_warning(
                    f"[BOOTSTRAP] Detected existing holdings={exch_holdings:.8f}. "
                    f"Seeded ledger at price={last_px:.2f} (unrealized_pnl starts at 0)."
                )
        except Exception as e:
            self.logger.log_warning(f"[BOOTSTRAP] Failed to seed holdings into ledger: {e}")

        # Place initial grid orders
        self._sync_exchange_orders(current_price=None)

    def _compute_factors(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Compute the same factor columns as simple_lean_runner (rolling window)."""
        data = bars.copy()

        # trend_score / mr_z
        try:
            from analytics.indicators.regime_factors import (
                calculate_ema,
                calculate_ema_slope,
                rolling_zscore,
                trend_score_from_slope,
            )

            ema = calculate_ema(data["close"], period=int(self.config.trend_ema_period))
            slope = calculate_ema_slope(ema, lookback=int(self.config.trend_slope_lookback))
            data["trend_score"] = trend_score_from_slope(
                slope, slope_ref=float(self.config.trend_slope_ref)
            )
            data["mr_z"] = rolling_zscore(data["close"], window=int(self.config.mr_z_lookback))
        except Exception:
            data["trend_score"] = float("nan")
            data["mr_z"] = float("nan")

        # breakout risk / range_pos / vol_score
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

        # funding (spot live: keep shape, treat as 0)
        data["funding_rate"] = 0.0
        data["minutes_to_funding"] = float("nan")
        return data

    def _get_total_cost_basis_from_ledger(self) -> float:
        total_cost = 0.0
        for positions in self.algorithm.grid_manager.buy_positions.values():
            for pos in positions:
                try:
                    sz = float(pos.get("size", 0.0))
                    px = float(pos.get("buy_price", 0.0))
                except Exception:
                    continue
                if sz > 0 and px > 0:
                    total_cost += sz * px
        return float(total_cost)

    def _get_holdings_from_ledger(self) -> float:
        total_sz = 0.0
        for positions in self.algorithm.grid_manager.buy_positions.values():
            for pos in positions:
                try:
                    sz = float(pos.get("size", 0.0))
                except Exception:
                    continue
                if sz > 0:
                    total_sz += sz
        return float(total_sz)

    def _get_portfolio_state(self, current_price: float) -> Dict[str, Any]:
        """
        Get current portfolio state.

        Returns
        -------
        dict
            Portfolio state with equity, cash, holdings, etc.
        """
        try:
            balance = self.execution_engine.get_account_balance()
            positions = self.execution_engine.get_positions(self.symbol)

            # Calculate total equity
            available_balance = float(balance.get("available_balance", 0.0) or 0.0)
            frozen_balance = float(balance.get("frozen_balance", 0.0) or 0.0)

            # Exchange holdings for the symbol (spot base asset)
            exch_holdings = 0.0
            for pos in positions:
                if pos.get("symbol") == self.symbol or pos.get("currency") == self.symbol.replace("USDT", ""):
                    exch_holdings = float(pos.get("quantity", 0.0) or 0.0)
                    break

            # Strategy ledger holdings/cost-basis (backtest-consistent for unrealized_pnl)
            ledger_holdings = self._get_holdings_from_ledger()
            total_cost_basis = self._get_total_cost_basis_from_ledger()

            # Spot equity approximation in USDT uses exchange holdings (real account value)
            total_equity = (available_balance + frozen_balance) + float(exch_holdings) * float(current_price)

            # Unrealized PnL uses ledger (same as backtest runner)
            unrealized_pnl = float(ledger_holdings) * float(current_price) - float(total_cost_basis)

            drift = float(exch_holdings) - float(ledger_holdings)
            if abs(drift) > 1e-6:
                self.logger.log_warning(
                    f"[LEDGER_DRIFT] exchange_holdings={exch_holdings:.8f} vs ledger_holdings={ledger_holdings:.8f} "
                    f"(drift={drift:+.8f}). If you traded manually or restarted bot, consider re-bootstrap."
                )

            return {
                "equity": total_equity,
                "cash": available_balance,
                "holdings": ledger_holdings,
                "long_holdings": ledger_holdings,
                "short_holdings": 0.0,
                "unrealized_pnl": unrealized_pnl,
                "daily_pnl": 0.0,  # Will be updated by algorithm
            }

        except Exception as e:
            self.logger.log_error(f"Error getting portfolio state: {e}", exc_info=True)
            # Return default state
            return {
                "equity": self.config.initial_cash,
                "cash": self.config.initial_cash,
                "holdings": 0.0,
                "long_holdings": 0.0,
                "short_holdings": 0.0,
                "unrealized_pnl": 0.0,
                "daily_pnl": 0.0,
            }

    def _process_filled_orders(self):
        """Process filled orders and update strategy state."""
        try:
            # Get current open orders from exchange
            open_orders = self.execution_engine.get_open_orders(self.symbol)
            open_order_ids = {str(order.get("order_id", "")) for order in open_orders}

            # Check pending orders
            filled_orders = []
            for order_id, order_info in list(self.pending_orders.items()):
                if order_id not in open_order_ids:
                    # Order is no longer open - check if it's filled
                    order_status = self.execution_engine.get_order_status(
                        self.symbol, order_id
                    )

                    if order_status:
                        status = order_status.get("status", "").lower()
                        if status in ["filled", "partially_filled"]:
                            filled_quantity = float(order_status.get("filled_quantity", 0.0) or 0.0)
                            prev_processed = float(order_info.get("_processed_filled_qty", 0.0) or 0.0)
                            delta_qty = max(0.0, filled_quantity - prev_processed)
                            if delta_qty > 0:
                                avg_px = float(order_status.get("average_price", 0.0) or 0.0)
                                px = avg_px if avg_px > 0 else float(order_status.get("price", 0.0) or 0.0)
                                filled_order = {
                                    "direction": order_info.get("side", "").lower(),
                                    "price": px,
                                    "quantity": delta_qty,
                                    "level": int(order_info.get("level", -1)),
                                    "timestamp": datetime.now(timezone.utc),
                                    "leg": order_info.get("leg"),
                                }
                                filled_orders.append(filled_order)

                                # Update per-bar execution counters (for cooldown detection)
                                self._fills_this_bar += 1
                                if filled_order["direction"] == "buy" and filled_order.get("leg") is None:
                                    self._buy_fills_this_bar += 1
                                    self._buy_notional_added_this_bar += float(delta_qty) * float(px)

                                # Backtest-consistent realized PnL / position matching
                                if filled_order["direction"] == "sell" and filled_order.get("leg") is None:
                                    match = self.algorithm.grid_manager.match_sell_order(
                                        sell_level_index=int(filled_order["level"]),
                                        sell_size=float(filled_order["quantity"]),
                                    )
                                    if match is not None:
                                        _, buy_price, msz = match
                                        pnl = (float(filled_order["price"]) - float(buy_price)) * float(msz)
                                        self.algorithm.grid_manager.update_realized_pnl(float(pnl))

                                # Update strategy
                                self.algorithm.on_order_filled(filled_order)

                                self.logger.log_order(
                                    order_id=order_id,
                                    status="filled",
                                    price=filled_order["price"],
                                    quantity=filled_order["quantity"],
                                )

                                # Update processed qty; remove when fully filled
                                order_info["_processed_filled_qty"] = float(prev_processed + delta_qty)
                                remaining = float(order_status.get("remaining_quantity", 0.0) or 0.0)
                                if status == "filled" or remaining <= 0.0:
                                    del self.pending_orders[order_id]

            return filled_orders

        except Exception as e:
            self.logger.log_error(f"Error processing filled orders: {e}", exc_info=True)
            return []

    def _order_key(self, direction: str, level_index: int, leg: Optional[str]) -> str:
        leg_tag = leg if leg is not None else "long"
        return f"{direction}:{int(level_index)}:{leg_tag}"

    def _make_client_oid(self, direction: str, level_index: int, leg: Optional[str]) -> str:
        leg_tag = leg if leg is not None else "long"
        return f"{self._client_oid_prefix}{direction}_{int(level_index)}_{leg_tag}"

    def _sync_exchange_orders(self, current_price: Optional[float]) -> None:
        """
        Sync algorithm.pending_limit_orders -> exchange open orders.

        For backtest-consistency:
        - Grid limit orders must be resting on the exchange.
        - Sizes are recomputed each bar using the same sizing function (factors + equity).
        - Orders are only eligible if they won't immediately cross the market:
          BUY only if level_price <= current_price; SELL only if level_price >= current_price.
        """
        if self.dry_run:
            return

        # If grid disabled, cancel all bot orders.
        if not bool(self.algorithm.grid_manager.grid_enabled):
            self.execution_engine.cancel_all_orders(self.symbol, client_oid_prefix=self._client_oid_prefix)
            return

        cp = float(current_price) if current_price is not None else None

        # Apply active_buy_levels filter (matches backtest execution knobs)
        pending = list(self.algorithm.grid_manager.pending_limit_orders)
        cp = float(current_price) if current_price is not None else None
        if cp is not None and self.active_buy_levels is not None and self.active_buy_levels > 0:
            keep_n = int(self.active_buy_levels)
            if self._in_cooldown(datetime.now(timezone.utc)) and self.cooldown_active_buy_levels > 0:
                keep_n = int(self.cooldown_active_buy_levels)

            # Eligible BUY orders: price <= current_price (resting buy)
            buys = [o for o in pending if str(o.get("direction")) == "buy" and bool(o.get("placed", False))]
            eligible = [o for o in buys if float(o.get("price", 0.0)) <= float(cp)]
            if len(eligible) > keep_n:
                eligible_sorted = sorted(eligible, key=lambda o: abs(float(cp) - float(o.get("price", 0.0))))
                keep_keys = {(int(o.get("level_index")), o.get("leg")) for o in eligible_sorted[:keep_n]}
                # Remove extra eligible buys from desired set by marking placed=False
                for o in pending:
                    if str(o.get("direction")) == "buy" and bool(o.get("placed", False)):
                        k = (int(o.get("level_index")), o.get("leg"))
                        if float(o.get("price", 0.0)) <= float(cp) and k not in keep_keys:
                            o["placed"] = False

        desired: Dict[str, dict] = {}
        for o in pending:
            if not bool(o.get("placed", False)):
                continue
            direction = str(o.get("direction"))
            level_index = int(o.get("level_index"))
            price = float(o.get("price"))
            leg = o.get("leg")

            # Eligibility to avoid immediate taker fills
            if cp is not None:
                if direction == "buy" and price > cp:
                    continue
                if direction == "sell" and price < cp:
                    continue

            desired[self._order_key(direction, level_index, leg)] = o

        open_orders = self.execution_engine.get_open_orders(self.symbol)
        open_by_client: Dict[str, dict] = {}
        for oo in open_orders:
            coid = str(oo.get("client_order_id") or "")
            if coid.startswith(self._client_oid_prefix):
                open_by_client[coid] = oo

        # Cancel extra bot orders not in desired set
        for coid, oo in list(open_by_client.items()):
            suffix = coid[len(self._client_oid_prefix):]
            parts = suffix.split("_")
            if len(parts) < 3:
                continue
            direction = parts[0]
            level_index = int(parts[1])
            leg_tag = "_".join(parts[2:])
            leg = None if leg_tag == "long" else leg_tag
            k = self._order_key(direction, level_index, leg)
            if k not in desired:
                oid = str(oo.get("order_id") or "")
                if oid:
                    self.execution_engine.cancel_order(self.symbol, oid)

        # Place / replace desired orders
        # Recompute size using latest factor snapshot + equity snapshot
        ps = self._get_portfolio_state(current_price=float(cp) if cp is not None else (float(list(desired.values())[0]["price"]) if desired else 1.0))
        for k, o in desired.items():
            direction = str(o.get("direction"))
            level_index = int(o.get("level_index"))
            price = float(o.get("price"))
            leg = o.get("leg")
            client_oid = self._make_client_oid(direction, level_index, leg)

            # Use latest factors (computed in run loop) to match backtest sizing semantics.
            fs = self._last_factor_state or {}
            mr_z = fs.get("mr_z")
            trend_score = fs.get("trend_score")
            br_down = fs.get("breakout_risk_down")
            br_up = fs.get("breakout_risk_up")
            rp = fs.get("range_pos")
            fr = fs.get("funding_rate")
            mtf = fs.get("minutes_to_funding")
            vs = fs.get("vol_score")

            size, throttle = self.algorithm.grid_manager.calculate_order_size(
                direction=direction,
                level_index=level_index,
                level_price=price,
                equity=float(ps.get("equity", self.config.initial_cash)),
                daily_pnl=float(ps.get("daily_pnl", 0.0)),
                risk_budget=float(self.algorithm.risk_budget),
                holdings_btc=float(ps.get("holdings", 0.0)),
                order_leg=leg,
                current_price=float(cp) if cp is not None else price,
                mr_z=mr_z,
                trend_score=trend_score,
                breakout_risk_down=br_down,
                breakout_risk_up=br_up,
                range_pos=rp,
                funding_rate=fr,
                minutes_to_funding=mtf,
                vol_score=vs,
            )

            qty = float(size)
            if qty <= 0.0:
                # If blocked, ensure any existing order is cancelled
                if client_oid in open_by_client:
                    oid = str(open_by_client[client_oid].get("order_id") or "")
                    if oid:
                        self.execution_engine.cancel_order(self.symbol, oid)
                continue

            # If already open, replace only when quantity differs materially
            if client_oid in open_by_client:
                oo = open_by_client[client_oid]
                open_qty = float(oo.get("quantity", 0.0) or 0.0)
                if open_qty > 0 and abs(open_qty - qty) / open_qty < 0.05:
                    continue
                oid = str(oo.get("order_id") or "")
                if oid:
                    self.execution_engine.cancel_order(self.symbol, oid)

            r = self.execution_engine.place_order(
                symbol=self.symbol,
                side=direction,
                quantity=qty,
                price=price,
                order_type="limit",
                client_order_id=client_oid,
            )
            if r and r.get("order_id"):
                oid = str(r["order_id"])
                self.pending_orders[oid] = {
                    "side": direction,
                    "price": price,
                    "quantity": qty,
                    "level": level_index,
                    "leg": leg,
                    "_processed_filled_qty": 0.0,
                    "client_order_id": client_oid,
                    "reason": getattr(throttle, "reason", None),
                }

    def run(self):
        """Main execution loop."""
        self.logger.log_info("=" * 80)
        self.logger.log_info("Starting Live Trading Runner")
        self.logger.log_info(f"Symbol: {self.symbol}")
        self.logger.log_info(f"Dry Run: {self.dry_run}")
        if self.subaccount_uid:
            self.logger.log_info(f"Subaccount UID: {self.subaccount_uid}")
        self.logger.log_info("=" * 80)

        try:
            while True:
                try:
                    # Get latest bar (use 1m to match grid calculation timeframe)
                    latest_bar = self.data_source.get_latest_bar(self.symbol, "1m")

                    if latest_bar is None:
                        self.logger.log_warning("Failed to get latest bar, retrying...")
                        time.sleep(5)
                        continue

                    bar_timestamp = latest_bar["timestamp"]

                    # Skip if we've already processed this bar
                    if self.last_bar_timestamp is not None:
                        if bar_timestamp <= self.last_bar_timestamp:
                            # Wait for new bar
                            time.sleep(10)
                            continue

                    self.last_bar_timestamp = bar_timestamp
                    self._bar_index += 1
                    self.algorithm._current_bar_index = self._bar_index
                    # Reset execution counters for this bar
                    self._fills_this_bar = 0
                    self._buy_fills_this_bar = 0
                    self._buy_notional_added_this_bar = 0.0

                    # Update rolling bars window for factor computation
                    row = {
                        "open": float(latest_bar["open"]),
                        "high": float(latest_bar["high"]),
                        "low": float(latest_bar["low"]),
                        "close": float(latest_bar["close"]),
                        "volume": float(latest_bar["volume"]),
                    }
                    one = pd.DataFrame(
                        [row],
                        index=pd.DatetimeIndex([pd.Timestamp(bar_timestamp)]),
                    )
                    if self._recent_bars is None:
                        self._recent_bars = one
                    else:
                        self._recent_bars = pd.concat([self._recent_bars, one], axis=0)
                        self._recent_bars = self._recent_bars[~self._recent_bars.index.duplicated(keep="last")]
                        self._recent_bars = self._recent_bars.sort_index().tail(self._recent_bars_maxlen)

                    factors = self._compute_factors(self._recent_bars)
                    last = factors.iloc[-1]
                    self._last_factor_state = {
                        "trend_score": float(last.get("trend_score")) if "trend_score" in last else float("nan"),
                        "mr_z": float(last.get("mr_z")) if "mr_z" in last else float("nan"),
                        "breakout_risk_down": float(last.get("breakout_risk_down", 0.0)),
                        "breakout_risk_up": float(last.get("breakout_risk_up", 0.0)),
                        "range_pos": float(last.get("range_pos", 0.5)),
                        "vol_score": float(last.get("vol_score", 0.0)),
                        "funding_rate": float(last.get("funding_rate", 0.0)),
                        "minutes_to_funding": last.get("minutes_to_funding"),
                    }

                    # Get portfolio state
                    portfolio_state = self._get_portfolio_state(current_price=float(latest_bar["close"]))

                    # Log portfolio state periodically
                    self.logger.log_portfolio(
                        equity=portfolio_state["equity"],
                        cash=portfolio_state["cash"],
                        holdings=portfolio_state["holdings"],
                        unrealized_pnl=portfolio_state["unrealized_pnl"],
                    )

                    # Process filled orders first
                    self._process_filled_orders()

                    # Possibly enter cooldown based on abnormal-minute heuristics
                    self._maybe_enter_cooldown(
                        bar_ts=bar_timestamp,
                        bar_high=float(latest_bar["high"]),
                        bar_low=float(latest_bar["low"]),
                        equity=float(portfolio_state.get("equity", self.config.initial_cash)),
                        close_px=float(latest_bar["close"]),
                    )

                    # Prepare bar data
                    bar_data = {
                        "open": latest_bar["open"],
                        "high": latest_bar["high"],
                        "low": latest_bar["low"],
                        "close": latest_bar["close"],
                        "volume": latest_bar["volume"],
                        "trend_score": self._last_factor_state.get("trend_score"),
                        "mr_z": self._last_factor_state.get("mr_z"),
                        "breakout_risk_down": self._last_factor_state.get("breakout_risk_down", 0.0),
                        "breakout_risk_up": self._last_factor_state.get("breakout_risk_up", 0.0),
                        "range_pos": self._last_factor_state.get("range_pos", 0.5),
                        "vol_score": self._last_factor_state.get("vol_score", 0.0),
                        "funding_rate": self._last_factor_state.get("funding_rate", 0.0),
                        "minutes_to_funding": self._last_factor_state.get("minutes_to_funding"),
                    }

                    # Call strategy in live_mode:
                    # - grid orders are resting on exchange (no OHLC trigger simulation)
                    # - may emit special market orders (forced deleverage / short stop)
                    order_signal = self.algorithm.on_data(
                        current_time=bar_timestamp,
                        bar_data=bar_data,
                        portfolio_state=portfolio_state,
                        live_mode=True,
                    )

                    # If grid disabled, cancel all bot orders and skip placing
                    if not bool(self.algorithm.grid_manager.grid_enabled):
                        if not self.dry_run:
                            self.execution_engine.cancel_all_orders(
                                symbol=self.symbol, client_oid_prefix=self._client_oid_prefix
                            )
                        time.sleep(5)
                        continue

                    # Execute special order if emitted (market/limit)
                    if order_signal and not self.dry_run:
                        side = str(order_signal["direction"]).lower()
                        qty = float(order_signal["quantity"])
                        px = order_signal.get("price", None)
                        level = int(order_signal.get("level", -1))
                        leg = order_signal.get("leg")

                        if px is None:
                            order_result = self.execution_engine.place_order(
                                symbol=self.symbol,
                                side=side,
                                quantity=qty,
                                price=None,
                                order_type="market",
                                client_order_id=f"{self._client_oid_prefix}mkt_{int(time.time())}",
                            )
                        else:
                            order_result = self.execution_engine.place_order(
                                symbol=self.symbol,
                                side=side,
                                quantity=qty,
                                price=float(px),
                                order_type="limit",
                                client_order_id=f"{self._client_oid_prefix}sig_{side}_{level}_{leg or 'long'}_{int(time.time())}",
                            )

                        if order_result:
                            order_id = order_result.get("order_id")
                            if order_id:
                                # Store pending order
                                self.pending_orders[order_id] = {
                                    "side": order_signal["direction"],
                                    "price": order_signal["price"],
                                    "quantity": order_signal["quantity"],
                                    "level": order_signal.get("level", -1),
                                    "leg": order_signal.get("leg"),
                                    "_processed_filled_qty": 0.0,
                                }

                                self.logger.log_signal(
                                    signal_type=order_signal["direction"],
                                    price=order_signal["price"],
                                    quantity=order_signal["quantity"],
                                    level=order_signal.get("level"),
                                    reason=order_signal.get("reason"),
                                )

                                self.logger.log_order(
                                    order_id=order_id,
                                    status="placed",
                                    price=order_signal["price"],
                                    quantity=order_signal["quantity"],
                                )
                        else:
                            self.logger.log_warning(
                                f"Failed to place order: {order_signal}"
                            )

                    elif order_signal and self.dry_run:
                        # Log signal in dry run mode
                        self.logger.log_signal(
                            signal_type=order_signal["direction"],
                            price=order_signal["price"],
                            quantity=order_signal["quantity"],
                            level=order_signal.get("level"),
                            reason="DRY RUN - Order not placed",
                        )

                    # Sync grid orders to exchange (place missing, cancel extra, re-size)
                    self._sync_exchange_orders(current_price=float(latest_bar["close"]))

                    # Wait for next minute
                    # Calculate sleep time to align with minute boundary
                    now = datetime.now(timezone.utc)
                    next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
                    sleep_seconds = (next_minute - now).total_seconds()
                    if sleep_seconds > 0:
                        time.sleep(min(sleep_seconds, 60))

                except KeyboardInterrupt:
                    self.logger.log_info("Received interrupt signal, stopping...")
                    break
                except Exception as e:
                    self.logger.log_error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(10)  # Wait before retrying

        except Exception as e:
            self.logger.log_error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            self.logger.log_info("=" * 80)
            self.logger.log_info("Live Trading Runner Stopped")
            self.logger.log_info("=" * 80)
