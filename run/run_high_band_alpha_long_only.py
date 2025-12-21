"""
实验：long-only 下“高位震荡额外收益”能否超过 NEUTRAL？

做法：
- 仍然 long-only，不开空
- 启用 mid shift（仅在空仓时重心上移/下移），让网格围绕当前震荡区域，提升成交/周转

窗口：2025-01-19 ~ 2025-02-24
S/R：90k / 108k
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def main() -> None:
    base = TaoGridLeanConfig(
        name="NEUTRAL long-only + mid shift (high-band alpha)",
        description="Try to harvest extra turnover in high-band oscillation without shorting",
        support=90000.0,
        resistance=108000.0,
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
        # 风控：全开
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=True,
        enable_funding_factor=True,
        enable_vol_regime_factor=True,
        enable_mm_risk_zone=True,
        max_risk_inventory_pct=0.80,
        max_risk_loss_pct=0.30,
        # P0：保持开启
        inventory_use_equity_floor=True,
        enable_regime_inventory_scaling=True,
        inventory_regime_gamma=1.2,
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
        # Mid shift（核心实验开关）
        enable_mid_shift=True,
        mid_shift_threshold=300,  # every 300 bars (~5h) at most
        mid_shift_range_pos_trigger=0.15,
        mid_shift_flat_holdings_btc=0.0005,
        enable_console_log=False,
    )

    runner = SimpleLeanRunner(
        config=base,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 1, 19, tzinfo=timezone.utc),
        end_date=datetime(2025, 2, 24, tzinfo=timezone.utc),
        verbose=True,
        progress_every=5000,
        output_dir=Path("run/results_neutral_midshift_20250119_20250224"),
    )
    results = runner.run()
    runner.print_summary(results)
    runner.save_results(results, runner.output_dir)


if __name__ == "__main__":
    main()

