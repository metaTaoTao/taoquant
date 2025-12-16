"""
TaoGrid 压力测试 v2 - 2025-09-26 至 2025-10-26（增强诊断版本）

调整：
1. 添加详细的未实现亏损诊断日志
2. 使用更宽松的风控阈值（用于压力测试）
3. 或者先禁用 MM Risk Zone，观察基本交易逻辑

用法:
    python run/taogrid_stress_test_2025_09_26_v2.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def main():
    """运行压力测试回测 - 增强诊断版"""
    
    # 配置：先使用更宽松的风控阈值，观察基本行为
    config = TaoGridLeanConfig(
        name="TaoGrid Stress Test v2 (Enhanced Diagnostics)",
        description="压力测试 v2：增强诊断，宽松风控阈值",
        
        # ========== S/R Levels ==========
        support=107_000.0,
        resistance=123_000.0,
        regime="NEUTRAL_RANGE",
        
        # ========== Grid Parameters ==========
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.2,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.6,
        cushion_multiplier=0.8,
        atr_period=14,
        
        # ========== Risk Parameters ==========
        risk_budget_pct=0.6,
        enable_throttling=True,
        initial_cash=100_000.0,
        leverage=20.0,
        
        # ========== Factors ==========
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=False,
        enable_funding_factor=False,
        enable_vol_regime_factor=True,
        
        # ========== MM Risk Zone (调整为更宽松阈值用于压力测试) ==========
        enable_mm_risk_zone=True,
        max_risk_loss_pct=0.50,  # 从30%放宽到50%，用于压力测试
        max_risk_atr_mult=3.0,
        enable_profit_buffer=True,
        profit_buffer_ratio=0.5,
        
        # ========== Inventory ==========
        inventory_capacity_threshold_pct=0.9,
        inventory_skew_k=0.5,
        
        # ========== Console Logging ==========
        enable_console_log=True,
    )
    
    # 输出目录
    output_dir = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 runner
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        output_dir=output_dir,
        verbose=True,
        progress_every=5000,
        collect_equity_detail=True,
    )
    
    # 运行回测
    print("=" * 80)
    print("TaoGrid 压力测试 v2 (增强诊断)")
    print("=" * 80)
    print(f"日期范围: 2025-09-26 至 2025-10-26")
    print(f"支撑/阻力: ${config.support:,.0f} / ${config.resistance:,.0f}")
    print(f"杠杆: {config.leverage}x")
    print(f"MM Risk Zone: 启用 (亏损阈值: {config.max_risk_loss_pct:.0%})")
    print("=" * 80)
    print()
    
    results = runner.run()
    
    # 打印摘要
    runner.print_summary(results)
    
    # 保存结果
    runner.save_results(results, output_dir)
    
    print()
    print("=" * 80)
    print("压力测试 v2 完成！")
    print("=" * 80)
    print(f"结果已保存至: {output_dir}")
    print()


if __name__ == "__main__":
    main()
