"""
Dry-run shadow test for Bitget live runner logic (no real orders).

Goal:
- Validate that factor computation + sizing + pending order set evolution is stable
  and aligned with backtest semantics *without* sending orders to Bitget.

How it works:
- Loads historical bars from OKX swap cache (fast, reproducible).
- Runs TaoGridLeanAlgorithm in backtest mode (simulated fills by OHLC touch) to build a reference ledger.
- Runs TaoGridLeanAlgorithm in "live_mode" with a mocked exchange:
  - We keep a set of resting orders (pending_limit_orders) and simulate fills using the SAME OHLC touch rule
    (which is exactly what backtest does).
  - This validates the new live runner style state machine: resting orders -> fills -> on_order_filled -> re-place.

This script does NOT require Bitget credentials.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager
from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def _simulate_shadow(
    cfg: TaoGridLeanConfig,
    data: pd.DataFrame,
) -> dict:
    """
    Shadow simulation:
    - Use algorithm in live_mode (so it won't self-trigger orders).
    - We simulate exchange fills by checking OHLC touch against the algorithm's pending_limit_orders.
    """
    algo = TaoGridLeanAlgorithm(cfg)
    algo.initialize(
        symbol="BTCUSDT",
        start_date=data.index[0].to_pydatetime(),
        end_date=data.index[-1].to_pydatetime(),
        historical_data=data.head(100),
    )

    # Pre-compute factor columns (same intent as SimpleLeanRunner)
    bars = data.copy()
    try:
        from analytics.indicators.regime_factors import (
            calculate_ema,
            calculate_ema_slope,
            rolling_zscore,
            trend_score_from_slope,
        )

        ema = calculate_ema(bars["close"], period=int(cfg.trend_ema_period))
        slope = calculate_ema_slope(ema, lookback=int(cfg.trend_slope_lookback))
        bars["trend_score"] = trend_score_from_slope(slope, slope_ref=float(cfg.trend_slope_ref))
        bars["mr_z"] = rolling_zscore(bars["close"], window=int(cfg.mr_z_lookback))
    except Exception:
        bars["trend_score"] = float("nan")
        bars["mr_z"] = float("nan")

    try:
        from analytics.indicators.volatility import calculate_atr
        from analytics.indicators.breakout_risk import compute_breakout_risk
        from analytics.indicators.range_factors import compute_range_position
        from analytics.indicators.vol_regime import calculate_atr_pct, rolling_quantile_score

        atr = calculate_atr(bars["high"], bars["low"], bars["close"], period=int(cfg.atr_period))
        br = compute_breakout_risk(
            close=bars["close"],
            atr=atr,
            support=float(cfg.support),
            resistance=float(cfg.resistance),
            trend_score=bars.get("trend_score"),
            band_atr_mult=float(getattr(cfg, "breakout_band_atr_mult", 1.5)),
            band_pct=float(getattr(cfg, "breakout_band_pct", 0.003)),
            trend_weight=float(getattr(cfg, "breakout_trend_weight", 0.7)),
        )
        bars["breakout_risk_down"] = br["breakout_risk_down"]
        bars["breakout_risk_up"] = br["breakout_risk_up"]
        bars["range_pos"] = compute_range_position(
            close=bars["close"],
            support=float(cfg.support),
            resistance=float(cfg.resistance),
        )
        atr_pct = calculate_atr_pct(atr=atr, close=bars["close"])
        bars["vol_score"] = rolling_quantile_score(
            series=atr_pct,
            lookback=int(getattr(cfg, "vol_lookback", 1440)),
            low_q=float(getattr(cfg, "vol_low_q", 0.20)),
            high_q=float(getattr(cfg, "vol_high_q", 0.80)),
        )
    except Exception:
        bars["breakout_risk_down"] = 0.0
        bars["breakout_risk_up"] = 0.0
        bars["range_pos"] = 0.5
        bars["vol_score"] = 0.0

    bars["funding_rate"] = 0.0
    bars["minutes_to_funding"] = float("nan")

    cash = float(cfg.initial_cash)
    holdings = 0.0
    realized = 0.0
    total_cost_basis = 0.0
    commission_rate = float(cfg.maker_fee)

    def equity(px: float) -> float:
        return cash + holdings * px

    for i, (ts, row) in enumerate(bars.iterrows()):
        algo._current_bar_index = i

        # bar factors are already present in data when coming from SimpleLeanRunner.load_data pipeline,
        # but here we will keep it minimal (no factors) since this script is about order state machine.
        bar_data = {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "trend_score": float(row.get("trend_score", float("nan"))),
            "mr_z": float(row.get("mr_z", float("nan"))),
            "breakout_risk_down": float(row.get("breakout_risk_down", 0.0)),
            "breakout_risk_up": float(row.get("breakout_risk_up", 0.0)),
            "range_pos": float(row.get("range_pos", 0.5)),
            "vol_score": float(row.get("vol_score", 0.0)),
            "funding_rate": float(row.get("funding_rate", 0.0)),
            "minutes_to_funding": row.get("minutes_to_funding"),
        }
        ps = {
            "equity": equity(float(row["close"])),
            "cash": cash,
            "holdings": holdings,
            "long_holdings": holdings,
            "short_holdings": 0.0,
            "unrealized_pnl": holdings * float(row["close"]) - float(total_cost_basis),
            "daily_pnl": 0.0,
        }

        # Risk checks / special orders (market)
        special = algo.on_data(ts.to_pydatetime(), bar_data, ps, live_mode=True)
        if special is not None:
            # Execute at close for shadow
            px = float(row["close"])
            if special["direction"] == "sell":
                qty = min(holdings, float(special["quantity"]))
                cash += qty * px
                holdings -= qty
                # Reduce cost basis by matching ledger (best-effort)
                match = algo.grid_manager.match_sell_order(int(special.get("level", 0)), float(qty))
                if match is not None:
                    _, buy_price, msz = match
                    total_cost_basis -= float(msz) * float(buy_price)
            elif special["direction"] == "buy":
                qty = float(special["quantity"])
                cash -= qty * px
                holdings += qty
                total_cost_basis += qty * px
            special_fill = dict(special)
            special_fill["price"] = px
            algo.on_order_filled(special_fill)

        # IMPORTANT: honor risk shutdown state like the real runner
        if not bool(algo.grid_manager.grid_enabled):
            continue

        # Simulate exchange fills for resting limit orders using OHLC touch rule
        # Simulate at most 1 fill per bar (matches SimpleLeanRunner default max_fills_per_bar=1)
        triggered = algo.grid_manager.check_limit_order_triggers(
            current_price=float(row["close"]),
            prev_price=None,
            bar_high=float(row["high"]),
            bar_low=float(row["low"]),
            bar_index=i,
            range_pos=float(row.get("range_pos", 0.5)),
        )
        if triggered is None:
            continue

        size, throttle = algo.grid_manager.calculate_order_size(
            direction=str(triggered["direction"]),
            level_index=int(triggered["level_index"]),
            level_price=float(triggered["price"]),
            equity=equity(float(row["close"])),
            daily_pnl=0.0,
            risk_budget=algo.risk_budget,
            holdings_btc=float(holdings),
            order_leg=triggered.get("leg"),
            current_price=float(row["close"]),
            mr_z=float(row.get("mr_z", float("nan"))),
            trend_score=float(row.get("trend_score", float("nan"))),
            breakout_risk_down=float(row.get("breakout_risk_down", 0.0)),
            breakout_risk_up=float(row.get("breakout_risk_up", 0.0)),
            range_pos=float(row.get("range_pos", 0.5)),
            funding_rate=float(row.get("funding_rate", 0.0)),
            minutes_to_funding=row.get("minutes_to_funding"),
            vol_score=float(row.get("vol_score", 0.0)),
        )
        if float(size) <= 0:
            triggered["triggered"] = False
            triggered["last_checked_bar"] = None
            continue

        # Match SimpleLeanRunner fill price model:
        # - Buy: if bar opens below limit, fill at open; else at limit
        # - Sell: if bar opens above limit, fill at open; else at limit
        bar_open = float(row["open"])
        limit_px = float(triggered["price"])
        direction = str(triggered["direction"])
        if direction == "buy":
            execution_price = min(limit_px, bar_open)
        else:
            execution_price = max(limit_px, bar_open)

        fill = {
            "direction": direction,
            "price": float(execution_price),
            "quantity": float(size),
            "level": int(triggered["level_index"]),
            "timestamp": ts.to_pydatetime(),
            "leg": triggered.get("leg"),
        }

        if fill["direction"] == "buy":
            # Leverage / margin constraint (same as SimpleLeanRunner long-only)
            mkt_px = float(row["close"])
            eq = cash + holdings * mkt_px
            max_notional = eq * float(cfg.leverage)
            new_gross_notional = (holdings + float(fill["quantity"])) * mkt_px
            if not (eq > 0 and new_gross_notional <= max_notional):
                # reject and release trigger for next bar
                algo.grid_manager.reset_triggered_orders()
                continue

            notional = float(fill["quantity"]) * float(fill["price"])
            commission = notional * commission_rate
            cash -= notional + commission
            holdings += float(fill["quantity"])
            total_cost_basis += notional
        else:
            if float(fill["quantity"]) > float(holdings) + 1e-12:
                algo.grid_manager.reset_triggered_orders()
                continue
            qty = float(fill["quantity"])
            notional = qty * float(fill["price"])
            commission = notional * commission_rate
            cash += notional - commission
            holdings -= qty
            fill["quantity"] = qty
            match = algo.grid_manager.match_sell_order(int(fill["level"]), float(fill["quantity"]))
            if match is not None:
                _, buy_price, msz = match
                total_cost_basis -= float(msz) * float(buy_price)
                pnl = (float(fill["price"]) - float(buy_price)) * float(msz)
                realized += pnl
                algo.grid_manager.update_realized_pnl(float(pnl))

        algo.on_order_filled(fill)

    return {
        "final_equity": equity(float(data["close"].iloc[-1])),
        "cash": cash,
        "holdings": holdings,
        "realized_pnl": realized,
        "total_cost_basis": total_cost_basis,
        "orders": len(algo.filled_orders),
    }


def main() -> None:
    START = datetime(2024, 7, 3, tzinfo=timezone.utc)
    END_EXCL = datetime(2024, 7, 10, tzinfo=timezone.utc)  # short smoke window

    cfg = TaoGridLeanConfig(
        name="shadow_dryrun",
        support=56_000.0,
        resistance=70_000.0,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,
        spacing_multiplier=1.0,
        leverage=5.0,
        risk_budget_pct=1.0,
        enable_console_log=False,
    )

    dm = DataManager()
    data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=START,
        end=END_EXCL,
        source="okx_swap",
        use_cache=True,
    )

    # Reference: existing backtest runner
    ref = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=START,
        end_date=END_EXCL,
        data=data,
        verbose=False,
        progress_every=999999,
        output_dir=Path("run/results_shadow_ref"),
    ).run()

    shadow = _simulate_shadow(cfg, data)

    print("=" * 80)
    print("Shadow dry-run check (smoke)")
    print("=" * 80)
    print(f"REF  : final_equity={ref['metrics']['final_equity']:.2f}, orders={len(ref.get('orders', []))}")
    print(f"SHADO: final_equity={shadow['final_equity']:.2f}, orders={shadow['orders']}")
    print("=" * 80)


if __name__ == "__main__":
    main()

