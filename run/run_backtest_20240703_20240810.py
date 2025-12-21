"""
TaoGrid Backtest - 2024.07.03 to 2024.08.10

Parameters:
- Period: 2024-07-03 to 2024-08-10
- Support: 56,000
- Resistance: 72,000
- Timeframe: 1m
- Regime: NEUTRAL_RANGE (default, can be adjusted)

Usage:
    python run/run_backtest_20240703_20240810.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def _run(cfg: TaoGridLeanConfig, data, out: Path, title: str) -> dict:
    """Run a single backtest configuration."""
    print("=" * 80)
    print(title)
    print("=" * 80)
    runner = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2024, 7, 3, tzinfo=timezone.utc),
        end_date=datetime(2024, 8, 10, tzinfo=timezone.utc),
        data=data,
        verbose=True,
        progress_every=5000,
        output_dir=out,
    )
    res = runner.run()
    runner.print_summary(res)
    runner.save_results(res, out)
    return res


def _row(name: str, m: dict) -> str:
    """Format a metrics row for comparison."""
    return (
        f"{name:26s}  "
        f"ret={m['total_return']:+7.2%}  "
        f"maxDD={m['max_drawdown']:+7.2%}  "
        f"sharpe={m['sharpe_ratio']:6.2f}  "
        f"calmar={m.get('calmar_ratio', 0.0):6.2f}  "
        f"ulcer={m.get('ulcer_index', 0.0):6.2f}  "
        f"trades={int(m.get('total_trades', 0)):5d}"
    )


def main() -> None:
    """Run backtest for 2024-07-03 to 2024-08-10 with S=56K, R=72K."""
    # Load data ONCE
    dm = DataManager()
    start = datetime(2024, 7, 3, tzinfo=timezone.utc)
    end = datetime(2024, 8, 10, tzinfo=timezone.utc)

    print("=" * 80)
    print("TaoGrid Backtest: 2024-07-03 to 2024-08-10")
    print("=" * 80)
    print(f"Support: $56,000")
    print(f"Resistance: $72,000")
    print(f"Range: $16,000 ({16000/64000*100:.1f}%)")
    print("=" * 80)
    print("Loading data...")

    data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=start,
        end=end,
        source="okx",
    )
    print(f"  Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    print()

    # Base configuration
    base = TaoGridLeanConfig(
        name="TaoGrid 20240703-20240810",
        description="S=56K, R=72K",
        support=56000.0,
        resistance=72000.0,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        leverage=5.0,
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        # Risk factors
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=True,
        enable_funding_factor=True,
        enable_vol_regime_factor=True,
        enable_mm_risk_zone=True,
        max_risk_inventory_pct=0.80,
        max_risk_loss_pct=0.30,
        # P0 fixes
        inventory_use_equity_floor=True,
        enable_regime_inventory_scaling=True,
        inventory_regime_gamma=1.2,
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
        enable_console_log=False,
    )

    # Run three regimes for comparison
    cfg_neutral = replace(base, regime="NEUTRAL_RANGE", enable_short_in_bearish=False)
    cfg_bullish = replace(base, regime="BULLISH_RANGE", enable_short_in_bearish=False)
    cfg_bearish = replace(base, regime="BEARISH_RANGE", enable_short_in_bearish=True)

    r_neu = _run(
        cfg_neutral,
        data,
        Path("run/results_neutral_20240703_20240810"),
        "NEUTRAL_RANGE"
    )

    r_bul = _run(
        cfg_bullish,
        data,
        Path("run/results_bullish_20240703_20240810"),
        "BULLISH_RANGE"
    )

    r_bear = _run(
        cfg_bearish,
        data,
        Path("run/results_bearish_20240703_20240810"),
        "BEARISH_RANGE (with short overlay)"
    )

    # Print comparison
    m_neu = r_neu["metrics"]
    m_bul = r_bul["metrics"]
    m_bear = r_bear["metrics"]

    print()
    print("=" * 80)
    print("Results Comparison (2024-07-03 to 2024-08-10)")
    print("=" * 80)
    print(_row("NEUTRAL_RANGE", m_neu))
    print(_row("BULLISH_RANGE", m_bul))
    print(_row("BEARISH_RANGE", m_bear))
    print("=" * 80)


if __name__ == "__main__":
    main()
