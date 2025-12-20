"""
快速测试 Sell Size Limit 修复

简化版本，减少日志输出，专注于验证修复效果
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig


def quick_test():
    """
    快速测试修复效果
    """
    print("=" * 80)
    print("快速测试 Sell Size Limit 修复")
    print("=" * 80)
    print()
    
    # 使用bug报告中相同的配置，但禁用详细日志
    config = TaoGridLeanConfig(
        name="TaoGrid Sell Size Limit Fix Test",
        support=92000.0,
        resistance=106000.0,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=20,
        grid_layers_sell=20,
        initial_cash=10000.0,
        min_return=0.0012,  # 0.12%
        leverage=5.0,
        # 启用所有风控（这些会导致sell size放大）
        enable_mm_risk_zone=True,
        enable_range_pos_asymmetry_v2=True,
        enable_vol_regime_factor=True,
        enable_funding_factor=True,
        enable_throttling=True,
        enable_console_log=False,  # 禁用详细日志，加快速度
    )
    
    # 使用较短的时间段进行快速测试（7天而不是35天）
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 1, 19, tzinfo=timezone.utc),
        end_date=datetime(2025, 1, 26, tzinfo=timezone.utc),  # 只测试7天
        verbose=False,  # 减少输出
    )
    
    print("运行回测（7天数据，禁用详细日志）...")
    print("这可能需要几分钟...")
    print()
    
    results = runner.run()
    
    print()
    print("=" * 80)
    print("回测结果")
    print("=" * 80)
    
    # 分析配对正确率
    import pandas as pd
    trades_df = results.get('trades', pd.DataFrame())
    
    # 显示基本信息
    if 'metrics' in results:
        metrics = results['metrics']
        print(f"总收益: {metrics.get('total_return', 0):.2%}")
        print(f"总交易数: {metrics.get('total_trades', 0)}")
        print(f"平均单笔收益: {metrics.get('avg_return_per_trade', 0):.4%}")
        print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        print()
    
    if isinstance(trades_df, pd.DataFrame) and len(trades_df) > 0:
        df = trades_df
        
        # 计算配对正确率
        correct_matches = (df['entry_level'] == df['exit_level']).sum()
        total_trades = len(df)
        correct_rate = correct_matches / total_trades if total_trades > 0 else 0
        
        print(f"总交易数: {total_trades}")
        print(f"正确配对 (entry_level == exit_level): {correct_matches} ({correct_rate:.1%})")
        print(f"错误配对: {total_trades - correct_matches} ({1 - correct_rate:.1%})")
        
        # 分析收益
        if 'profit_pct' in df.columns:
            correct_profit = df[df['entry_level'] == df['exit_level']]['profit_pct'].mean()
            wrong_profit = df[df['entry_level'] != df['exit_level']]['profit_pct'].mean()
            avg_profit = df['profit_pct'].mean()
            
            print()
            print("收益分析:")
            print(f"  正确配对平均收益: {correct_profit:.4%}")
            print(f"  错误配对平均收益: {wrong_profit:.4%}")
            print(f"  总体平均收益: {avg_profit:.4%}")
        
        # 检查多次平仓的情况
        if 'exit_timestamp' in df.columns:
            df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'])
            exit_counts = df.groupby('exit_timestamp').size()
            multiple_exits = exit_counts[exit_counts > 1]
            
            print()
            print(f"同一时间多笔交易平仓的次数: {len(multiple_exits)}")
            if total_trades > 0:
                print(f"占总交易数的比例: {len(multiple_exits) / total_trades:.1%}")
        
        # 总体指标
        if 'total_return' in results:
            print()
            print(f"总收益: {results['total_return']:.2%}")
        if 'sharpe_ratio' in results:
            print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    
        print()
    else:
        print("没有交易记录（可能是价格未触及网格层级）")
        print()
    
    print("=" * 80)
    print("修复验证")
    print("=" * 80)
    print()
    print("预期效果:")
    print("  [OK] 配对正确率: 50% -> 90%+")
    print("  [OK] 平均单笔收益: -0.16% -> +0.12%+")
    print("  [OK] 多次平仓情况: 40% -> <5%")
    print()
    
    if isinstance(trades_df, pd.DataFrame) and len(trades_df) > 0:
        df = trades_df
        correct_rate = (df['entry_level'] == df['exit_level']).sum() / len(df) if len(df) > 0 else 0
        
        if correct_rate >= 0.85:
            print("[SUCCESS] 配对正确率 >= 85%，修复有效！")
        elif correct_rate >= 0.70:
            print("[PARTIAL] 配对正确率 >= 70%，有改善但还需优化")
        else:
            print("[WARNING] 配对正确率 < 70%，可能还有其他问题")
        
        if 'profit_pct' in df.columns:
            avg_profit = df['profit_pct'].mean()
            if avg_profit > 0:
                print(f"[SUCCESS] 平均单笔收益转正: {avg_profit:.4%}")
            else:
                print(f"[WARNING] 平均单笔收益仍为负: {avg_profit:.4%}")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    quick_test()
