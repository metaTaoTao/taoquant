"""
TaoGrid 压力测试 - 2025-09-26 至 2025-10-26（含极端插针行情）

这段区间包含极端行情，用于测试策略在极端市场条件下的表现。

用法:
    python run/taogrid_stress_test_2025_09_26.py

输出:
    run/results_lean_taogrid_stress_test_2025_09_26/
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
    """运行压力测试回测"""
    
    # 配置：使用合理的参数，启用 MM Risk Zone 做压力测试
    config = TaoGridLeanConfig(
        name="TaoGrid Stress Test (2025-09-26 to 2025-10-26)",
        description="压力测试：极端插针行情，S=107K, R=123K",
        
        # ========== S/R Levels ==========
        support=107_000.0,
        resistance=123_000.0,
        regime="NEUTRAL_RANGE",
        
        # ========== Grid Parameters ==========
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.2,
        spacing_multiplier=1.0,
        min_return=0.0012,  # 0.12% net return
        maker_fee=0.0002,
        volatility_k=0.6,
        cushion_multiplier=0.8,
        atr_period=14,
        
        # ========== Risk Parameters ==========
        risk_budget_pct=0.6,
        enable_throttling=True,
        initial_cash=100_000.0,
        leverage=20.0,  # 使用适中杠杆
        
        # ========== Factors ==========
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=False,  # 简化，专注压力测试
        enable_funding_factor=False,  # 压力测试时暂时禁用，避免API依赖
        enable_vol_regime_factor=True,
        
        # ========== MM Risk Zone (关键：压力测试必须启用) ==========
        enable_mm_risk_zone=True,  # 启用风控，测试极端行情下的表现
        max_risk_loss_pct=0.30,  # 30% 亏损阈值
        max_risk_atr_mult=3.0,  # 价格跌破支撑 - 3×ATR 关闭网格
        enable_profit_buffer=True,  # 使用利润缓冲
        profit_buffer_ratio=0.5,
        
        # ========== Inventory ==========
        inventory_capacity_threshold_pct=0.9,
        inventory_skew_k=0.5,
        
        # ========== Console Logging ==========
        enable_console_log=True,  # 压力测试时保持日志，观察关键事件
    )
    
    # 输出目录
    output_dir = Path("run/results_lean_taogrid_stress_test_2025_09_26")
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
        collect_equity_detail=True,  # 压力测试需要详细的权益曲线分析
    )
    
    # 运行回测
    print("=" * 80)
    print("TaoGrid 压力测试")
    print("=" * 80)
    print(f"日期范围: 2025-09-26 至 2025-10-26")
    print(f"支撑/阻力: ${config.support:,.0f} / ${config.resistance:,.0f}")
    print(f"杠杆: {config.leverage}x")
    print(f"MM Risk Zone: {'启用' if config.enable_mm_risk_zone else '禁用'}")
    print("=" * 80)
    print()
    
    results = runner.run()
    
    # 打印摘要
    runner.print_summary(results)
    
    # 保存结果
    runner.save_results(results, output_dir)
    
    print()
    print("=" * 80)
    print("压力测试完成！")
    print("=" * 80)
    print(f"结果已保存至: {output_dir}")
    print()
    print("关键文件:")
    print(f"  - metrics.json: 性能指标")
    print(f"  - equity_curve.csv: 权益曲线（用于分析回撤）")
    print(f"  - trades.csv: 交易明细")
    print(f"  - orders.csv: 订单明细")
    print()


if __name__ == "__main__":
    main()
