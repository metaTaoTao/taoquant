"""
回测 SUIUSDT 在不同 regime 下的表现（10倍杠杆）
测试时间：2025.09.03 - 2025.10.17
支撑：3.1，阻力：4.2
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner

# =============================================================================
# 回测参数
# =============================================================================
SYMBOL = "SUIUSDT"
START_DATE = datetime(2025, 9, 3, tzinfo=timezone.utc)
END_DATE = datetime(2025, 10, 17, tzinfo=timezone.utc)
SUPPORT = 3.1
RESISTANCE = 4.2
LEVERAGE = 10.0
INITIAL_CASH = 100000.0  # 初始资金 $100,000

# 测试的 regime
REGIMES = [
    "BULLISH_RANGE",   # 70% buy, 30% sell
    "NEUTRAL_RANGE",   # 50% buy, 50% sell
    "BEARISH_RANGE",   # 30% buy, 70% sell
]

# =============================================================================
# 优化后的风控参数（使用增强版配置）
# =============================================================================
def create_config(regime: str) -> TaoGridLeanConfig:
    """创建配置，启用所有优化后的风控功能"""
    return TaoGridLeanConfig(
        # 基础参数
        name=f"TaoGrid SUIUSDT {regime}",
        description=f"SUIUSDT {regime} with enhanced risk controls",
        support=SUPPORT,
        resistance=RESISTANCE,
        regime=regime,
        
        # 网格参数
        grid_layers_buy=5,
        grid_layers_sell=5,
        weight_k=0.5,
        spacing_multiplier=1.0,
        cushion_multiplier=0.8,
        min_return=0.005,
        maker_fee=0.0002,
        volatility_k=0.6,
        atr_period=14,
        
        # 杠杆
        leverage=LEVERAGE,
        initial_cash=INITIAL_CASH,
        
        # 风险参数
        risk_budget_pct=0.3,
        max_long_units=10.0,
        max_short_units=10.0,
        daily_loss_limit=2000.0,
        
        # ENHANCED: 优化后的风控参数
        # 网格关闭阈值（降低，提前触发）
        max_risk_atr_mult=2.0,  # 从 3.0 降至 2.0
        max_risk_loss_pct=0.20,  # 从 0.30 降至 0.20
        max_risk_inventory_pct=0.8,
        max_daily_drawdown_pct=0.20,  # 新增：单日跌幅阈值
        
        # 持仓级止损
        enable_position_level_stop_loss=True,  # 网格关闭时强制平仓
        
        # 强制去杠杆（默认启用，降低阈值）
        enable_forced_deleverage=True,  # 默认启用
        deleverage_level1_unrealized_loss_pct=0.10,  # 从 0.15 降至 0.10
        deleverage_level2_unrealized_loss_pct=0.15,  # 从 0.25 降至 0.15
        deleverage_level3_unrealized_loss_pct=0.20,  # 新增：完全平仓
        deleverage_level1_sell_frac=0.25,
        deleverage_level2_sell_frac=0.50,
        deleverage_level3_sell_frac=1.0,  # 100% 平仓
        deleverage_cooldown_bars=60,
        deleverage_min_notional_usd=2000.0,
        
        # 网格重新启用保护
        grid_re_enable_cooldown_bars=1440,  # 24小时冷却期
        grid_re_enable_price_recovery_atr_mult=1.0,  # 价格恢复验证
        grid_re_enable_requires_manual_approval=False,
        
        # MM 风险区
        enable_mm_risk_zone=True,
        mm_risk_level1_buy_mult=0.2,
        mm_risk_level1_sell_mult=3.0,
        mm_risk_level3_buy_mult=0.05,
        mm_risk_level3_sell_mult=5.0,
        
        # 因子过滤
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_funding_factor=True,
        enable_range_pos_asymmetry_v2=False,
        enable_vol_regime_factor=True,
        
        # 库存管理
        enable_throttling=True,
        inventory_capacity_threshold_pct=0.9,
        enable_regime_inventory_scaling=True,
        
        # 成本基础风险区
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
    )


def check_liquidation(results: dict) -> bool:
    """检查是否爆仓（权益归零或接近归零）"""
    equity_curve = results.get("equity_curve", [])
    if not equity_curve:
        return False
    
    # 获取最小权益
    min_equity = min(point.get("equity", INITIAL_CASH) for point in equity_curve)
    min_equity_pct = min_equity / INITIAL_CASH
    
    # 如果权益低于初始资金的 5%，认为爆仓
    return min_equity_pct < 0.05


def print_results_summary(regime: str, results: dict):
    """打印回测结果摘要"""
    print("\n" + "=" * 80)
    print(f"回测结果摘要 - {regime}")
    print("=" * 80)
    
    metrics = results.get("metrics", {})
    
    # 关键指标
    total_return = metrics.get("total_return", 0.0)
    max_drawdown = metrics.get("max_drawdown", 0.0)
    sharpe_ratio = metrics.get("sharpe_ratio", 0.0)
    win_rate = metrics.get("win_rate", 0.0)
    
    # 权益信息
    equity_curve = results.get("equity_curve", [])
    if equity_curve:
        final_equity = equity_curve[-1].get("equity", INITIAL_CASH)
        min_equity = min(point.get("equity", INITIAL_CASH) for point in equity_curve)
        min_equity_pct = (min_equity / INITIAL_CASH) * 100
    else:
        final_equity = INITIAL_CASH
        min_equity = INITIAL_CASH
        min_equity_pct = 100.0
    
    # 检查爆仓
    is_liquidated = check_liquidation(results)
    
    print(f"\n关键指标:")
    print(f"  总收益率: {total_return:.2%}")
    print(f"  最大回撤: {max_drawdown:.2%}")
    print(f"  Sharpe 比率: {sharpe_ratio:.2f}")
    print(f"  胜率: {win_rate:.2%}")
    
    print(f"\n权益信息:")
    print(f"  初始权益: ${INITIAL_CASH:,.2f}")
    print(f"  最终权益: ${final_equity:,.2f}")
    print(f"  最小权益: ${min_equity:,.2f} ({min_equity_pct:.2f}%)")
    
    print(f"\n风险检查:")
    if is_liquidated:
        print(f"  [X] 爆仓风险: 是（权益最低降至 {min_equity_pct:.2f}%）")
    else:
        print(f"  [OK] 爆仓风险: 否（权益最低 {min_equity_pct:.2f}%）")
    
    if max_drawdown < -0.50:
        print(f"  [WARNING] 最大回撤超过 50%: {max_drawdown:.2%}")
    elif max_drawdown < -0.30:
        print(f"  [WARNING] 最大回撤超过 30%: {max_drawdown:.2%}")
    else:
        print(f"  [OK] 最大回撤在可接受范围: {max_drawdown:.2%}")
    
    print("=" * 80)


def main():
    """主函数：测试所有 regime"""
    print("=" * 80)
    print("SUIUSDT 多 Regime 回测（10倍杠杆）")
    print("=" * 80)
    print(f"\n回测参数:")
    print(f"  交易对: {SYMBOL}")
    print(f"  时间范围: {START_DATE.date()} 至 {END_DATE.date()}")
    print(f"  支撑: ${SUPPORT:.2f}")
    print(f"  阻力: ${RESISTANCE:.2f}")
    print(f"  杠杆: {LEVERAGE}x")
    print(f"  初始资金: ${INITIAL_CASH:,.2f}")
    print(f"  测试 Regime: {', '.join(REGIMES)}")
    print("=" * 80)
    
    all_results = {}
    
    for regime in REGIMES:
        print(f"\n\n{'='*80}")
        print(f"开始回测: {regime}")
        print(f"{'='*80}\n")
        
        try:
            # 创建配置
            config = create_config(regime)
            
            # 创建 runner
            output_dir = Path(f"run/results_suiusdt_{regime.lower()}")
            runner = SimpleLeanRunner(
                config=config,
                symbol=SYMBOL,
                timeframe="1m",
                start_date=START_DATE,
                end_date=END_DATE,
                verbose=True,
                progress_every=1000,
                output_dir=output_dir,
            )
            
            # 运行回测
            results = runner.run()
            
            # 保存结果
            runner.save_results(results, output_dir)
            
            # 打印摘要
            print_results_summary(regime, results)
            
            all_results[regime] = results
            
        except Exception as e:
            print(f"\n[ERROR] 回测失败 ({regime}): {e}")
            import traceback
            traceback.print_exc()
            all_results[regime] = None
    
    # 打印对比总结
    print("\n\n" + "=" * 80)
    print("所有 Regime 对比总结")
    print("=" * 80)
    
    print(f"\n{'Regime':<20} {'总收益率':<12} {'最大回撤':<12} {'Sharpe':<10} {'爆仓风险':<10}")
    print("-" * 80)
    
    for regime in REGIMES:
        if all_results.get(regime) is None:
            print(f"{regime:<20} {'失败':<12} {'-':<12} {'-':<10} {'-':<10}")
            continue
        
        results = all_results[regime]
        metrics = results.get("metrics", {})
        total_return = metrics.get("total_return", 0.0)
        max_drawdown = metrics.get("max_drawdown", 0.0)
        sharpe_ratio = metrics.get("sharpe_ratio", 0.0)
        is_liquidated = check_liquidation(results)
        
        liquidation_status = "是" if is_liquidated else "否"
        
        print(f"{regime:<20} {total_return:>10.2%} {max_drawdown:>10.2%} {sharpe_ratio:>8.2f} {liquidation_status:>8}")
    
    print("=" * 80)
    print("\n回测完成！")


if __name__ == "__main__":
    main()

