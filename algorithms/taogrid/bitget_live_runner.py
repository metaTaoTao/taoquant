"""
Bitget Live Trading Runner.

This module provides real-time execution of TaoGrid strategy on Bitget exchange.
"""

from __future__ import annotations

import sys
import time
import json
import math
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import pandas as pd

# Optional DB persistence (best-effort; never required for trading loop)
try:
    from persistence.db import PostgresStore
except Exception:  # pragma: no cover
    PostgresStore = None  # type: ignore[assignment]

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
        # --- Live Status Output ---
        enable_live_status: bool = False,
        live_status_file: Optional[Path] = None,
        live_status_update_frequency: int = 1,
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
        self.market_type: str = str(self.execution_model.get("market_type", "spot") or "spot").lower()
        # Dry-run fill simulation: if True, we will simulate fills using bar OHLC touch rule
        # and update an internal paper portfolio (backtest-consistent). This helps validate
        # "price crossed my limit" scenarios in dry-run.
        self.simulate_fills_in_dry_run: bool = bool(self.execution_model.get("simulate_fills_in_dry_run", False))

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

        # ====================================================================
        # Execution safety fuses (infra hard-gates)
        # ====================================================================
        self.safety_max_orders_per_min = max(0, int(self.execution_model.get("safety_max_orders_per_min", 30)))
        self.safety_max_cancels_per_min = max(0, int(self.execution_model.get("safety_max_cancels_per_min", 60)))
        self.safety_max_notional_add_frac_equity_per_min = float(
            self.execution_model.get("safety_max_notional_add_frac_equity_per_min", 0.30)
        )
        self.safety_data_stale_seconds = max(0, int(self.execution_model.get("safety_data_stale_seconds", 90)))
        self.safety_exchange_degrade_errors = max(0, int(self.execution_model.get("safety_exchange_degrade_errors", 3)))

        ks = str(self.execution_model.get("safety_kill_switch_file", "state/kill_switch") or "state/kill_switch")
        p = Path(ks)
        if not p.is_absolute():
            base = Path(getattr(self.config, "state_dir", "state"))
            p = base / p
        self.safety_kill_switch_file: Path = p

        self._safety_window_start: datetime | None = None
        self._safety_orders_count: int = 0
        self._safety_cancels_count: int = 0
        self._safety_notional_added: float = 0.0

        # Paper portfolio state (used only when dry_run + simulate_fills_in_dry_run)
        self._paper_cash: float = float(getattr(self.config, "initial_cash", 0.0))
        self._paper_long_holdings: float = 0.0
        self._paper_short_holdings: float = 0.0
        self._paper_total_cost_basis: float = 0.0
        self._paper_total_short_entry_value: float = 0.0
        # Estimated commissions (dry-run only; in live we would need exchange fills/fees)
        self._paper_commission_paid: float = 0.0
        # In-memory blotter (for periodic reporting / dashboard integration)
        self._blotter_events: list[dict] = []
        self._blotter_maxlen: int = 200
        # Grid snapshot signature (to log when it changes)
        self._grid_signature: str | None = None

        # Initialize logger
        self.logger = LiveLogger(log_dir=log_dir, name=f"bitget_live_{symbol}")

        # Initialize data source
        self.data_source = BitgetSDKDataSource(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            debug=True,
            market_type=self.market_type,
        )

        # Initialize execution engine
        self.execution_engine = BitgetExecutionEngine(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            subaccount_uid=subaccount_uid,
            debug=True,
            market_type=self.market_type,
        )

        # Initialize algorithm
        self.algorithm = TaoGridLeanAlgorithm(config)

        # Track last processed bar timestamp
        self.last_bar_timestamp: Optional[datetime] = None

        # Track pending orders (order_id -> order_info)
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        # Live bar index (monotonic) used by algorithm time-based guards
        self._bar_index: int = 0
        # Client order id prefix with startup timestamp to ensure uniqueness across restarts
        # Bitget rejects duplicate clientOid even if previous order failed/cancelled
        self._startup_ts: int = int(time.time())
        self._client_oid_prefix: str = f"tg_{self.symbol}_{self._startup_ts}_"
        # Version counter for each order key to ensure unique clientOid on re-placement
        self._order_version: Dict[str, int] = {}
        # Rolling bars window for factor computation
        self._recent_bars: Optional[pd.DataFrame] = None
        self._recent_bars_maxlen: int = 3000
        self._last_factor_state: Dict[str, Any] = {}

        # --- Live Status Output ---
        self.enable_live_status = bool(enable_live_status)
        self.live_status_file = live_status_file
        self.live_status_update_frequency = max(1, int(live_status_update_frequency))
        self._live_status_update_counter = 0
        self._start_time = datetime.now(timezone.utc)  # Track start time for uptime
        # Market bars stream (JSONL) for dashboard-side market service
        base = Path(getattr(self.config, "state_dir", "state"))
        self._market_bars_file: Path = base / "market_bars_1m.jsonl"
        self._last_market_bar_ts: datetime | None = None
        # DB outbox (when DB is down, buffer payloads here for replay)
        self._db_outbox_file: Path = base / "db_outbox.jsonl"
        # Latest planned grid limit orders (computed in _sync_exchange_orders each bar)
        self._last_planned_limit_orders: list[dict] = []
        self._last_planned_limit_orders_ts: datetime | None = None

        # DB persistence store (optional)
        self._db_store = None
        try:
            if PostgresStore is not None:
                self._db_store = PostgresStore.from_env()
        except Exception:
            self._db_store = None
        # Lightweight health counters for dashboard diagnostics
        self._consecutive_loop_errors: int = 0
        self._last_loop_error_ts: datetime | None = None

        # Session management (v2 schema)
        self._session_id: str = f"sess_{self._startup_ts}"
        self._bootstrap_orders_cancelled: int = 0
        self._bootstrap_orders_placed: int = 0
        self._bootstrap_position_qty: float | None = None

        # Initialize strategy
        self._initialize_strategy()
        # Bootstrap exchange grid: ensure resting limit orders exist (backtest-consistent)
        self._bootstrap_exchange_grid()

        # Create session record in DB after bootstrap
        self._create_db_session()

    def _grid_sig(self) -> str:
        gm = self.algorithm.grid_manager
        bl = gm.buy_levels
        sl = gm.sell_levels
        def _head_tail(arr):
            if arr is None or len(arr) == 0:
                return ("NA", "NA")
            return (f"{float(arr[0]):.2f}", f"{float(arr[-1]):.2f}")
        b0, bN = _head_tail(bl)
        s0, sN = _head_tail(sl)
        nb = len(bl) if bl is not None else 0
        ns = len(sl) if sl is not None else 0
        return f"regime={getattr(self.config,'regime',None)} support={float(self.config.support):.2f} resistance={float(self.config.resistance):.2f} nb={nb} ns={ns} b=({b0},{bN}) s=({s0},{sN})"

    def _log_grid_snapshot(self, reason: str) -> None:
        gm = self.algorithm.grid_manager
        bl = gm.buy_levels
        sl = gm.sell_levels
        spacing = self._estimate_spacing_pct()

        def _sample(arr):
            if arr is None or len(arr) == 0:
                return []
            vals = [float(arr[i]) for i in range(min(3, len(arr)))]
            if len(arr) > 3:
                vals += [float(arr[-i]) for i in range(min(3, len(arr)), 0, -1)]
            # unique while preserving order
            out = []
            for v in vals:
                if v not in out:
                    out.append(v)
            return out

        self.logger.log_info(
            f"[GRID] {reason} market_type={self.market_type} support={float(self.config.support):.0f} "
            f"resistance={float(self.config.resistance):.0f} regime={getattr(self.config,'regime','')} "
            f"buy_levels={len(bl) if bl is not None else 0} sell_levels={len(sl) if sl is not None else 0} "
            f"spacing_est={spacing:.4%}"
        )
        if bl is not None and len(bl) > 0:
            self.logger.log_info("  buy_levels_sample=" + ", ".join([f"{x:.2f}" for x in _sample(bl)]))
        if sl is not None and len(sl) > 0:
            self.logger.log_info("  sell_levels_sample=" + ", ".join([f"{x:.2f}" for x in _sample(sl)]))

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
            # Always print grid snapshot once after init (even when enable_console_log is False)
            sig = self._grid_sig()
            self._grid_signature = sig
            self._log_grid_snapshot("initialized")

        except Exception as e:
            self.logger.log_error(f"Failed to initialize strategy: {e}", exc_info=True)
            raise

    def _write_status_snapshot(
        self,
        *,
        bar_timestamp: datetime,
        latest_bar: dict,
        portfolio_state: Dict[str, Any],
    ) -> None:
        """
        Write a compact status snapshot for dashboard/monitoring.

        This is intentionally file-based (no extra infra). The dashboard can read
        `state/live_status.json` to show PnL/risk/grid state.
        """
        try:
            base = Path(getattr(self.config, "state_dir", "state"))
            base.mkdir(parents=True, exist_ok=True)
            status_path = base / "live_status.json"

            gm = self.algorithm.grid_manager

            realized = float(getattr(gm, "realized_pnl", 0.0) or 0.0)
            risk_level = int(getattr(gm, "risk_level", 0) or 0)
            grid_enabled = bool(getattr(gm, "grid_enabled", True))
            shutdown_reason = getattr(gm, "grid_shutdown_reason", None)

            # Buy/sell ranges are helpful when troubleshooting "grid is far away".
            buy_min = float(gm.buy_levels.min()) if getattr(gm, "buy_levels", None) is not None and len(gm.buy_levels) > 0 else None
            buy_max = float(gm.buy_levels.max()) if getattr(gm, "buy_levels", None) is not None and len(gm.buy_levels) > 0 else None
            sell_min = float(gm.sell_levels.min()) if getattr(gm, "sell_levels", None) is not None and len(gm.sell_levels) > 0 else None
            sell_max = float(gm.sell_levels.max()) if getattr(gm, "sell_levels", None) is not None and len(gm.sell_levels) > 0 else None

            doc = {
                "ts": pd.Timestamp(bar_timestamp).tz_convert("UTC").isoformat(),
                "mode": "dry_run" if bool(self.dry_run) else "live",
                "symbol": str(self.symbol),
                "market_type": str(self.market_type),
                "market": {
                    "open": float(latest_bar.get("open", 0.0) or 0.0),
                    "high": float(latest_bar.get("high", 0.0) or 0.0),
                    "low": float(latest_bar.get("low", 0.0) or 0.0),
                    "close": float(latest_bar.get("close", 0.0) or 0.0),
                    "volume": float(latest_bar.get("volume", 0.0) or 0.0),
                },
                "portfolio": {
                    "equity": float(portfolio_state.get("equity", 0.0) or 0.0),
                    "cash": float(portfolio_state.get("cash", 0.0) or 0.0),
                    "holdings": float(portfolio_state.get("holdings", 0.0) or 0.0),
                    "long_holdings": float(portfolio_state.get("long_holdings", 0.0) or 0.0),
                    "short_holdings": float(portfolio_state.get("short_holdings", 0.0) or 0.0),
                    "unrealized_pnl": float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0),
                    "realized_pnl": realized,
                },
                "risk": {
                    "risk_level": risk_level,
                    "grid_enabled": grid_enabled,
                    "shutdown_reason": shutdown_reason,
                    "in_cooldown": bool(self._in_cooldown(bar_timestamp)),
                },
                "grid": {
                    "support": float(getattr(self.config, "support", 0.0) or 0.0),
                    "resistance": float(getattr(self.config, "resistance", 0.0) or 0.0),
                    "atr": float(getattr(gm, "current_atr", 0.0) or 0.0),
                    "buy_levels": int(len(getattr(gm, "buy_levels", []) or [])),
                    "sell_levels": int(len(getattr(gm, "sell_levels", []) or [])),
                    "buy_range": [buy_min, buy_max],
                    "sell_range": [sell_min, sell_max],
                    "active_buy_levels": self.active_buy_levels,
                },
                "factors": dict(self._last_factor_state or {}),
            }

            # atomic write
            tmp = status_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(status_path)
        except Exception:
            # Do not crash trading loop because dashboard snapshot failed
            return

    def _bootstrap_exchange_grid(self) -> None:
        """
        Ensure exchange open orders reflect the algorithm's pending grid orders.

        Backtest assumption: grid limit orders are already resting and get filled by price.
        Live must therefore place those limit orders on the exchange and react on fills.
        """
        if self.dry_run:
            self.logger.log_info("[DRY_RUN] Skip bootstrap order placement.")
            return

        # Short overlay requires contracts.
        if bool(getattr(self.config, "enable_short_in_bearish", False)) and self.market_type == "spot":
            self.logger.log_warning(
                "enable_short_in_bearish=True but market_type=spot. "
                "Short overlay requires swap/futures; disabling short for live."
            )
            self.config.enable_short_in_bearish = False

        # Best-effort: set leverage on swap
        try:
            if self.market_type in ("swap", "future", "futures"):
                _ = self.execution_engine.set_leverage(self.symbol, float(getattr(self.config, "leverage", 1.0)))
        except Exception:
            pass

        # Cancel all existing bot orders (with convergence loop to handle race conditions).
        # Use a generic prefix pattern to match orders from ANY previous startup session
        # (since each startup has unique timestamp in prefix: tg_BTCUSDT_<ts>_)
        bot_prefix_pattern = f"tg_{self.symbol}_"  # Matches all TaoGrid orders for this symbol
        try:
            cancelled = self.execution_engine.cancel_all_orders(
                symbol=self.symbol,
                client_oid_prefix=bot_prefix_pattern,
            )
            total_cancelled = int(cancelled or 0)

            # Converge: cancel -> refetch -> retry (handles "filled while cancelling" / residuals).
            max_rounds = 5
            remaining = []
            for _ in range(max_rounds):
                open_orders = self.execution_engine.get_open_orders(self.symbol) or []
                bot_orders = [
                    oo for oo in open_orders
                    if str(oo.get("client_order_id") or "").startswith(bot_prefix_pattern)
                ]
                remaining = bot_orders
                if not bot_orders:
                    break
                for oo in bot_orders:
                    oid = str(oo.get("order_id") or "")
                    if not oid:
                        continue
                    try:
                        self.execution_engine.cancel_order(self.symbol, oid)
                        total_cancelled += 1
                    except Exception:
                        continue
                time.sleep(1)

            if total_cancelled > 0:
                self.logger.log_info(
                    f"Cancelled {total_cancelled} previous TaoGrid orders (pattern={bot_prefix_pattern})"
                )
                # Track for session stats
                self._bootstrap_orders_cancelled = total_cancelled
            if remaining:
                self.logger.log_warning(
                    f"[BOOTSTRAP] Residual bot open orders remain after retries: {len(remaining)} "
                    f"(pattern={bot_prefix_pattern}). Will continue and rely on sync loop."
                )
        except Exception:
            pass

        # Seed internal ledger from current exchange holdings (restart-safe baseline).
        last_px: float = float(getattr(self.config, "support", 0.0) or 0.0) or 1.0
        try:
            latest = self.data_source.get_latest_bar(self.symbol, "1m")
            last_px = float(latest["close"]) if latest else last_px
            positions = self.execution_engine.get_positions(self.symbol)
            # Best-effort: persist positions snapshot immediately
            try:
                if self._db_store is not None:
                    self._db_store.upsert_exchange_positions_current(
                        bot_id=self._bot_id(),
                        ts=datetime.now(timezone.utc),
                        rows=positions or [],
                    )
            except Exception:
                pass
            exch_long = 0.0
            exch_short = 0.0
            for pos in positions:
                sym = str(pos.get("symbol") or "")
                if self.symbol not in sym and self.symbol.replace("USDT", "") not in sym:
                    continue
                side = str(pos.get("side") or "spot").lower()
                qty = float(pos.get("quantity", 0.0) or 0.0)
                if self.market_type == "spot":
                    exch_long = qty
                else:
                    if side == "long":
                        exch_long += qty
                    elif side == "short":
                        exch_short += qty

            if exch_long > float(getattr(self.config, "short_flat_holdings_btc", 0.0005)):
                # Put the whole inventory into ledger at mark-to-market cost (conservative, avoids fake unrealized pnl).
                gm = self.algorithm.grid_manager
                if gm.buy_levels is not None and len(gm.buy_levels) > 0:
                    # choose nearest buy level index for pairing
                    diffs = [abs(float(p) - last_px) for p in gm.buy_levels]
                    idx = int(diffs.index(min(diffs)))
                else:
                    idx = 0
                gm.buy_positions.setdefault(idx, []).append(
                    {"size": float(exch_long), "buy_price": float(last_px), "target_sell_level": int(idx)}
                )
                # Seed inventory tracker exposure too
                gm.inventory_tracker.update(long_size=float(exch_long), grid_level="seed_long")
                self.logger.log_warning(
                    f"[BOOTSTRAP] Detected existing long={exch_long:.8f}. "
                    f"Seeded ledger at price={last_px:.2f} (unrealized_pnl starts at 0)."
                )
                # Track for session stats
                self._bootstrap_position_qty = float(exch_long)

            if self.market_type != "spot" and exch_short > float(getattr(self.config, "short_flat_holdings_btc", 0.0005)):
                # Seed short ledger similarly at mark-to-market.
                gm = self.algorithm.grid_manager
                if gm.sell_levels is not None and len(gm.sell_levels) > 0:
                    diffs = [abs(float(p) - last_px) for p in gm.sell_levels]
                    sidx = int(diffs.index(min(diffs)))
                else:
                    sidx = 0
                gm.short_positions.setdefault(sidx, []).append(
                    {"size": float(exch_short), "sell_price": float(last_px), "target_buy_level": int(max(0, sidx - 1))}
                )
                gm.inventory_tracker.update(short_size=float(exch_short), grid_level="seed_short")
                self.logger.log_warning(
                    f"[BOOTSTRAP] Detected existing short={exch_short:.8f}. "
                    f"Seeded short ledger at price={last_px:.2f} (unrealized_pnl starts at 0)."
                )
        except Exception as e:
            self.logger.log_warning(f"[BOOTSTRAP] Failed to seed holdings into ledger: {e}")

        # Best-effort: replay fills since last seen cursor (implemented later)
        try:
            self._replay_fills_best_effort()
        except Exception:
            pass

        # Place initial grid orders
        # IMPORTANT: pass current price so we don't place crossing orders at bootstrap
        # (otherwise BUY above market / SELL below market can execute immediately as taker).
        # Also skip safety limits during bootstrap to ensure initial grid is fully placed.
        
        # Apply active_buy_levels filter BEFORE placing orders (consistent with backtest)
        if self.active_buy_levels is not None and self.active_buy_levels > 0:
            self._apply_active_buy_levels_filter(current_price=float(last_px), keep_levels=int(self.active_buy_levels))
            self.logger.log_info(f"[BOOTSTRAP] Applied active_buy_levels filter: keeping {self.active_buy_levels} buy levels")
        
        self.logger.log_info(f"[BOOTSTRAP] Placing initial grid orders at current_price=${last_px:.2f} (bypassing safety limits)")
        self._sync_exchange_orders(current_price=float(last_px), skip_safety_limits=True)

        # Reconcile positions: sync exchange positions to ledger and place hedge orders
        self._reconcile_positions_on_startup(current_price=float(last_px))

        # Verify orders were placed (best-effort check)
        try:
            open_orders = self.execution_engine.get_open_orders(self.symbol) or []
            bot_open = [oo for oo in open_orders if str(oo.get("client_order_id") or "").startswith(self._client_oid_prefix)]
            self.logger.log_info(f"[BOOTSTRAP] Verification: {len(bot_open)} bot orders currently open on exchange")
            if bot_open:
                for oo in bot_open[:5]:  # Show first 5
                    self.logger.log_info(
                        f"  - {str(oo.get('side', '')).upper()} @ ${float(oo.get('price', 0) or 0):.2f} "
                        f"qty={float(oo.get('quantity', 0) or 0):.6f} "
                        f"client_oid={str(oo.get('client_order_id', ''))}"
                    )
        except Exception as e:
            self.logger.log_warning(f"[BOOTSTRAP] Could not verify open orders: {e}")

    def _reconcile_positions_on_startup(self, current_price: float) -> None:
        """
        Reconcile positions on startup: sync exchange positions to ledger and place hedge orders.

        This handles the case where:
        1. Bot was restarted and lost tracking of filled orders
        2. Positions exist on exchange but not in ledger
        3. Need to place hedge orders for unhedged positions

        Strategy:
        - Get positions from exchange (with entry_price)
        - Calculate position drift vs ledger
        - For untracked positions:
          * Find nearest grid level based on entry_price
          * Update ledger to record the position
          * Place corresponding hedge SELL order (with proper spacing)

        Parameters
        ----------
        current_price : float
            Current market price for validation
        """
        if self.dry_run:
            # In dry-run, positions are simulated, no reconciliation needed
            return

        try:
            # 1. Get positions from exchange
            exchange_positions = self.execution_engine.get_positions(self.symbol)

            # 2. Get ledger positions
            ledger_long = float(self._get_holdings_from_ledger() or 0.0)
            ledger_short = 0.0  # TODO: track short positions if needed

            # 3. Calculate drift
            exchange_long = 0.0
            exchange_short = 0.0
            for pos in exchange_positions:
                side = str(pos.get('side', '')).lower()
                qty = float(pos.get('quantity', 0.0))
                if side == 'long':
                    exchange_long += qty
                elif side == 'short':
                    exchange_short += qty

            drift_long = exchange_long - ledger_long
            drift_short = exchange_short - ledger_short

            # 4. Log drift detection
            if abs(drift_long) > 1e-8 or abs(drift_short) > 1e-8:
                self.logger.log_warning(
                    f"[POSITION_RECOVERY] Detected position drift: "
                    f"exchange_long={exchange_long:.8f} vs ledger_long={ledger_long:.8f} (drift={drift_long:+.8f}), "
                    f"exchange_short={exchange_short:.8f} vs ledger_short={ledger_short:.8f} (drift={drift_short:+.8f})"
                )

                # 5. Reconcile each position
                for pos in exchange_positions:
                    side = str(pos.get('side', '')).lower()
                    qty = float(pos.get('quantity', 0.0))
                    entry_price = pos.get('entry_price')

                    if qty <= 1e-8:
                        continue

                    if entry_price is None or entry_price <= 0:
                        self.logger.log_warning(
                            f"[POSITION_RECOVERY] Position has no entry_price, skipping: "
                            f"side={side} qty={qty:.8f}"
                        )
                        continue

                    entry_price = float(entry_price)

                    # Only handle long positions for now (grid strategy is long-biased)
                    if side == 'long':
                        self._recover_long_position(
                            qty=qty,
                            entry_price=entry_price,
                            current_price=current_price
                        )
            else:
                self.logger.log_info(
                    f"[POSITION_RECOVERY] No drift detected: "
                    f"exchange matches ledger (long={exchange_long:.8f}, short={exchange_short:.8f})"
                )

        except Exception as e:
            self.logger.log_error(f"[POSITION_RECOVERY] Error during reconciliation: {e}", exc_info=True)

    def _recover_long_position(self, qty: float, entry_price: float, current_price: float) -> None:
        """
        Recover a long position: update ledger and place hedge SELL order.

        Parameters
        ----------
        qty : float
            Position quantity (BTC)
        entry_price : float
            Average entry price
        current_price : float
            Current market price
        """
        try:
            # Get grid configuration
            buy_levels = self.algorithm.grid_manager.buy_levels
            sell_levels = self.algorithm.grid_manager.sell_levels

            if buy_levels is None or sell_levels is None or len(buy_levels) == 0:
                self.logger.log_warning(
                    f"[POSITION_RECOVERY] Grid not initialized, cannot recover position"
                )
                return

            # Find nearest buy level to entry_price
            nearest_buy_idx = min(
                range(len(buy_levels)),
                key=lambda i: abs(buy_levels[i] - entry_price)
            )
            nearest_buy_price = buy_levels[nearest_buy_idx]

            # Calculate target sell price (with spacing to ensure profit)
            # Get current spacing from grid manager
            spacing_pct = 0.0016  # Default fallback
            try:
                # Try to get actual spacing from grid calculation
                from analytics.indicators.grid_generator import calculate_grid_spacing
                import pandas as pd
                # Use a simple estimate if ATR not available
                spacing_pct = float(self.config.min_return) + 2 * float(self.config.maker_fee)
            except Exception:
                pass

            sell_price_target = entry_price * (1.0 + spacing_pct)

            # Find nearest sell level to target
            if nearest_buy_idx < len(sell_levels):
                # Use corresponding sell level (buy[i] -> sell[i])
                sell_idx = nearest_buy_idx
                sell_price = sell_levels[sell_idx]
            else:
                # Fallback: find any nearest sell level
                sell_idx = min(
                    range(len(sell_levels)),
                    key=lambda i: abs(sell_levels[i] - sell_price_target)
                )
                sell_price = sell_levels[sell_idx]

            # Calculate actual spacing achieved
            actual_spacing_pct = (sell_price / entry_price) - 1.0

            # Validate that sell_price > entry_price (must have profit)
            if sell_price <= entry_price:
                self.logger.log_warning(
                    f"[POSITION_RECOVERY] SELL price ${sell_price:.2f} <= entry ${entry_price:.2f}, "
                    f"this would result in loss! Using target price instead."
                )
                sell_price = sell_price_target
                # Find nearest level again
                sell_idx = min(
                    range(len(sell_levels)),
                    key=lambda i: abs(sell_levels[i] - sell_price)
                )
                sell_price = sell_levels[sell_idx]
                actual_spacing_pct = (sell_price / entry_price) - 1.0

            # CRITICAL: Check if current price already passed the sell target
            # If so, place limit order at current price to ensure immediate execution
            buffer_pct = 0.0005  # 0.05% buffer (same as eligibility check)
            price_passed_target = current_price >= sell_price * (1.0 - buffer_pct)

            if price_passed_target:
                # Price already passed sell target - use aggressive limit order
                unrealized_profit = (current_price - entry_price) * qty
                unrealized_profit_pct = (current_price / entry_price) - 1.0

                # Place limit order slightly ABOVE current price to bypass buffer check
                # This ensures: (1) order not filtered by ORDER_SKIP, (2) immediate fill, (3) maker fees
                # Buffer threshold is current_price * (1 + 0.0005), so we use 1.001 to be safely above
                aggressive_sell_price = current_price * 1.001  # 0.1% above current (bypasses 0.05% buffer)

                self.logger.log_warning(
                    f"[POSITION_RECOVERY] Current price ${current_price:.2f} already >= target SELL ${sell_price:.2f}! "
                    f"Unrealized profit: ${unrealized_profit:.2f} ({unrealized_profit_pct:.2%}). "
                    f"Placing aggressive SELL limit @ ${aggressive_sell_price:.2f} (current price +0.1%) to lock profit."
                )

                # Override sell_price to use aggressive price
                sell_price = aggressive_sell_price

            # Update ledger to track this position
            self.algorithm.grid_manager.add_buy_position(
                buy_level_index=nearest_buy_idx,
                size=qty,
                buy_price=entry_price
            )

            # Place hedge SELL order
            self.algorithm.grid_manager.place_pending_order(
                direction='sell',
                level_index=sell_idx,
                level_price=sell_price,
                bar_index=None,
                leg=None
            )

            self.logger.log_warning(
                f"[POSITION_RECOVERY] Recovered long position: "
                f"{qty:.8f} BTC @ entry=${entry_price:.2f} (nearest_buy_L{nearest_buy_idx+1}@${nearest_buy_price:.2f}) "
                f"-> placing SELL hedge @ ${sell_price:.2f} (L{sell_idx+1}, "
                f"target_spacing={spacing_pct:.2%}, actual_spacing={actual_spacing_pct:.2%})"
            )

            # Sync the hedge order to exchange immediately
            self._sync_exchange_orders(current_price=current_price, skip_safety_limits=False)

        except Exception as e:
            self.logger.log_error(f"[POSITION_RECOVERY] Error recovering long position: {e}", exc_info=True)

    def _replay_fills_best_effort(self) -> None:
        """
        Trade/fill replay (idempotent) to reconcile downtime.

        - Only runs in live mode
        - Filters to bot orders by client_oid_prefix
        - Persists to DB `trade_fills` + updates `replay_cursor`
        """
        if bool(self.dry_run) or self._db_store is None:
            return

        # Determine replay window
        bot_id = self._bot_id()
        cursor = None
        try:
            cursor = self._db_store.get_replay_cursor(bot_id=bot_id)
        except Exception:
            cursor = None

        last_seen_ts = None
        if isinstance(cursor, dict):
            last_seen_ts = cursor.get("last_seen_ts")

        since_ms = None
        try:
            if isinstance(last_seen_ts, datetime):
                # rewind a bit to tolerate clock skew / exchange pagination; dedupe via unique keys
                since_ms = int((last_seen_ts - timedelta(minutes=5)).timestamp() * 1000)
        except Exception:
            since_ms = None

        trades = []
        try:
            trades = self.execution_engine.get_my_trades(self.symbol, since_ms=since_ms, limit=200) or []
        except Exception:
            trades = []

        if not trades:
            return

        prefix = str(self._client_oid_prefix or "")
        fills_rows: list[dict] = []
        max_ts: datetime | None = None
        max_trade_id: str | None = None

        for t in trades:
            try:
                client_oid = str(t.get("client_order_id") or "")
                if prefix and not client_oid.startswith(prefix):
                    continue

                ts_ms = int(t.get("timestamp_ms") or 0)
                if ts_ms <= 0:
                    continue
                ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

                trade_id = str(t.get("trade_id") or "") or None
                order_id = str(t.get("order_id") or "") or None
                side = str(t.get("side") or "").lower()

                fills_rows.append(
                    {
                        "ts": ts,
                        "trade_id": trade_id,
                        "exchange_order_id": order_id,
                        "client_order_id": client_oid,
                        "side": side,
                        "price": float(t.get("price") or 0.0),
                        "qty": float(t.get("qty") or 0.0),
                        "fee": float(t.get("fee") or 0.0),
                        "fee_currency": str(t.get("fee_currency") or ""),
                        "raw": t.get("raw"),
                    }
                )

                if max_ts is None or ts > max_ts:
                    max_ts = ts
                    max_trade_id = trade_id
            except Exception:
                continue

        if not fills_rows:
            return

        # Skip DB writes if DB store is not available
        if self._db_store is None:
            return

        # Persist fills (idempotent on trade_id when available)
        try:
            self._db_store.insert_trade_fills(bot_id=bot_id, rows=fills_rows)
        except Exception:
            pass

        # Advance replay cursor
        try:
            if max_ts is not None:
                self._db_store.upsert_replay_cursor(
                    bot_id=bot_id,
                    last_seen_trade_id=max_trade_id,
                    last_seen_ts=max_ts,
                )
        except Exception:
            pass

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

    def _get_avg_cost_from_ledger(self) -> float | None:
        h = float(self._get_holdings_from_ledger())
        if h <= 0:
            return None
        cb = float(self._get_total_cost_basis_from_ledger())
        return float(cb / h) if cb > 0 else None

    def _log_summary(self, *, ts: datetime, current_price: float, portfolio_state: Dict[str, Any]) -> None:
        """
        Compact risk/PnL summary line for easy grepping.
        """
        try:
            px = float(current_price)
            equity = float(portfolio_state.get("equity", 0.0) or 0.0)
            long_h = float(portfolio_state.get("long_holdings", portfolio_state.get("holdings", 0.0)) or 0.0)
            short_h = float(portfolio_state.get("short_holdings", 0.0) or 0.0)
            net = float(long_h) - float(short_h)
            unreal = float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0)
            gm = self.algorithm.grid_manager
            realized = float(getattr(gm, "realized_pnl", 0.0) or 0.0)
            avg_cost = self._get_avg_cost_from_ledger()
            # Effective leverage = gross notional / equity (best-effort)
            gross_notional = (abs(float(long_h)) + abs(float(short_h))) * px
            eff_lev = (gross_notional / equity) if equity > 0 else 0.0
            fees = float(self._paper_commission_paid) if bool(self.dry_run) else 0.0

            self.logger.log_info(
                f"[SUMMARY] {ts} price={px:.2f} net_pos={net:.6f} "
                f"avg_cost={(avg_cost if avg_cost is not None else float('nan')):.2f} "
                f"unreal={unreal:+.2f} realized={realized:+.2f} "
                f"equity={equity:.2f} eff_lev={eff_lev:.2f} fees_est={fees:.4f}"
            )
        except Exception:
            return

    def _append_blotter_event(self, event: Dict[str, Any]) -> None:
        """Store blotter event in memory and append to state/blotter.jsonl (best-effort)."""
        try:
            self._blotter_events.append(event)
            if len(self._blotter_events) > int(self._blotter_maxlen):
                self._blotter_events = self._blotter_events[-int(self._blotter_maxlen):]

            base = Path(getattr(self.config, "state_dir", "state"))
            base.mkdir(parents=True, exist_ok=True)
            path = base / "blotter.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            return

    def _emit_periodic_reports(self, *, ts: datetime, current_price: float, portfolio_state: Dict[str, Any]) -> None:
        """
        Emit a heartbeat summary + blotter snapshot every 5 minutes (assuming 1m bars).

        Even if there are no fills, we still emit the summary and an empty blotter snapshot.
        This makes frontend integration and monitoring much easier.
        """
        try:
            # Best-effort: bar index is incremented in runner; 1 bar ~= 1 minute here.
            bar_idx = int(getattr(self, "_bar_index", 0) or 0)
            if bar_idx <= 0:
                return
            if (bar_idx % 5) != 0:
                return

            # Summary heartbeat
            self.logger.log_info("[SUMMARY_5M] ------------------------------")
            self._log_summary(ts=ts, current_price=current_price, portfolio_state=portfolio_state)

            # Blotter heartbeat: last N events
            tail_n = 10
            tail = self._blotter_events[-tail_n:] if self._blotter_events else []
            self.logger.log_info(
                f"[BLOTTER_5M] ts={ts} events_total={len(self._blotter_events)} tail={len(tail)}"
            )
            if not tail:
                self.logger.log_info("[BLOTTER_5M] (empty)")
            else:
                for e in tail[-5:]:
                    self.logger.log_info(
                        "[BLOTTER_5M] "
                        f"{e.get('ts')} {e.get('side')} L{e.get('level')} "
                        f"px={e.get('px')} qty={e.get('qty')} fee_est={e.get('fee_est')} "
                        f"net_pos={e.get('net_pos')} unreal={e.get('unreal')}"
                    )

            # Also write a compact tail snapshot for the dashboard
            base = Path(getattr(self.config, "state_dir", "state"))
            base.mkdir(parents=True, exist_ok=True)
            snap = {
                "ts": pd.Timestamp(ts).tz_convert("UTC").isoformat(),
                "symbol": str(self.symbol),
                "mode": "dry_run" if bool(self.dry_run) else "live",
                "summary": self._readable_summary_from_state(
                    portfolio_state=portfolio_state,
                    current_price=current_price,
                    realized=float(getattr(self.algorithm.grid_manager, "realized_pnl", 0.0) or 0.0),
                    avg_cost=self._get_avg_cost_from_ledger(),
                    fees_est=float(self._paper_commission_paid) if bool(self.dry_run) else None,
                ),
                "blotter_tail": tail,
            }
            tmp = base / "report_5m.json.tmp"
            out = base / "report_5m.json"
            tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(out)
        except Exception:
            return
    @staticmethod
    def _readable_summary_from_state(
        *,
        portfolio_state: Dict[str, Any],
        current_price: float,
        realized: float,
        avg_cost: float | None,
        fees_est: float | None,
    ) -> Dict[str, Any]:
        """Helper for report json payload (pure-ish, no side effects)."""
        equity = float(portfolio_state.get("equity", 0.0) or 0.0)
        long_h = float(
            portfolio_state.get("long_holdings", portfolio_state.get("holdings", 0.0)) or 0.0
        )
        short_h = float(portfolio_state.get("short_holdings", 0.0) or 0.0)
        net = float(long_h) - float(short_h)
        unreal = float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0)
        px = float(current_price)
        gross_notional = (abs(float(long_h)) + abs(float(short_h))) * px
        eff_lev = (gross_notional / equity) if equity > 0 else 0.0
        return {
            "current_price": px,
            "net_position": net,
            "avg_cost": avg_cost,
            "unrealized_pnl": unreal,
            "realized_pnl": float(realized),
            "equity": equity,
            "cash": float(portfolio_state.get("cash", 0.0) or 0.0),
            "effective_leverage": eff_lev,
            "fees_est": fees_est,
        }

    def _get_portfolio_state(self, current_price: float) -> Dict[str, Any]:
        """
        Get current portfolio state.

        Returns
        -------
        dict
            Portfolio state with equity, cash, holdings, etc.
        """
        try:
            # DRY-RUN: ALWAYS use paper portfolio based on config.initial_cash.
            # - If simulate_fills_in_dry_run=False: portfolio stays static (cash=initial_cash, no holdings).
            # - If simulate_fills_in_dry_run=True: portfolio is updated by OHLC fill simulation in run().
            if bool(self.dry_run):
                px = float(current_price)
                equity = float(self._paper_cash) + (float(self._paper_long_holdings) * px) - (float(self._paper_short_holdings) * px)
                unrealized_pnl = (float(self._paper_long_holdings) * px - float(self._paper_total_cost_basis)) + (
                    float(self._paper_total_short_entry_value) - float(self._paper_short_holdings) * px
                )
                return {
                    "equity": equity,
                    "cash": float(self._paper_cash),
                    "holdings": float(self._paper_long_holdings) - float(self._paper_short_holdings),
                    "long_holdings": float(self._paper_long_holdings),
                    "short_holdings": float(self._paper_short_holdings),
                    "unrealized_pnl": float(unrealized_pnl),
                    "daily_pnl": 0.0,
                }

            balance = self.execution_engine.get_account_balance()
            positions = self.execution_engine.get_positions(self.symbol)

            # Calculate total equity
            available_balance = float(balance.get("available_balance", 0.0) or 0.0)
            frozen_balance = float(balance.get("frozen_balance", 0.0) or 0.0)

            exch_long = 0.0
            exch_short = 0.0
            for pos in positions:
                sym = str(pos.get("symbol") or "")
                if self.symbol not in sym and self.symbol.replace("USDT", "") not in sym:
                    continue
                side = str(pos.get("side") or "spot").lower()
                qty = float(pos.get("quantity", 0.0) or 0.0)
                if self.market_type == "spot":
                    exch_long = qty
                else:
                    if side == "long":
                        exch_long += qty
                    elif side == "short":
                        exch_short += qty

            # Strategy ledger holdings/cost-basis (backtest-consistent for unrealized_pnl)
            ledger_holdings = self._get_holdings_from_ledger()
            total_cost_basis = self._get_total_cost_basis_from_ledger()
            ledger_short = 0.0
            ledger_short_entry_value = 0.0
            for positions_by_level in self.algorithm.grid_manager.short_positions.values():
                for pos in positions_by_level:
                    try:
                        sz = float(pos.get("size", 0.0))
                        px = float(pos.get("sell_price", 0.0))
                    except Exception:
                        continue
                    if sz > 0 and px > 0:
                        ledger_short += sz
                        ledger_short_entry_value += sz * px

            if self.market_type == "spot":
                total_equity = (available_balance + frozen_balance) + float(exch_long) * float(current_price)
            else:
                # For swap, use balance total_equity if available; fallback to available+frozen.
                total_equity = float(balance.get("total_equity") or 0.0) or (available_balance + frozen_balance)

            # Unrealized PnL uses ledger (same as backtest runner)
            long_unreal = float(ledger_holdings) * float(current_price) - float(total_cost_basis)
            short_unreal = float(ledger_short_entry_value) - float(ledger_short) * float(current_price)
            unrealized_pnl = long_unreal + short_unreal

            if self.market_type == "spot":
                drift = float(exch_long) - float(ledger_holdings)
                if abs(drift) > 1e-6:
                    self.logger.log_warning(
                        f"[LEDGER_DRIFT] exchange_long={exch_long:.8f} vs ledger_long={ledger_holdings:.8f} "
                        f"(drift={drift:+.8f}). If you traded manually or restarted bot, consider re-bootstrap."
                    )
            else:
                d_long = float(exch_long) - float(ledger_holdings)
                d_short = float(exch_short) - float(ledger_short)
                if abs(d_long) > 1e-6 or abs(d_short) > 1e-6:
                    self.logger.log_warning(
                        f"[LEDGER_DRIFT] exchange_long={exch_long:.8f} exchange_short={exch_short:.8f} "
                        f"vs ledger_long={ledger_holdings:.8f} ledger_short={ledger_short:.8f} "
                        f"(d_long={d_long:+.8f}, d_short={d_short:+.8f})"
                    )

            # Reconciliation data (exchange vs internal ledger)
            reconciliation = {}
            if not bool(self.dry_run):
                if self.market_type == "spot":
                    drift = float(exch_long) - float(ledger_holdings)
                    reconciliation = {
                        "exchange_long": exch_long,
                        "ledger_long": ledger_holdings,
                        "drift": drift,
                        "drift_pct": (drift / ledger_holdings * 100) if ledger_holdings > 0 else 0.0,
                        "status": "OK" if abs(drift) <= 1e-6 else "DRIFT",
                    }
                else:
                    d_long = float(exch_long) - float(ledger_holdings)
                    d_short = float(exch_short) - float(ledger_short)
                    reconciliation = {
                        "exchange_long": exch_long,
                        "exchange_short": exch_short,
                        "ledger_long": ledger_holdings,
                        "ledger_short": ledger_short,
                        "drift_long": d_long,
                        "drift_short": d_short,
                        "drift_long_pct": (d_long / ledger_holdings * 100) if ledger_holdings > 0 else 0.0,
                        "drift_short_pct": (d_short / ledger_short * 100) if ledger_short > 0 else 0.0,
                        "status": "OK" if abs(d_long) <= 1e-6 and abs(d_short) <= 1e-6 else "DRIFT",
                    }

            return {
                "equity": total_equity,
                "cash": available_balance,
                "holdings": ledger_holdings,
                "long_holdings": ledger_holdings,
                "short_holdings": ledger_short,
                "unrealized_pnl": unrealized_pnl,
                "daily_pnl": 0.0,  # Will be updated by algorithm
                "reconciliation": reconciliation if reconciliation else None,
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

                    # CRITICAL FIX: If get_order_status returns None/error (e.g., Bitget 40109),
                    # the order likely filled and was cleared from exchange history.
                    # Strategy: Assume it filled at limit price and trigger hedge logic.
                    if order_status is None:
                        # Try to get current price for realistic fill simulation
                        try:
                            latest_bar = self.data_source.get_latest_bar(self.symbol, "1m")
                            current_price = float(latest_bar["close"]) if latest_bar else None
                        except Exception:
                            current_price = None

                        # Assume filled at limit price (order_info contains the original order details)
                        fill_price = float(order_info.get("price", 0.0))
                        fill_qty = float(order_info.get("quantity", 0.0))

                        if fill_price > 0 and fill_qty > 0:
                            self.logger.log_warning(
                                f"[FILL_RECOVERY] order_id={order_id} not in open orders and "
                                f"get_order_status returned None. Assuming FILLED and triggering hedge. "
                                f"side={order_info.get('side')} level={order_info.get('level')} "
                                f"price={fill_price:.2f} qty={fill_qty:.6f}"
                            )

                            # Create filled_order event to trigger hedge logic
                            filled_order = {
                                "direction": order_info.get("side", "").lower(),
                                "price": fill_price,
                                "quantity": fill_qty,
                                "level": int(order_info.get("level", -1)),
                                "timestamp": datetime.now(timezone.utc),
                                "leg": order_info.get("leg"),
                            }

                            # Trigger strategy's fill handler (this will place hedge orders)
                            self.logger.log_info(
                                f"[FILL_HEDGE] Calling on_order_filled for {filled_order['direction'].upper()} "
                                f"L{int(filled_order.get('level', -1))} (recovery) - will place hedge order"
                            )
                            self.algorithm.on_order_filled(filled_order)

                            # Log to blotter (best-effort)
                            try:
                                notional = fill_qty * fill_price
                                fee_est = notional * float(getattr(self.config, "maker_fee", 0.0) or 0.0)
                                portfolio_state = self._get_portfolio_state(current_price=current_price or fill_price)
                                blotter_event = {
                                    "ts": pd.Timestamp(datetime.now(timezone.utc)).tz_convert("UTC").isoformat(),
                                    "symbol": str(self.symbol),
                                    "side": str(filled_order["direction"]).upper(),
                                    "level": int(filled_order.get("level", -1)) + 1 if int(filled_order.get("level", -1)) >= 0 else 0,
                                    "px": fill_price,
                                    "qty": fill_qty,
                                    "notional": notional,
                                    "fee_est": fee_est,
                                    "leg": (filled_order.get("leg") or "long"),
                                    "cash": float(portfolio_state.get("cash", 0.0) or 0.0),
                                    "net_pos": float(portfolio_state.get("holdings", 0.0) or 0.0),
                                    "unreal": float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0),
                                }
                                self._append_blotter_event(blotter_event)
                            except Exception:
                                pass

                            filled_orders.append(filled_order)

                        # Remove from pending to stop repeated queries
                        del self.pending_orders[order_id]
                        continue

                    if order_status:
                        status = order_status.get("status", "").lower()
                        # CCXT often returns "closed" for fully-filled orders.
                        if status in ["filled", "closed", "partially_filled"]:
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

                                # Update strategy (this will place hedge orders)
                                self.logger.log_info(
                                    f"[FILL_HEDGE] Calling on_order_filled for {filled_order['direction'].upper()} "
                                    f"L{int(filled_order.get('level', -1))} - will place hedge order"
                                )
                                self.algorithm.on_order_filled(filled_order)

                                # Log pending orders after hedge placement
                                pending_count_by_side = {}
                                for po in self.algorithm.grid_manager.pending_limit_orders:
                                    side = str(po.get('direction', ''))
                                    pending_count_by_side[side] = pending_count_by_side.get(side, 0) + 1
                                self.logger.log_info(
                                    f"[FILL_HEDGE] After on_order_filled: pending_orders = "
                                    f"BUY:{pending_count_by_side.get('buy', 0)} SELL:{pending_count_by_side.get('sell', 0)}"
                                )

                                # Dashboard/order blotter (best-effort, in-memory + state/blotter.jsonl)
                                try:
                                    notional = float(delta_qty) * float(px)
                                    fee_est = float(notional) * float(getattr(self.config, "maker_fee", 0.0) or 0.0)
                                    portfolio_state = self._get_portfolio_state(current_price=float(px))
                                    blotter_event = {
                                        "ts": pd.Timestamp(datetime.now(timezone.utc)).tz_convert("UTC").isoformat(),
                                        "symbol": str(self.symbol),
                                        "side": str(filled_order["direction"]).upper(),
                                        "level": int(filled_order.get("level", -1)) + 1 if int(filled_order.get("level", -1)) >= 0 else 0,
                                        "px": float(px),
                                        "qty": float(delta_qty),
                                        "notional": float(notional),
                                        "fee_est": float(fee_est),
                                        "leg": (filled_order.get("leg") or "long"),
                                        "cash": float(portfolio_state.get("cash", 0.0) or 0.0),
                                        "net_pos": float(portfolio_state.get("holdings", 0.0) or 0.0),
                                        "unreal": float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0),
                                    }
                                    self._append_blotter_event(blotter_event)
                                    self.logger.log_info(
                                        f"[BLOTTER] {filled_order['timestamp']} {str(filled_order['direction']).upper()} "
                                        f"L{blotter_event['level']} px={float(px):.2f} qty={float(delta_qty):.6f} "
                                        f"notional={float(notional):.2f} fee_est={float(fee_est):.4f}"
                                    )
                                except Exception:
                                    pass

                                # Explicit fill log (high-signal, easy to grep)
                                self.logger.log_info(
                                    f"[ORDER_FILLED] order_id={order_id} side={filled_order['direction']} "
                                    f"price={float(filled_order['price']):.2f} qty={float(filled_order['quantity']):.6f} "
                                    f"level={int(filled_order.get('level', -1))} leg={filled_order.get('leg') or 'long'} "
                                    f"status={status}"
                                )

                                # Log fill event to DB (strategy triggered fills)
                                client_oid = str(order_info.get("client_order_id") or "")
                                self._log_order_event(
                                    client_order_id=client_oid,
                                    event_type="FILLED" if status in ["filled", "closed"] else "PARTIAL",
                                    trigger="strategy",
                                    new_status="filled" if status in ["filled", "closed"] else "partial",
                                    old_status="open",
                                    exchange_order_id=order_id,
                                    fill_qty=float(delta_qty),
                                    fill_price=float(px),
                                    fill_fee=float(fee_est) if fee_est else None,
                                    details={
                                        "level": int(filled_order.get("level", -1)),
                                        "leg": filled_order.get("leg") or "long",
                                        "total_filled": float(filled_quantity),
                                    },
                                )

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

    def _make_client_oid(self, direction: str, level_index: int, leg: Optional[str], increment_version: bool = False) -> str:
        """Generate unique client order ID.
        
        Parameters
        ----------
        increment_version : bool
            If True, increment version counter for this order key (use when placing new order).
            If False, return current version (use for lookups).
        """
        leg_tag = leg if leg is not None else "long"
        order_key = f"{direction}_{int(level_index)}_{leg_tag}"
        
        if increment_version:
            self._order_version[order_key] = self._order_version.get(order_key, 0) + 1
        
        version = self._order_version.get(order_key, 1)
        return f"{self._client_oid_prefix}{order_key}_v{version}"

    def _apply_active_buy_levels_filter(self, current_price: float, keep_levels: int, already_on_exchange: set | None = None) -> None:
        """
        Keep only the nearest `keep_levels` BUY pending orders (below current price) enabled.

        IMPORTANT:
        - This MUST be reversible (do NOT permanently remove orders).
        - We flip order['placed'] flags each bar, matching `simple_lean_runner.py` behavior.
        - This affects both:
          (1) real exchange sync (which orders are placed/cancelled)
          (2) dry-run fill simulation (which orders are eligible to trigger)

        Parameters
        ----------
        already_on_exchange : set | None
            Set of (direction, level_index, leg) tuples for orders already on the exchange.
            These orders are given priority to avoid unnecessary cancel/re-place cycles.
        """
        if keep_levels <= 0:
            return
        gm = self.algorithm.grid_manager
        pending = gm.pending_limit_orders
        if not pending:
            return

        buy_orders = [o for o in pending if str(o.get("direction")) == "buy" and o.get("leg") != "short_cover"]
        if not buy_orders:
            return

        # Apply buffer to avoid orders too close to current price (consistent with _sync_exchange_orders)
        buffer_pct = 0.0005  # 0.05% buffer
        price_threshold = current_price * (1.0 - buffer_pct)

        # Eligible BUY orders are those below the buffer threshold (not just below current price).
        eligible = [o for o in buy_orders if float(o.get("price", 0.0)) <= price_threshold]
        if len(eligible) <= keep_levels:
            # Enable all eligible, disable ineligible (above threshold)
            for o in buy_orders:
                o["placed"] = float(o.get("price", 0.0)) <= price_threshold
                if not o["placed"]:
                    o["triggered"] = False
            return

        # Build keep_ids with sticky behavior:
        # 1. First, keep orders already on exchange (if eligible)
        # 2. Then fill remaining slots with closest orders
        already_on_exchange = already_on_exchange or set()
        
        # Partition eligible into "already placed" and "new"
        already_placed_eligible = []
        new_eligible = []
        for o in eligible:
            oid = (o.get("direction"), int(o.get("level_index", -1)), o.get("leg"))
            if oid in already_on_exchange:
                already_placed_eligible.append(o)
            else:
                new_eligible.append(o)
        
        # Sort both by distance (closest first)
        already_placed_eligible.sort(key=lambda o: abs(float(current_price) - float(o.get("price", 0.0))))
        new_eligible.sort(key=lambda o: abs(float(current_price) - float(o.get("price", 0.0))))
        
        # Keep already-placed orders first, then fill with new ones
        keep_list = already_placed_eligible[:keep_levels]
        remaining_slots = keep_levels - len(keep_list)
        if remaining_slots > 0:
            keep_list.extend(new_eligible[:remaining_slots])
        
        keep_ids = {(o.get("direction"), int(o.get("level_index", -1)), o.get("leg")) for o in keep_list}

        # Enable kept orders; disable the rest (and clear triggered state)
        for o in buy_orders:
            oid = (o.get("direction"), int(o.get("level_index", -1)), o.get("leg"))
            is_eligible = float(o.get("price", 0.0)) <= price_threshold
            o["placed"] = bool(is_eligible and oid in keep_ids)
            if not o["placed"]:
                o["triggered"] = False

    # ====================================================================
    # Execution safety fuses (infra hard-gates)
    # ====================================================================
    def _safety_roll_window(self, now: datetime) -> None:
        w = now.replace(second=0, microsecond=0)
        if self._safety_window_start is None or w > self._safety_window_start:
            self._safety_window_start = w
            self._safety_orders_count = 0
            self._safety_cancels_count = 0
            self._safety_notional_added = 0.0

    def _safety_is_kill_switch_on(self) -> bool:
        if str(os.getenv("TAOQUANT_KILL_SWITCH", "")).strip().lower() in ("1", "true", "yes"):
            return True
        try:
            return bool(self.safety_kill_switch_file.exists())
        except Exception:
            return False

    def _safety_should_degrade(self, *, bar_timestamp: datetime) -> tuple[bool, str]:
        """
        Return (degrade, reason). When degraded: allow cancels, deny new placements.
        """
        # Data stale => no new orders
        try:
            lag = (datetime.now(timezone.utc) - bar_timestamp).total_seconds()
            if self.safety_data_stale_seconds > 0 and lag > float(self.safety_data_stale_seconds):
                return True, f"DATA_FEED_STALE(lag={lag:.0f}s)"
        except Exception:
            pass

        # Exchange errors => degrade
        if self.safety_exchange_degrade_errors > 0 and int(self._consecutive_loop_errors) >= int(self.safety_exchange_degrade_errors):
            return True, f"EXCHANGE_API_DEGRADED(errors={int(self._consecutive_loop_errors)})"

        return False, ""

    def _safety_can_cancel(self, *, now: datetime) -> bool:
        self._safety_roll_window(now)
        if self.safety_max_cancels_per_min <= 0:
            return True
        return self._safety_cancels_count < int(self.safety_max_cancels_per_min)

    def _safety_mark_cancel(self) -> None:
        self._safety_cancels_count += 1

    def _safety_can_place(self, *, now: datetime, notional: float, equity: float) -> bool:
        self._safety_roll_window(now)
        if self.safety_max_orders_per_min > 0 and self._safety_orders_count >= int(self.safety_max_orders_per_min):
            return False
        cap = float(equity) * float(self.safety_max_notional_add_frac_equity_per_min)
        if cap > 0 and (self._safety_notional_added + float(notional)) > cap:
            return False
        return True

    def _safety_mark_place(self, *, notional: float) -> None:
        self._safety_orders_count += 1
        self._safety_notional_added += float(notional)

    def _sync_exchange_orders(self, current_price: Optional[float], current_time: Optional[datetime] = None, skip_safety_limits: bool = False) -> None:
        """
        Sync algorithm.pending_limit_orders -> exchange open orders.

        For backtest-consistency:
        - Grid limit orders must be resting on the exchange.
        - Sizes are recomputed each bar using the same sizing function (factors + equity).
        - Orders are only eligible if they won't immediately cross the market:
          BUY only if level_price <= current_price; SELL only if level_price >= current_price.
        
        Parameters
        ----------
        skip_safety_limits : bool
            If True, bypass safety rate limits (useful for bootstrap to place initial grid).
        """
        # If grid disabled, cancel all bot orders (real) or just log (dry-run).
        if not bool(self.algorithm.grid_manager.grid_enabled):
            if not self.dry_run:
                self.execution_engine.cancel_all_orders(self.symbol, client_oid_prefix=self._client_oid_prefix)
            else:
                self.logger.log_warning("[DRY_RUN] grid disabled -> would cancel all bot orders")
            return

        cp = float(current_price) if current_price is not None else None

        # NOTE:
        # active_buy_levels filter is applied in the main loop via `_apply_active_buy_levels_filter`
        # to keep it reversible (backtest-consistent). DO NOT permanently flip placed flags here.
        pending = list(self.algorithm.grid_manager.pending_limit_orders)
        cp = float(current_price) if current_price is not None else None

        # Log sync start (helps debug hedge order placement)
        pending_by_side = {}
        for p in pending:
            side = str(p.get('direction', ''))
            placed = bool(p.get('placed', False))
            key = f"{side}_placed" if placed else f"{side}_not_placed"
            pending_by_side[key] = pending_by_side.get(key, 0) + 1
        if not self.dry_run:  # Only log in live mode to avoid spam
            cp_display = cp if cp is not None else 0.0
            self.logger.log_info(
                f"[SYNC_START] cp=${cp_display:.2f} pending_orders: {dict(pending_by_side)}"
            )

        desired: Dict[str, dict] = {}
        for o in pending:
            if not bool(o.get("placed", False)):
                continue
            direction = str(o.get("direction"))
            level_index = int(o.get("level_index"))
            price = float(o.get("price"))
            leg = o.get("leg")

            # Eligibility to avoid immediate taker fills
            # Add small buffer (0.05% of price) to prevent orders that are exactly at market from executing immediately
            if cp is not None:
                buffer_pct = 0.0005  # 0.05% buffer
                if direction == "buy" and price > cp * (1.0 - buffer_pct):
                    self.logger.log_warning(
                        f"[ORDER_SKIP] BUY L{level_index+1} @ ${price:.2f} too close to market (cp=${cp:.2f}, "
                        f"threshold=${cp * (1.0 - buffer_pct):.2f}) - would execute immediately as taker"
                    )
                    continue  # Skip buy orders at or too close to current price
                if direction == "sell" and price < cp * (1.0 + buffer_pct):
                    self.logger.log_warning(
                        f"[ORDER_SKIP] SELL L{level_index+1} @ ${price:.2f} too close to market (cp=${cp:.2f}, "
                        f"threshold=${cp * (1.0 + buffer_pct):.2f}) - would execute immediately as taker"
                    )
                    continue  # Skip sell orders at or too close to current price

            desired[self._order_key(direction, level_index, leg)] = o

        # Compute target quantities for preview and/or placing on exchange
        fs = self._last_factor_state or {}
        mr_z = fs.get("mr_z")
        trend_score = fs.get("trend_score")
        br_down = fs.get("breakout_risk_down")
        br_up = fs.get("breakout_risk_up")
        rp = fs.get("range_pos")
        fr = fs.get("funding_rate")
        mtf = fs.get("minutes_to_funding")
        vs = fs.get("vol_score")

        ps = self._get_portfolio_state(
            current_price=float(cp)
            if cp is not None
            else (float(list(desired.values())[0]["price"]) if desired else 1.0)
        )

        planned: list[dict] = []
        for _, o in desired.items():
            direction = str(o.get("direction"))
            level_index = int(o.get("level_index"))
            price = float(o.get("price"))
            leg = o.get("leg")
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
            if qty <= 0:
                continue
            planned.append(
                {
                    "direction": direction,
                    "level_index": level_index,
                    "price": price,
                    "quantity": qty,
                    "leg": leg,
                    "reason": getattr(throttle, "reason", None),
                }
            )

        # Expose latest planned active limit orders for dashboard (dry-run + live).
        # NOTE: "planned" already accounts for:
        # - active_buy_levels filter (via placed flags)
        # - immediate-cross eligibility around current price
        self._last_planned_limit_orders = list(planned)
        self._last_planned_limit_orders_ts = current_time or datetime.now(timezone.utc)

        # Dry-run preview: log a compact order summary periodically
        if self.dry_run:
            if int(getattr(self, "_bar_index", 0) or 0) % 5 == 0:
                buys = sorted([o for o in planned if o["direction"] == "buy"], key=lambda x: x["price"], reverse=True)
                sells = sorted([o for o in planned if o["direction"] == "sell"], key=lambda x: x["price"])
                ts = current_time or datetime.now(timezone.utc)
                self.logger.log_info(
                    f"[DRY_RUN_ORDERS] {ts} price={cp if cp is not None else 'NA'} "
                    f"planned_buy={len(buys)} planned_sell={len(sells)} "
                    f"(active_buy_levels={self.active_buy_levels}, in_cooldown={self._in_cooldown(ts)})"
                )
                for o in buys[:5]:
                    self.logger.log_info(
                        f"  BUY  L{o['level_index']+1} @{o['price']:.2f} qty={o['quantity']:.6f}"
                    )
                for o in sells[:5]:
                    self.logger.log_info(
                        f"  SELL L{o['level_index']+1} @{o['price']:.2f} qty={o['quantity']:.6f}"
                    )
            return

        # === Real exchange sync below (non-dry-run) ===
        now_ts = datetime.now(timezone.utc)
        bar_ts = current_time or now_ts

        # Kill switch: cancel bot orders and do nothing else.
        if self._safety_is_kill_switch_on():
            try:
                self.execution_engine.cancel_all_orders(self.symbol, client_oid_prefix=self._client_oid_prefix)
            except Exception:
                pass
            self.logger.log_warning("[KILL_SWITCH] enabled -> cancelled bot orders, skip placements.")
            return

        degrade, degrade_reason = self._safety_should_degrade(bar_timestamp=bar_ts)
        allow_place = not degrade
        if degrade:
            self.logger.log_warning(f"[SAFETY_DEGRADE] {degrade_reason} -> cancel-only mode (no new orders).")

        equity_for_limits = float(ps.get("equity", self.config.initial_cash) or self.config.initial_cash)

        open_orders = self.execution_engine.get_open_orders(self.symbol)
        # Map by order_key (direction:level:leg) instead of full client_oid
        # This allows matching orders regardless of version suffix
        open_by_order_key: Dict[str, dict] = {}
        for oo in open_orders:
            coid = str(oo.get("client_order_id") or "")
            if coid.startswith(self._client_oid_prefix):
                # Parse: tg_BTCUSDT_TS_buy_11_long_v1 -> order_key = buy:11:long
                suffix = coid[len(self._client_oid_prefix):]
                parts = suffix.split("_")
                if len(parts) >= 3:
                    direction = parts[0]
                    level_str = parts[1]
                    # leg is parts[2], version is parts[3] (if exists)
                    leg_tag = parts[2]
                    leg = None if leg_tag == "long" else leg_tag
                    order_key = self._order_key(direction, int(level_str), leg)
                    open_by_order_key[order_key] = oo

        # Log sync state for debugging (every 5 minutes or when mismatch)
        desired_buy_levels = sorted([int(k.split(":")[1]) for k in desired.keys() if k.startswith("buy:")])
        open_buy_levels = []
        for k in open_by_order_key.keys():
            parts = k.split(":")
            if len(parts) >= 2 and parts[0] == "buy":
                open_buy_levels.append(int(parts[1]))
        open_buy_levels = sorted(open_buy_levels)
        
        if desired_buy_levels != open_buy_levels:
            cp_str = f"{cp:.2f}" if cp is not None else "NA"
            self.logger.log_info(
                f"[SYNC_STATE] desired_buy_levels={desired_buy_levels} open_buy_levels={open_buy_levels} "
                f"cp={cp_str}"
            )

        # Cancel extra bot orders not in desired set
        # Determine trigger: bootstrap if skip_safety_limits, else strategy (normal sync)
        cancel_trigger = "bootstrap" if skip_safety_limits else "strategy"
        for order_key, oo in list(open_by_order_key.items()):
            if order_key not in desired:
                oid = str(oo.get("order_id") or "")
                coid = str(oo.get("client_order_id") or "")
                # Parse order_key to get direction and level for logging
                parts = order_key.split(":")
                direction = parts[0] if len(parts) > 0 else "?"
                level_index = int(parts[1]) if len(parts) > 1 else 0
                if oid:
                    if self._safety_can_cancel(now=now_ts):
                        # Log cancellation with reason
                        self.logger.log_warning(
                            f"[ORDER_CANCEL] {direction.upper()} L{level_index+1} not in desired set "
                            f"(desired_keys={len(desired)}, order_id={oid}, client_oid={coid})"
                        )
                        self.execution_engine.cancel_order(self.symbol, oid)
                        self._safety_mark_cancel()
                        # Log event to DB
                        self._log_order_event(
                            client_order_id=coid,
                            event_type="CANCELLED",
                            trigger=cancel_trigger,
                            new_status="cancelled",
                            old_status="open",
                            exchange_order_id=oid,
                            details={"reason": "not_in_desired_set", "order_key": order_key},
                        )
                        # Throttle API calls (Bitget limit: 10 req/s)
                        time.sleep(0.12)
                    else:
                        self.logger.log_warning("[SAFETY] cancel rate limited; skip further cancels this minute.")
                        break

        for o in planned:
            if not allow_place:
                break
            direction = str(o.get("direction"))
            level_index = int(o.get("level_index"))
            price = float(o.get("price"))
            leg = o.get("leg")
            qty = float(o.get("quantity"))
            order_key = self._order_key(direction, level_index, leg)

            if order_key in open_by_order_key:
                oo = open_by_order_key[order_key]
                open_qty = float(oo.get("quantity", 0.0) or 0.0)
                # Use 20% tolerance because exchange may truncate/round our quantity
                # (e.g., we send 0.000795, exchange accepts 0.0007 due to precision)
                # If order exists with similar quantity, skip (don't replace)
                if open_qty > 0 and abs(open_qty - qty) / max(open_qty, qty) < 0.20:
                    continue
                # Only replace if quantity difference is significant (>20%)
                # Log when replacing to help debug
                existing_coid = str(oo.get("client_order_id") or "")
                self.logger.log_info(
                    f"[ORDER_REPLACE] {order_key} qty mismatch: open={open_qty:.6f} vs target={qty:.6f} "
                    f"(diff={(abs(open_qty - qty) / max(open_qty, qty) * 100):.1f}%)"
                )
                oid = str(oo.get("order_id") or "")
                if oid:
                    if self._safety_can_cancel(now=now_ts):
                        self.execution_engine.cancel_order(self.symbol, oid)
                        self._safety_mark_cancel()
                        # Throttle API calls (Bitget limit: 10 req/s)
                        time.sleep(0.12)
                    else:
                        self.logger.log_warning("[SAFETY] cancel rate limited; skip replace cancels this minute.")
                        continue

            notional = float(qty) * float(price)
            if not skip_safety_limits and not self._safety_can_place(now=now_ts, notional=notional, equity=equity_for_limits):
                self.logger.log_warning(
                    "[SAFETY] place limited; skip new orders this minute "
                    f"(orders={self._safety_orders_count}, cancels={self._safety_cancels_count}, "
                    f"notional_added={self._safety_notional_added:.2f})."
                )
                break

            # Generate unique client_oid with version increment for new placement
            client_oid = self._make_client_oid(direction, level_index, leg, increment_version=True)

            # Derivatives position semantics for Bitget swap:
            #
            # IMPORTANT: Bitget swap in unilateral position mode REQUIRES tradeSide parameter
            # for all orders to distinguish between opening and closing positions.
            # Error 40774 "The order type for unilateral position must also be the unilateral position type."
            # occurs if tradeSide is missing or incorrect.
            #
            # Correct tradeSide values:
            # - BUY to open long: tradeSide='open'
            # - SELL to close long: tradeSide='close'
            # - SELL to open short: tradeSide='open'
            # - BUY to close short: tradeSide='close'
            params: Dict[str, Any] = {}
            if self.market_type in ("swap", "future", "futures"):
                if leg == "short_cover" and direction == "buy":
                    # Close short position - use tradeSide=close
                    params["tradeSide"] = "close"
                elif leg == "short_open" and direction == "sell":
                    # Open short position - use tradeSide=open
                    params["tradeSide"] = "open"
                elif leg is None and direction == "buy":
                    # Open long position (grid BUY) - use tradeSide=open
                    params["tradeSide"] = "open"
                elif leg is None and direction == "sell":
                    # Close long position (grid SELL) - MUST use tradeSide=close
                    params["tradeSide"] = "close"

            # Determine trigger for this order placement
            place_trigger = "bootstrap" if skip_safety_limits else "strategy"

            r = self.execution_engine.place_order(
                symbol=self.symbol,
                side=direction,
                quantity=qty,
                price=price,
                order_type="limit",
                client_order_id=client_oid,
                params=params or None,
            )
            if r and r.get("order_id"):
                self._safety_mark_place(notional=notional)
                oid = str(r["order_id"])
                self.pending_orders[oid] = {
                    "side": direction,
                    "price": price,
                    "quantity": qty,
                    "level": level_index,
                    "leg": leg,
                    "_processed_filled_qty": 0.0,
                    "client_order_id": client_oid,
                    "reason": o.get("reason"),
                }
                # Log successful order placement (especially important for bootstrap)
                self.logger.log_info(
                    f"[ORDER_PLACED] {direction.upper()} L{level_index+1} @ ${price:.2f} "
                    f"qty={qty:.6f} notional=${notional:.2f} "
                    f"order_id={oid} client_oid={client_oid}"
                )
                # Track bootstrap orders placed
                if skip_safety_limits:
                    self._bootstrap_orders_placed += 1
                # Log event to DB
                self._log_order_event(
                    client_order_id=client_oid,
                    event_type="SUBMITTED",
                    trigger=place_trigger,
                    new_status="open",
                    exchange_order_id=oid,
                    details={
                        "price": price,
                        "qty": qty,
                        "notional": notional,
                        "level": level_index,
                        "leg": leg,
                        "reason": o.get("reason"),
                    },
                )
            else:
                self.logger.log_warning(
                    f"[ORDER_FAILED] {direction.upper()} L{level_index+1} @ ${price:.2f} "
                    f"qty={qty:.6f} - place_order returned None/empty"
                )
                # Log failure event to DB
                self._log_order_event(
                    client_order_id=client_oid,
                    event_type="REJECTED",
                    trigger=place_trigger,
                    new_status="rejected",
                    details={
                        "price": price,
                        "qty": qty,
                        "level": level_index,
                        "leg": leg,
                        "error": "place_order returned None/empty",
                    },
                )
                # Log error
                self._log_db_error(
                    level="WARNING",
                    message=f"Order placement failed: {direction.upper()} L{level_index+1} @ ${price:.2f}",
                    component="order_sync",
                    order_id=client_oid,
                    details={"price": price, "qty": qty, "level": level_index},
                )
            
            # Throttle API calls to stay under Bitget's 10 requests/second limit
            # Use 120ms delay (~8 req/s) to leave headroom for other API calls
            time.sleep(0.12)

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
                    # Fresh bar received => clear loop error streak
                    self._consecutive_loop_errors = 0
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

                    # Log grid snapshot if it changed (e.g., future mid-shift / manual update)
                    sig = self._grid_sig()
                    if self._grid_signature is None:
                        self._grid_signature = sig
                    elif sig != self._grid_signature:
                        self._grid_signature = sig
                        self._log_grid_snapshot("updated")

                    # Log portfolio state periodically
                    self.logger.log_portfolio(
                        equity=portfolio_state["equity"],
                        cash=portfolio_state["cash"],
                        holdings=portfolio_state["holdings"],
                        unrealized_pnl=portfolio_state["unrealized_pnl"],
                    )

                    # Append 1m market bar (dashboard computes 24h stats from this stream)
                    self._append_market_bar(bar_timestamp=bar_timestamp, latest_bar=latest_bar)

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

                    # Execution-layer policy: active BUY levels filter (backtest-consistent, reversible)
                    cp = float(latest_bar["close"])
                    if self.active_buy_levels is not None and self.active_buy_levels > 0:
                        keep_n = int(self.active_buy_levels)
                        if self._in_cooldown(bar_timestamp) and self.cooldown_active_buy_levels > 0:
                            keep_n = int(self.cooldown_active_buy_levels)
                        
                        # Get orders already on exchange for sticky behavior
                        already_on_exchange: set = set()
                        if not self.dry_run:
                            try:
                                open_orders = self.execution_engine.get_open_orders(self.symbol) or []
                                for oo in open_orders:
                                    coid = str(oo.get("client_order_id") or "")
                                    if coid.startswith(self._client_oid_prefix):
                                        # Parse: tg_BTCUSDT_TS_buy_11_long -> direction=buy, level=11, leg=long
                                        suffix = coid[len(self._client_oid_prefix):]
                                        parts = suffix.split("_")
                                        if len(parts) >= 3:
                                            direction, level_str, leg = parts[0], parts[1], parts[2]
                                            # Store with None as leg to match how orders store it internally
                                            # (grid_manager stores leg as None for regular long orders)
                                            leg_normalized = None if leg == "long" else leg
                                            already_on_exchange.add((direction, int(level_str), leg_normalized))
                            except Exception:
                                pass  # If we can't get orders, proceed without sticky behavior
                        
                        self._apply_active_buy_levels_filter(
                            current_price=cp, 
                            keep_levels=keep_n, 
                            already_on_exchange=already_on_exchange
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

                    # Dry-run fill simulation (optional):
                    # In plain dry-run we only show "planned orders". If simulate_fills_in_dry_run is enabled,
                    # we additionally simulate fills using OHLC touch rules and update a paper portfolio.
                    if self.dry_run and self.simulate_fills_in_dry_run:
                        fills_this_bar = 0
                        in_cd = self._in_cooldown(bar_timestamp)
                        while fills_this_bar < int(self.max_fills_per_bar):
                            triggered = self.algorithm.grid_manager.check_limit_order_triggers(
                                current_price=float(latest_bar["close"]),
                                prev_price=None,
                                bar_high=float(latest_bar["high"]),
                                bar_low=float(latest_bar["low"]),
                                bar_index=int(self._bar_index),
                                range_pos=float(self._last_factor_state.get("range_pos", 0.5)),
                            )
                            if not triggered:
                                break

                            if in_cd and str(triggered.get("direction")) == "buy":
                                self.algorithm.grid_manager.reset_triggered_orders()
                                break

                            size, _ = self.algorithm.grid_manager.calculate_order_size(
                                direction=str(triggered["direction"]),
                                level_index=int(triggered["level_index"]),
                                level_price=float(triggered["price"]),
                                equity=float(portfolio_state.get("equity", self.config.initial_cash)),
                                daily_pnl=float(portfolio_state.get("daily_pnl", 0.0)),
                                risk_budget=float(self.algorithm.risk_budget),
                                holdings_btc=float(portfolio_state.get("holdings", 0.0)),
                                order_leg=triggered.get("leg"),
                                current_price=float(latest_bar["close"]),
                                mr_z=self._last_factor_state.get("mr_z"),
                                trend_score=self._last_factor_state.get("trend_score"),
                                breakout_risk_down=self._last_factor_state.get("breakout_risk_down"),
                                breakout_risk_up=self._last_factor_state.get("breakout_risk_up"),
                                range_pos=self._last_factor_state.get("range_pos"),
                                funding_rate=self._last_factor_state.get("funding_rate"),
                                minutes_to_funding=self._last_factor_state.get("minutes_to_funding"),
                                vol_score=self._last_factor_state.get("vol_score"),
                            )
                            qty = float(size)
                            if qty <= 0:
                                triggered["triggered"] = False
                                triggered["last_checked_bar"] = None
                                break

                            # Execution price model (same as backtest runner)
                            limit_px = float(triggered["price"])
                            bar_open = float(latest_bar["open"])
                            direction = str(triggered["direction"])
                            exec_px = min(limit_px, bar_open) if direction == "buy" else max(limit_px, bar_open)

                            commission_rate = float(getattr(self.config, "maker_fee", 0.0))
                            mkt_px = float(latest_bar["close"])
                            leg = triggered.get("leg")

                            # Paper portfolio updates (simplified but backtest-consistent)
                            if leg == "short_open" and direction == "sell":
                                proceeds = qty * exec_px
                                commission = proceeds * commission_rate
                                self._paper_commission_paid += float(commission)
                                equity_now = float(self._paper_cash) + (float(self._paper_long_holdings) * mkt_px) - (float(self._paper_short_holdings) * mkt_px)
                                max_notional = equity_now * float(getattr(self.config, "leverage", 1.0))
                                new_gross = (float(self._paper_long_holdings) * mkt_px) + ((float(self._paper_short_holdings) + qty) * mkt_px)
                                if not (equity_now > 0 and new_gross <= max_notional):
                                    self.algorithm.grid_manager.reset_triggered_orders()
                                    break
                                self._paper_cash += proceeds - commission
                                self._paper_short_holdings += qty
                                self._paper_total_short_entry_value += qty * exec_px
                            elif leg == "short_cover" and direction == "buy":
                                if float(self._paper_short_holdings) <= 1e-12:
                                    self.algorithm.grid_manager.reset_triggered_orders()
                                    break
                                cover = min(qty, float(self._paper_short_holdings))
                                cost = cover * exec_px
                                commission = cost * commission_rate
                                self._paper_commission_paid += float(commission)
                                self._paper_cash -= cost + commission
                                self._paper_short_holdings = max(0.0, float(self._paper_short_holdings) - cover)
                                self._paper_total_short_entry_value = max(0.0, float(self._paper_total_short_entry_value) - cover * exec_px)
                                qty = cover
                            elif direction == "buy":
                                notional = qty * exec_px
                                commission = notional * commission_rate
                                self._paper_commission_paid += float(commission)
                                equity_now = float(self._paper_cash) + (float(self._paper_long_holdings) * mkt_px) - (float(self._paper_short_holdings) * mkt_px)
                                max_notional = equity_now * float(getattr(self.config, "leverage", 1.0))
                                new_gross = ((float(self._paper_long_holdings) + qty) * mkt_px) + (float(self._paper_short_holdings) * mkt_px)
                                if not (equity_now > 0 and new_gross <= max_notional):
                                    self.algorithm.grid_manager.reset_triggered_orders()
                                    break
                                self._paper_cash -= notional + commission
                                self._paper_long_holdings += qty
                                self._paper_total_cost_basis += notional
                            else:
                                # sell long
                                if qty > float(self._paper_long_holdings) + 1e-12:
                                    self.algorithm.grid_manager.reset_triggered_orders()
                                    break
                                proceeds = qty * exec_px
                                commission = proceeds * commission_rate
                                self._paper_commission_paid += float(commission)
                                self._paper_cash += proceeds - commission
                                self._paper_long_holdings = max(0.0, float(self._paper_long_holdings) - qty)
                                match = self.algorithm.grid_manager.match_sell_order(
                                    sell_level_index=int(triggered["level_index"]),
                                    sell_size=float(qty),
                                )
                                if match is not None:
                                    _, buy_price, msz = match
                                    self._paper_total_cost_basis = max(0.0, float(self._paper_total_cost_basis) - float(msz) * float(buy_price))
                                    pnl = (float(exec_px) - float(buy_price)) * float(msz)
                                    self.algorithm.grid_manager.update_realized_pnl(float(pnl))

                            filled_order = {
                                "direction": direction,
                                "price": float(exec_px),
                                "quantity": float(qty),
                                "level": int(triggered["level_index"]),
                                "timestamp": bar_timestamp,
                                "leg": leg,
                            }
                            self.algorithm.on_order_filled(filled_order)
                            fills_this_bar += 1
                            # Recompute portfolio after this fill (for blotter/summary)
                            portfolio_state = self._get_portfolio_state(current_price=float(latest_bar["close"]))
                            notional = float(qty) * float(exec_px)
                            blotter_event = {
                                "ts": pd.Timestamp(bar_timestamp).tz_convert("UTC").isoformat(),
                                "symbol": str(self.symbol),
                                "side": direction.upper(),
                                "level": int(triggered["level_index"]) + 1,
                                "px": float(exec_px),
                                "qty": float(qty),
                                "notional": float(notional),
                                "fee_est": float(commission),
                                "leg": leg or "long",
                                "cash": float(portfolio_state.get("cash", 0.0) or 0.0),
                                "net_pos": float(portfolio_state.get("holdings", 0.0) or 0.0),
                                "unreal": float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0),
                            }
                            self._append_blotter_event(blotter_event)
                            self.logger.log_info(
                                f"[BLOTTER] {bar_timestamp} {direction.upper()} L{int(triggered['level_index'])+1} "
                                f"px={exec_px:.2f} qty={qty:.6f} notional={notional:.2f} "
                                f"fee_est={commission:.4f} cash={float(portfolio_state.get('cash', 0.0)):.2f} "
                                f"net_pos={float(portfolio_state.get('holdings', 0.0)):.6f} "
                                f"unreal={float(portfolio_state.get('unrealized_pnl', 0.0)):+.2f}"
                            )
                            # Optional: a compact summary every fill
                            self._log_summary(ts=bar_timestamp, current_price=float(latest_bar["close"]), portfolio_state=portfolio_state)

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

                    # Sync grid orders to exchange (place/cancel/re-size) or preview (dry-run)
                    self._sync_exchange_orders(
                        current_price=float(latest_bar["close"]),
                        current_time=bar_timestamp,
                    )

                    # Heartbeat report every 5 minutes (even if no fills)
                    self._emit_periodic_reports(
                        ts=bar_timestamp,
                        current_price=float(latest_bar["close"]),
                        portfolio_state=portfolio_state,
                    )

                    # Update live_status.json for dashboard
                    status_payload = self._update_live_status(latest_bar, bar_timestamp)
                    # Best-effort: persist to DB (even if dashboard status writing is disabled)
                    if not isinstance(status_payload, dict) and self._db_store is not None:
                        try:
                            status_payload = self._build_live_status_dict(latest_bar, bar_timestamp)
                        except Exception:
                            status_payload = None
                    if isinstance(status_payload, dict):
                        self._persist_status_to_db(status=status_payload, bar_timestamp=bar_timestamp)

                    # Wait for next minute
                    # Calculate sleep time to align with minute boundary
                    now = datetime.now(timezone.utc)
                    next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
                    sleep_seconds = (next_minute - now).total_seconds()
                    if sleep_seconds > 0:
                        time.sleep(min(sleep_seconds, 60))

                except KeyboardInterrupt:
                    self.logger.log_info("Received interrupt signal, stopping...")
                    self._end_db_session("manual_stop")
                    break
                except Exception as e:
                    self.logger.log_error(f"Error in main loop: {e}", exc_info=True)
                    self._consecutive_loop_errors += 1
                    self._last_loop_error_ts = datetime.now(timezone.utc)
                    # Log error to DB
                    self._log_db_error(
                        level="ERROR",
                        message=str(e),
                        component="main_loop",
                        details={"consecutive_errors": self._consecutive_loop_errors},
                    )
                    time.sleep(10)  # Wait before retrying

        except Exception as e:
            self.logger.log_error(f"Fatal error: {e}", exc_info=True)
            self._end_db_session("crash")
            raise
        finally:
            self.logger.log_info("=" * 80)
            self.logger.log_info("Live Trading Runner Stopped")
            self.logger.log_info("=" * 80)
            # Ensure session is ended (in case not already done)
            self._end_db_session("normal")

    # ====================================================================
    # Live Status Output Methods
    # ====================================================================

    def _append_market_bar(self, *, bar_timestamp: datetime, latest_bar: dict) -> None:
        """Append current 1m bar to JSONL stream (best-effort, non-blocking)."""
        try:
            ts = pd.Timestamp(bar_timestamp).tz_convert("UTC").to_pydatetime()
            if self._last_market_bar_ts is not None and ts <= self._last_market_bar_ts:
                return
            self._last_market_bar_ts = ts

            base = Path(getattr(self.config, "state_dir", "state"))
            base.mkdir(parents=True, exist_ok=True)
            path = self._market_bars_file
            doc = {
                "ts": pd.Timestamp(ts).tz_convert("UTC").isoformat(),
                "symbol": str(self.symbol),
                "open": float(latest_bar.get("open", 0.0) or 0.0),
                "high": float(latest_bar.get("high", 0.0) or 0.0),
                "low": float(latest_bar.get("low", 0.0) or 0.0),
                "close": float(latest_bar.get("close", 0.0) or 0.0),
                "volume": float(latest_bar.get("volume", 0.0) or 0.0),
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        except Exception:
            return

    def _atomic_write_json(self, filepath: Path, data: dict) -> None:
        """Atomically write JSON to file (temp + rename)."""
        try:
            payload = self._sanitize_jsonable(data)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            temp_file = filepath.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                # IMPORTANT: browser JSON.parse cannot handle NaN/Infinity.
                json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
            temp_file.replace(filepath)
        except Exception:
            return

    @staticmethod
    def _sanitize_jsonable(obj: Any) -> Any:
        """
        Recursively sanitize objects to be strict-JSON compatible.

        - Replace NaN/Infinity with None
        - Convert numpy scalar via .item() when available
        """
        try:
            # numpy scalar -> python scalar
            if hasattr(obj, "item") and callable(getattr(obj, "item")):
                obj = obj.item()
        except Exception:
            pass

        if obj is None:
            return None
        if isinstance(obj, (str, int, bool)):
            return obj
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {str(k): BitgetLiveRunner._sanitize_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [BitgetLiveRunner._sanitize_jsonable(v) for v in obj]
        try:
            return str(obj)
        except Exception:
            return None

    def _build_live_status_dict(self, current_bar: dict, timestamp: datetime) -> dict:
        """Build live_status.json payload (matches dashboard schema)."""
        ts_iso = pd.Timestamp(timestamp).tz_convert("UTC").isoformat()
        price = float(current_bar.get("close", 0.0) or 0.0)
        portfolio_state = self._get_portfolio_state(current_price=price)

        # Uptime
        uptime_seconds = int((timestamp - self._start_time).total_seconds())

        equity = float(portfolio_state.get("equity", self.config.initial_cash) or self.config.initial_cash)
        cash = float(portfolio_state.get("cash", self.config.initial_cash) or self.config.initial_cash)
        long_holdings = float(portfolio_state.get("long_holdings", 0.0) or 0.0)
        short_holdings = float(portfolio_state.get("short_holdings", 0.0) or 0.0)
        net_position_btc = float(long_holdings) - float(short_holdings)
        unrealized_pnl = float(portfolio_state.get("unrealized_pnl", 0.0) or 0.0)

        # Cost basis (for % metrics & avg cost)
        if bool(self.dry_run):
            total_cost_basis = float(self._paper_total_cost_basis)
            total_short_entry_value = float(self._paper_total_short_entry_value)
        else:
            total_cost_basis = float(self._get_total_cost_basis_from_ledger())
            total_short_entry_value = 0.0
            for positions_by_level in self.algorithm.grid_manager.short_positions.values():
                for pos in positions_by_level:
                    try:
                        sz = float(pos.get("size", 0.0))
                        px = float(pos.get("sell_price", 0.0))
                    except Exception:
                        continue
                    if sz > 0 and px > 0:
                        total_short_entry_value += sz * px

        # Display realized PnL (dashboard definition): total_pnl - unrealized_pnl
        total_pnl = equity - float(self.config.initial_cash)
        realized_pnl = float(total_pnl) - float(unrealized_pnl)

        # Daily PnL (placeholder; can be upgraded later)
        daily_pnl = float(portfolio_state.get("daily_pnl", 0.0) or 0.0)
        daily_pnl_pct = (daily_pnl / float(self.config.initial_cash)) if float(self.config.initial_cash) > 0 else 0.0

        # Direction
        if abs(net_position_btc) < 1e-8:
            direction = "FLAT"
        elif net_position_btc > 0:
            direction = "LONG"
        else:
            direction = "SHORT"

        # Avg cost (prefer ledger, fallback to cost_basis/holdings)
        avg_cost = float(self._get_avg_cost_from_ledger() or 0.0)
        if avg_cost <= 0 and long_holdings > 0 and total_cost_basis > 0:
            avg_cost = float(total_cost_basis / long_holdings)

        # Percent metrics
        unrealized_pnl_pct = (unrealized_pnl / total_cost_basis) if total_cost_basis > 0 else 0.0
        distance_to_cost_pct = ((price - avg_cost) / avg_cost) if avg_cost > 0 else 0.0

        # Risk checks (match GridManager's capacity concept: equity * leverage)
        gm = self.algorithm.grid_manager
        risk_level = int(getattr(gm, "risk_level", 0) or 0)
        grid_enabled = bool(getattr(gm, "grid_enabled", True))
        shutdown_reason = getattr(gm, "grid_shutdown_reason", None)

        atr = float(getattr(gm, "current_atr", 0.0) or 0.0)
        max_risk_atr_mult = float(getattr(self.config, "max_risk_atr_mult", 3.0) or 3.0)
        price_depth_threshold = float(getattr(self.config, "support", 0.0) or 0.0) - max_risk_atr_mult * atr

        max_loss_pct = float(getattr(self.config, "max_risk_loss_pct", 0.30) or 0.30)
        # Profit buffer uses realized profits only (negative realized should not reduce safety margin)
        profit_buffer_ratio = float(getattr(self.config, "profit_buffer_ratio", 0.5) or 0.5)
        realized_for_buffer = max(0.0, float(getattr(gm, "realized_pnl", 0.0) or 0.0))
        profit_buffer = realized_for_buffer * profit_buffer_ratio if bool(getattr(self.config, "enable_profit_buffer", True)) else 0.0
        adjusted_loss_threshold = max(0.0, max_loss_pct - (profit_buffer / equity)) if equity > 0 else max_loss_pct

        unrealized_loss_pct = max(0.0, (-unrealized_pnl / equity) if equity > 0 and unrealized_pnl < 0 else 0.0)
        if unrealized_loss_pct >= adjusted_loss_threshold:
            unrealized_loss_status = "CRITICAL"
        elif unrealized_loss_pct >= adjusted_loss_threshold * 0.8:
            unrealized_loss_status = "WARN"
        else:
            unrealized_loss_status = "OK"

        leverage = float(getattr(self.config, "leverage", 1.0) or 1.0)
        max_capacity = equity * leverage if equity > 0 else 1.0
        inv_notional = abs(net_position_btc) * price
        inventory_risk_pct = (inv_notional / max_capacity) if max_capacity > 0 else 0.0
        inv_threshold = float(getattr(self.config, "max_risk_inventory_pct", 0.8) or 0.8)
        if inventory_risk_pct >= inv_threshold:
            inventory_status = "CRITICAL"
        elif inventory_risk_pct >= inv_threshold * 0.8:
            inventory_status = "WARN"
        else:
            inventory_status = "OK"

        price_depth_status = "OK" if price >= price_depth_threshold else "WARN"

        # Regime mapping (dashboard schema wants BULLISH/NEUTRAL/BEARISH)
        regime_raw = str(getattr(self.config, "regime", "NEUTRAL") or "NEUTRAL")
        if regime_raw.upper().startswith("BULL"):
            regime = "BULLISH"
        elif regime_raw.upper().startswith("BEAR"):
            regime = "BEARISH"
        else:
            regime = "NEUTRAL"

        # Orders: transform blotter events to dashboard schema
        orders = []
        for e in list(self._blotter_events[-100:])[::-1]:
            try:
                orders.append(
                    {
                        "id": e.get("id") or f"{e.get('ts')}:{e.get('side')}:{e.get('level')}",
                        "timestamp": e.get("ts"),
                        "direction": str(e.get("side", "")).lower(),
                        "level": int(e.get("level", 0) or 0),
                        "price": float(e.get("px", 0.0) or 0.0),
                        "size": float(e.get("qty", 0.0) or 0.0),
                        "notional": float(e.get("notional", 0.0) or 0.0),
                        "commission": float(e.get("fee_est", 0.0) or 0.0),
                        "slippage": 0.0,
                        "order_id": e.get("order_id"),
                        "execution_type": "DRY_RUN_FILL" if bool(self.dry_run) else "FILLED",
                        "matched_trade": None,
                        "factors": dict(self._last_factor_state or {}),
                    }
                )
            except Exception:
                continue

        # Active limit orders (planned grid orders currently enabled for placement)
        active_orders: list[dict] = []
        try:
            for o in (self._last_planned_limit_orders or [])[:400]:
                direction = str(o.get("direction", "")).lower()
                level_index = int(o.get("level_index", 0) or 0)
                leg = o.get("leg")
                client_oid = self._make_client_oid(direction, level_index, leg)
                active_orders.append(
                    {
                        "direction": direction,
                        "level": int(level_index) + 1,
                        "price": float(o.get("price", 0.0) or 0.0),
                        "size": float(o.get("quantity", 0.0) or 0.0),
                        "leg": (leg if leg is not None else "long"),
                        "client_order_id": client_oid,
                        "reason": o.get("reason"),
                        "ts": pd.Timestamp(self._last_planned_limit_orders_ts or timestamp).tz_convert("UTC").isoformat(),
                    }
                )
        except Exception:
            active_orders = []

        return {
            "ts": ts_iso,
            "mode": "dryrun" if bool(self.dry_run) else "live",
            "portfolio": {
                "equity": equity,
                "initial_cash": float(self.config.initial_cash),
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": float(total_pnl),
                "total_pnl_pct": (float(total_pnl) / float(self.config.initial_cash)) if float(self.config.initial_cash) > 0 else 0.0,
                "daily_pnl": daily_pnl,
                "daily_pnl_pct": daily_pnl_pct,
                "peak_equity_today": equity,  # TODO: day tracking (future)
                "peak_equity_today_time": ts_iso,
                "total_trades": int(len(self._blotter_events)),
                "open_positions_count": 1 if abs(net_position_btc) >= 1e-8 else 0,
            },
            "position": {
                "net_position_btc": net_position_btc,
                "direction": direction,
                "position_value_usd": abs(net_position_btc) * price,
                "avg_cost": avg_cost,
                "breakeven_price": avg_cost,  # TODO: include fees/funding in live
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": float(unrealized_pnl_pct),
                "distance_to_cost_pct": float(distance_to_cost_pct),
                "long_holdings": long_holdings,
                "short_holdings": short_holdings,
                "cost_basis": float(total_cost_basis),
                "short_entry_value": float(total_short_entry_value),
            },
            "market": {
                "symbol": str(self.symbol),
                "exchange": "Bitget",
                "close": price,
                "open": float(current_bar.get("open", price) or price),
                "high": float(current_bar.get("high", price) or price),
                "low": float(current_bar.get("low", price) or price),
                # Dashboard service will overwrite volume/change/high_24h/low_24h from market_bars_1m.jsonl
                "volume": float(current_bar.get("volume", 0.0) or 0.0),
                "change_24h": 0.0,
                "change_24h_pct": 0.0,
                "high_24h": price,
                "low_24h": price,
                "atr_14": atr,
                "spread": 0.0,
                "timestamp": ts_iso,
                "data_latency_ms": 0.0,
            },
            "risk": {
                "risk_level": risk_level,
                "grid_enabled": grid_enabled,
                "shutdown_reason": shutdown_reason,
                "checks": {
                    "price_depth": {
                        "status": price_depth_status,
                        "value": price,
                        "threshold": price_depth_threshold,
                    },
                    "unrealized_loss": {
                        "status": unrealized_loss_status,
                        "value_pct": unrealized_loss_pct,
                        "threshold": max_loss_pct,
                        "adjusted_threshold": adjusted_loss_threshold,
                    },
                    "inventory_risk": {
                        "status": inventory_status,
                        "value_pct": inventory_risk_pct,
                        "threshold": inv_threshold,
                    },
                },
                "last_check_time": ts_iso,
            },
            "strategy": {
                "name": f"TaoGrid {regime_raw}",
                "symbol": str(self.symbol),
                "exchange": "Bitget",
                "regime": regime,
                "buy_weight": float(getattr(gm, "regime_buy_ratio", 0.5) or 0.5),
                "sell_weight": float(getattr(gm, "regime_sell_ratio", 0.5) or 0.5),
                "support": float(getattr(self.config, "support", 0.0) or 0.0),
                "resistance": float(getattr(self.config, "resistance", 0.0) or 0.0),
                "range_usd": float(getattr(self.config, "resistance", 0.0) or 0.0) - float(getattr(self.config, "support", 0.0) or 0.0),
                "range_pct": ((float(getattr(self.config, "resistance", 0.0) or 0.0) - float(getattr(self.config, "support", 1.0) or 1.0)) / float(getattr(self.config, "support", 1.0) or 1.0)),
                "current_spacing_usd": 0.0,  # TODO: from grid spacing
                "current_spacing_pct": 0.0,
                "grid_levels_total": int(len(getattr(gm, "pending_limit_orders", []) or [])),
                # NOTE: buy_levels/sell_levels are numpy arrays; don't use `or []` (ambiguous truth value)
                "grid_levels_buy": int(len(getattr(gm, "buy_levels", None)) if getattr(gm, "buy_levels", None) is not None else 0),
                "grid_levels_sell": int(len(getattr(gm, "sell_levels", None)) if getattr(gm, "sell_levels", None) is not None else 0),
                "initial_cash": float(self.config.initial_cash),
                "leverage": leverage,
                "max_inventory_risk": inv_threshold,
                "max_unrealized_loss": max_loss_pct,
                "start_time": pd.Timestamp(self._start_time).tz_convert("UTC").isoformat(),
                "uptime_seconds": uptime_seconds,
            },
            "orders": orders,
            "active_orders": active_orders,
            "risk_log": [],
            "performance": {},
            "system": {
                "bot_status": "RUNNING",
                "last_heartbeat": ts_iso,
                "expected_bar_interval_seconds": 60,
                "actual_last_bar_seconds_ago": 0,
                "data_feed_status": "CONNECTED",
                "data_feed_latency_ms": 0,
                "data_feed_last_update": ts_iso,
                "exchange_api_status": "CONNECTED",
                "exchange_api_latency_ms": 0,
                "exchange_api_last_order": None,
                "last_bar_processing_time_ms": 0,
                "avg_bar_processing_time_ms": 0,
                "peak_bar_processing_time_ms": 0,
                "error_count_24h_critical": 0,
                "error_count_24h_warning": 0,
            },
        }

    def _update_live_status(self, current_bar: dict, timestamp: datetime) -> dict | None:
        """Conditionally update live_status.json based on frequency. Returns payload if written."""
        if not self.enable_live_status or self.live_status_file is None:
            return None

        self._live_status_update_counter += 1
        if self._live_status_update_counter % self.live_status_update_frequency != 0:
            return None

        status = self._build_live_status_dict(current_bar, timestamp)
        self._atomic_write_json(self.live_status_file, status)
        return status

    def _bot_id(self) -> str:
        return f"{str(self.symbol)}_{str(self.market_type)}"

    # ============================================================
    # V2 Schema: Session & Event Management
    # ============================================================

    def _create_db_session(self) -> None:
        """Create session record in DB after bootstrap."""
        if self._db_store is None:
            return
        try:
            config_dict = {}
            try:
                config_dict = {
                    "support": float(getattr(self.config, "support", 0)),
                    "resistance": float(getattr(self.config, "resistance", 0)),
                    "initial_cash": float(getattr(self.config, "initial_cash", 0)),
                    "leverage": float(getattr(self.config, "leverage", 1)),
                    "active_buy_levels": self.active_buy_levels,
                    "cooldown_active_buy_levels": self.cooldown_active_buy_levels,
                }
            except Exception:
                pass

            self._db_store.create_session(
                session_id=self._session_id,
                bot_id=self._bot_id(),
                symbol=self.symbol,
                mode="dryrun" if self.dry_run else "live",
                version=None,  # TODO: get git commit
                config_snapshot=config_dict,
                notes=f"market_type={self.market_type}",
            )
            # Update with bootstrap stats
            self._db_store.update_session_startup_stats(
                session_id=self._session_id,
                orders_cancelled=self._bootstrap_orders_cancelled,
                orders_placed=self._bootstrap_orders_placed,
                position_qty=self._bootstrap_position_qty,
            )
        except Exception:
            pass

    def _end_db_session(self, reason: str) -> None:
        """Mark session as ended in DB."""
        if self._db_store is None:
            return
        try:
            self._db_store.end_session(
                session_id=self._session_id,
                end_reason=reason,
            )
        except Exception:
            pass

    def _log_order_event(
        self,
        *,
        client_order_id: str,
        event_type: str,
        trigger: str,
        new_status: str,
        old_status: str | None = None,
        exchange_order_id: str | None = None,
        fill_qty: float | None = None,
        fill_price: float | None = None,
        fill_fee: float | None = None,
        trade_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log an order event to the database."""
        if self._db_store is None:
            return
        try:
            self._db_store.insert_order_event(
                session_id=self._session_id,
                client_order_id=client_order_id,
                event_type=event_type,
                trigger=trigger,
                new_status=new_status,
                old_status=old_status,
                exchange_order_id=exchange_order_id,
                fill_qty=fill_qty,
                fill_price=fill_price,
                fill_fee=fill_fee,
                trade_id=trade_id,
                details=details,
            )
        except Exception:
            pass

    def _log_db_error(
        self,
        *,
        level: str,
        message: str,
        component: str | None = None,
        error_code: str | None = None,
        order_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log an error to the database."""
        if self._db_store is None:
            return
        try:
            self._db_store.insert_error_log(
                bot_id=self._bot_id(),
                level=level,
                message=message,
                session_id=self._session_id,
                component=component,
                error_code=error_code,
                symbol=self.symbol,
                order_id=order_id,
                details=details,
            )
        except Exception:
            pass

    def _persist_status_to_db(self, *, status: dict, bar_timestamp: datetime) -> None:
        """
        Best-effort DB persistence. Never raises.

        Writes:
        - bot_state_current (jsonb snapshot)
        - bot_heartbeat (append-only)
        - active_limit_orders_current (replace per bar)
        - order_blotter (append-only; duplicates ignored)
        - exchange_open_orders_current / exchange_positions_current (live only; best-effort)
        """
        if self._db_store is None:
            return
        try:
            self._persist_status_to_db_core(status=status, bar_timestamp=bar_timestamp)
            # If DB recovered, try flushing backlog
            self._db_outbox_flush(max_events=50)
        except Exception:
            self._db_outbox_append(status=status, bar_timestamp=bar_timestamp)
            return

    def _persist_status_to_db_core(self, *, status: dict, bar_timestamp: datetime) -> None:
        """Core DB write. Raises on failure (caller handles buffering)."""
        if self._db_store is None:
            raise RuntimeError("db_store is None")

        now_ts = datetime.now(timezone.utc)
        bot_id = self._bot_id()
        mode = str(status.get("mode") or ("dryrun" if bool(self.dry_run) else "live"))

        # Data feed lag
        lag_seconds = None
        try:
            lag_seconds = float((now_ts - bar_timestamp).total_seconds())
        except Exception:
            lag_seconds = None

        data_feed_status = "CONNECTED"
        if lag_seconds is not None and lag_seconds > float(self.safety_data_stale_seconds or 90):
            data_feed_status = "STALE"

        exchange_api_status = "CONNECTED" if int(self._consecutive_loop_errors) == 0 else "DEGRADED"

        # Derive a single status label for heartbeat
        hb_status = "RUNNING"
        if data_feed_status == "STALE":
            hb_status = "DATA_FEED_STALE"
        elif exchange_api_status != "CONNECTED":
            hb_status = "EXCHANGE_API_DEGRADED"

        safe_status = self._sanitize_jsonable(status)

        # Skip DB writes if DB store is not available
        if self._db_store is None:
            return

        # Upsert current state snapshot
        self._db_store.upsert_bot_state_current(
            bot_id=bot_id,
            ts=now_ts,
            mode=mode,
            payload=safe_status,
        )

        # Insert heartbeat
        self._db_store.insert_heartbeat(
            bot_id=bot_id,
            ts=now_ts,
            mode=mode,
            last_bar_ts=bar_timestamp,
            lag_seconds=lag_seconds,
            status=hb_status,
            data_feed_status=data_feed_status,
            exchange_api_status=exchange_api_status,
            exchange_error_count=int(self._consecutive_loop_errors),
            payload={
                "symbol": str(self.symbol),
                "market_type": str(self.market_type),
            },
        )

        # Active limit orders (planned)
        active = list(safe_status.get("active_orders") or [])
        self._db_store.replace_active_limit_orders_current(bot_id=bot_id, ts=now_ts, orders=active)

        # Blotter orders (filled)
        blotter_rows: list[dict] = []
        for o in list(safe_status.get("orders") or []):
            try:
                blotter_rows.append(
                    {
                        "timestamp": o.get("timestamp"),
                        "direction": o.get("direction"),
                        "level": o.get("level"),
                        "price": o.get("price"),
                        "size": o.get("size"),
                        "notional": o.get("notional"),
                        "commission": o.get("commission"),
                        "leg": o.get("leg"),
                        "client_order_id": o.get("client_order_id") or o.get("id"),
                        "exchange_order_id": o.get("exchange_order_id"),
                        "trade_id": o.get("trade_id"),
                    }
                )
            except Exception:
                continue
        if blotter_rows:
            self._db_store.insert_order_blotter(bot_id=bot_id, rows=blotter_rows)

        # Live: snapshot exchange open orders & positions
        if not bool(self.dry_run):
            open_orders = self.execution_engine.get_open_orders(self.symbol)
            self._db_store.upsert_exchange_open_orders_current(bot_id=bot_id, ts=now_ts, rows=open_orders or [])
            positions = self.execution_engine.get_positions(self.symbol)
            self._db_store.upsert_exchange_positions_current(bot_id=bot_id, ts=now_ts, rows=positions or [])

    def _db_outbox_append(self, *, status: dict, bar_timestamp: datetime) -> None:
        """Append a buffered payload to outbox when DB is down (best-effort)."""
        try:
            base = Path(getattr(self.config, "state_dir", "state"))
            base.mkdir(parents=True, exist_ok=True)
            path = self._db_outbox_file
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "bar_timestamp": pd.Timestamp(bar_timestamp).tz_convert("UTC").isoformat(),
                "status": self._sanitize_jsonable(status),
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            return

    def _db_outbox_flush(self, *, max_events: int = 50) -> None:
        """Flush buffered outbox events back to DB, removing successes from the file."""
        if self._db_store is None:
            return
        try:
            path = self._db_outbox_file
            if not path.exists():
                return
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not lines:
                return
            remain: list[str] = []
            processed = 0
            for i, raw_ln in enumerate(lines):
                if processed >= int(max_events):
                    remain.append(raw_ln)
                    continue
                ln = raw_ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    status = rec.get("status")
                    bar_ts = rec.get("bar_timestamp")
                    bar_dt = pd.Timestamp(bar_ts).to_pydatetime() if bar_ts else datetime.now(timezone.utc)
                    if isinstance(status, dict):
                        self._persist_status_to_db_core(status=status, bar_timestamp=bar_dt)
                        processed += 1
                    else:
                        processed += 1
                except Exception:
                    # Stop on first failure to avoid dropping events
                    remain.append(raw_ln)
                    remain.extend(lines[i + 1 :])
                    break

            tmp = path.with_suffix(".jsonl.tmp")
            tmp.write_text("\n".join(remain) + ("\n" if remain else ""), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            return
