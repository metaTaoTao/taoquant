"""
Aggressive sweep for range position asymmetry v2 (top-band only).

Note:
  In current grid construction, executed sell levels tend to cluster near the mid-range,
  so we include lower top-band starts (e.g., 0.45+) to make the factor actually active.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig  # noqa: E402
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner  # noqa: E402


def _run(cfg: TaoGridLeanConfig, out_dir: Path) -> dict:
    runner = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 7, 10, tzinfo=timezone.utc),
        end_date=datetime(2025, 8, 10, tzinfo=timezone.utc),
        output_dir=out_dir,
        verbose=False,
        progress_every=10000,
    )
    results = runner.run()
    runner.save_results(results, out_dir)
    return results["metrics"]


def main() -> None:
    # Aggressive (and "active") ranges
    top_start_choices = [0.45, 0.48, 0.50, 0.52, 0.55, 0.60, 0.65, 0.70]
    buy_k_choices = [0.0, 0.2, 0.5, 0.8, 1.2, 1.6, 2.0, 3.0]
    buy_floor_choices = [0.2, 0.3, 0.4, 0.5, 0.7, 0.9]
    sell_k_choices = [0.0, 0.3, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0]
    sell_cap_choices = [1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0]

    trials = 140
    seed = 20251215 + 17

    out_root = Path("run/results_lean_taogrid_range_pos_v2_sweep")
    trial_dir = out_root / "trials"
    trial_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    base = TaoGridLeanConfig(
        name="TaoGrid RangePos v2 Sweep",
        description="Aggressive sweep range_pos v2 params for Sharpe",
        support=111000.0,
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
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=50.0,
        sharpe_annualization_days=365,
        enable_mr_trend_factor=False,
        # Breakout factor ON (winner params)
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,
        enable_range_pos_asymmetry_v2=True,
    )

    rows: list[dict] = []
    seen: set[tuple] = set()

    for t in range(trials):
        params = (
            random.choice(top_start_choices),
            random.choice(buy_k_choices),
            random.choice(buy_floor_choices),
            random.choice(sell_k_choices),
            random.choice(sell_cap_choices),
        )
        if params in seen:
            continue
        seen.add(params)

        top_start, buy_k, buy_floor, sell_k, sell_cap = params

        # Ensure floor doesn't exceed 1.0
        cfg = replace(
            base,
            range_top_band_start=float(top_start),
            range_buy_k=float(buy_k),
            range_buy_floor=float(buy_floor),
            range_sell_k=float(sell_k),
            range_sell_cap=float(sell_cap),
            name=f"RPv2 Sweep {t}",
        )

        out_dir = out_root / f"trial_{t:03d}"
        metrics = _run(cfg, out_dir)

        record = {
            "trial": t,
            "range_top_band_start": top_start,
            "range_buy_k": buy_k,
            "range_buy_floor": buy_floor,
            "range_sell_k": sell_k,
            "range_sell_cap": sell_cap,
            "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
            "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
            "total_return": float(metrics.get("total_return", 0.0)),
            "total_trades": float(metrics.get("total_trades", 0.0)),
            "avg_holding_period_hours": float(metrics.get("avg_holding_period_hours", 0.0)),
            "output_dir": str(out_dir),
        }
        rows.append(record)
        (trial_dir / f"trial_{t:03d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    df = pd.DataFrame(rows)
    df_ok = df[df["max_drawdown"] >= -0.20].copy()
    df_ok = df_ok.sort_values(by=["sharpe_ratio", "total_return"], ascending=False)
    df_ok.to_csv(out_root / "summary.csv", index=False)

    print("Top 10 (MaxDD<=20%):")
    print(df_ok.head(10).to_string(index=False))
    print(f"Saved: {out_root / 'summary.csv'}")


if __name__ == "__main__":
    main()


