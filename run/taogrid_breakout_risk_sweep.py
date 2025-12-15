"""
Aggressive parameter sweep for breakout risk factor.

Goal:
  Maximize traditional annualized Sharpe (daily returns) under risk constraints.

We sweep (aggressive ranges):
  - breakout_band_atr_mult
  - breakout_band_pct
  - breakout_buy_k
  - breakout_buy_floor
  - breakout_block_threshold

We use random sampling to avoid a very large full grid.

Outputs:
  run/results_lean_taogrid_breakout_risk_sweep/summary.csv
  run/results_lean_taogrid_breakout_risk_sweep/trials/*.json  (per-trial metrics + params)
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
    # Aggressive search space
    band_atr_mult_choices = [0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    band_pct_choices = [0.0008, 0.0010, 0.0015, 0.0020, 0.0030, 0.0050, 0.0080]
    buy_k_choices = [0.0, 0.2, 0.4, 0.6, 0.9, 1.2, 1.6, 2.0]
    buy_floor_choices = [0.05, 0.10, 0.20, 0.35, 0.50, 0.70, 0.90]
    block_threshold_choices = [0.70, 0.80, 0.85, 0.90, 0.95, 0.98, 0.995]

    # Random sample size (aggressive but bounded)
    trials = 140
    seed = 20251215

    out_root = Path("run/results_lean_taogrid_breakout_risk_sweep")
    trial_dir = out_root / "trials"
    trial_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    base = TaoGridLeanConfig(
        name="TaoGrid Breakout Risk Sweep",
        description="Aggressive sweep breakout risk params for Sharpe",
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
        # keep MR+Trend off so we isolate breakout factor effect
        enable_mr_trend_factor=False,
        enable_breakout_risk_factor=True,
    )

    rows: list[dict] = []
    seen: set[tuple] = set()

    for t in range(trials):
        params = (
            random.choice(band_atr_mult_choices),
            random.choice(band_pct_choices),
            random.choice(buy_k_choices),
            random.choice(buy_floor_choices),
            random.choice(block_threshold_choices),
        )
        if params in seen:
            continue
        seen.add(params)

        band_atr_mult, band_pct, buy_k, buy_floor, block_th = params

        cfg = replace(
            base,
            breakout_band_atr_mult=float(band_atr_mult),
            breakout_band_pct=float(band_pct),
            breakout_buy_k=float(buy_k),
            breakout_buy_floor=float(buy_floor),
            breakout_block_threshold=float(block_th),
            name=f"BR Sweep {t}",
        )

        out_dir = out_root / f"trial_{t:03d}"
        metrics = _run(cfg, out_dir)

        record = {
            "trial": t,
            "breakout_band_atr_mult": band_atr_mult,
            "breakout_band_pct": band_pct,
            "breakout_buy_k": buy_k,
            "breakout_buy_floor": buy_floor,
            "breakout_block_threshold": block_th,
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
    if df.empty:
        raise RuntimeError("No trials executed (unexpected).")

    # Filter by MaxDD <= 20% (max_drawdown is negative)
    df_ok = df[df["max_drawdown"] >= -0.20].copy()
    df_ok = df_ok.sort_values(by=["sharpe_ratio", "total_return"], ascending=False)

    df_ok.to_csv(out_root / "summary.csv", index=False)

    print("Top 10 (MaxDD<=20%):")
    print(df_ok.head(10).to_string(index=False))
    print(f"Saved: {out_root / 'summary.csv'}")


if __name__ == "__main__":
    main()


