"""Stress window analysis for BASE vs POLICY."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig
from data import DataManager

sd = datetime(2025, 9, 26, tzinfo=timezone.utc)
ed = datetime(2025, 10, 26, tzinfo=timezone.utc)

base_config = TaoGridLeanConfig(
    name="BASE",
    description="BASE",
    support=107000.0,
    resistance=123000.0,
    regime="NEUTRAL_RANGE",
    grid_layers_buy=40,
    grid_layers_sell=40,
    weight_k=0.0,
    spacing_multiplier=1.0,
    min_return=0.0012,
    maker_fee=0.0002,
    inventory_skew_k=0.5,
    inventory_capacity_threshold_pct=1.0,
    enable_mr_trend_factor=False,
    enable_breakout_risk_factor=True,
    breakout_band_atr_mult=1.0,
    breakout_band_pct=0.008,
    breakout_trend_weight=0.7,
    breakout_buy_k=2.0,
    breakout_buy_floor=0.5,
    breakout_block_threshold=0.9,
    enable_range_pos_asymmetry_v2=True,
    range_top_band_start=0.45,
    range_buy_k=0.2,
    range_buy_floor=0.2,
    range_sell_k=1.5,
    range_sell_cap=1.5,
    risk_budget_pct=1.0,
    enable_throttling=True,
    initial_cash=100000.0,
    leverage=50.0,
    enable_mm_risk_zone=False,
    enable_console_log=False,
)

policy_config = TaoGridLeanConfig(**{**base_config.__dict__, "name": "POLICY", "description": "POLICY"})


def analyze_stress_window(tag, config, runner_kwargs):
    """Analyze stress window from peak to trough."""
    print(f"\n{'='*80}")
    print(f"=== {tag} STRESS WINDOW ANALYSIS ===")
    print(f"{'='*80}\n")
    
    res = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=sd,
        end_date=ed,
        verbose=False,
        progress_every=999999,
        collect_equity_detail=True,
        **runner_kwargs,
    ).run()
    
    eq = res["equity_curve"].copy()
    eq["timestamp"] = pd.to_datetime(eq["timestamp"])
    eq = eq.sort_values("timestamp").reset_index(drop=True)
    eq["peak"] = eq["equity"].cummax()
    eq["dd"] = eq["equity"] / eq["peak"] - 1.0
    
    trough_i = int(eq["dd"].idxmin())
    trough_ts = eq.loc[trough_i, "timestamp"]
    dd_min = float(eq.loc[trough_i, "dd"])
    
    peak_i = int(eq.loc[:trough_i, "equity"].idxmax())
    peak_ts = eq.loc[peak_i, "timestamp"]
    peak_val = float(eq.loc[peak_i, "equity"])
    
    # Recovery point
    after = eq.loc[trough_i:]
    rec_hit = after.index[after["equity"] >= peak_val]
    rec_ts = eq.loc[rec_hit[0], "timestamp"] if len(rec_hit) > 0 else None
    
    print(f"Peak: {peak_ts} (equity=${peak_val:,.2f})")
    print(f"Trough: {trough_ts} (equity=${eq.loc[trough_i,'equity']:,.2f}, dd={dd_min*100:.2f}%)")
    if rec_ts:
        print(f"Recovery: {rec_ts}")
    print(f"Window duration: {(trough_ts - peak_ts).total_seconds() / 3600:.1f} hours")
    print()
    
    # Orders in window
    o = res["orders"].copy()
    o["timestamp"] = pd.to_datetime(o["timestamp"])
    oc = o.groupby("timestamp").size()
    bc = o[o.direction == "buy"].groupby("timestamp").size()
    sc = o[o.direction == "sell"].groupby("timestamp").size()
    
    # Price data
    dm = DataManager()
    price_data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=peak_ts,
        end=trough_ts + pd.Timedelta(minutes=5),
        source="okx",
    )
    price_data.index = pd.to_datetime(price_data.index)
    
    # Window dataframe
    w = eq[(eq["timestamp"] >= peak_ts) & (eq["timestamp"] <= trough_ts + pd.Timedelta(minutes=5))][
        ["timestamp", "equity", "holdings", "dd"]
    ].copy()
    w = w.merge(
        price_data[["open", "high", "low", "close"]],
        left_on="timestamp",
        right_index=True,
        how="left",
    )
    w["range_pct"] = ((w["high"] - w["low"]) / w["close"] * 100).round(2)
    w["orders"] = w["timestamp"].map(oc).fillna(0).astype(int)
    w["buys"] = w["timestamp"].map(bc).fillna(0).astype(int)
    w["sells"] = w["timestamp"].map(sc).fillna(0).astype(int)
    w["eq"] = w["equity"].round(2)
    w["h"] = w["holdings"].round(4)
    w["dd%"] = (w["dd"] * 100).round(2)
    w["price"] = w["close"].round(2)
    
    print(f"Window stats:")
    print(f"  Total orders: {int(w['orders'].sum())}")
    print(f"  Minutes with >=2 orders: {int((w['orders'] >= 2).sum())}")
    print(f"  Minutes with >=2 buys: {int((w['buys'] >= 2).sum())}")
    print(f"  Minutes with >=2 sells: {int((w['sells'] >= 2).sum())}")
    print(f"  Max holdings: {float(w['h'].max()):.4f} BTC")
    print(f"  Max range_pct: {float(w['range_pct'].max()):.2f}%")
    print()
    
    print("Minute-by-minute detail (first 30 minutes):")
    print(w[["timestamp", "price", "range_pct", "eq", "h", "dd%", "orders", "buys", "sells"]].head(30).to_string(index=False))
    if len(w) > 30:
        print(f"\n... ({len(w) - 30} more minutes)")
    print()


if __name__ == "__main__":
    analyze_stress_window(
        "BASE",
        base_config,
        {"max_fills_per_bar": 1},
    )
    
    analyze_stress_window(
        "POLICY",
        policy_config,
        {
            "max_fills_per_bar": 6,
            "active_buy_levels": 6,
            "cooldown_minutes": 2,
            "abnormal_buy_fills_trigger": 2,
            "abnormal_total_fills_trigger": 3,
            "abnormal_buy_notional_frac_equity": 0.03,
            "abnormal_range_mult_spacing": 4.0,
            "cooldown_active_buy_levels": 2,
        },
    )
