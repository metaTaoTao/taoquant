"""
测试 Sell Size Limit 修复

验证：
1. Sell size 是否被限制在对应 buy position size
2. 是否消除了多次匹配导致的 FIFO fallback
3. 配对正确率是否提升
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


def test_sell_size_limit_fix():
    """
    运行回测验证修复效果
    """
    print("=" * 80)
    print("测试 Sell Size Limit 修复")
    print("=" * 80)
    print()
    
    # 使用bug报告中相同的配置
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
    )
    
    # 使用bug报告中相同的时间段
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 1, 19, tzinfo=timezone.utc),
        end_date=datetime(2025, 2, 22, tzinfo=timezone.utc),
        verbose=False,  # 减少输出，加快速度
    )
    
    print("运行回测...")
    results = runner.run()
    
    print()
    print("=" * 80)
    print("回测结果分析")
    print("=" * 80)
    runner.print_summary(results)
    
    # 分析配对正确率
    print()
    print("=" * 80)
    print("配对分析")
    print("=" * 80)
    
    import pandas as pd
    trades_df = results.get('trades', pd.DataFrame())
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
        if 'return_pct' in df.columns:
            correct_profit = df[df['entry_level'] == df['exit_level']]['return_pct'].mean()
            wrong_profit = df[df['entry_level'] != df['exit_level']]['return_pct'].mean()
            avg_profit = df['return_pct'].mean()
            
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
            print(f"占总交易数的比例: {len(multiple_exits) / total_trades:.1%}")
            
            if len(multiple_exits) > 0:
                print()
                print("前10个多次平仓的时间点:")
                for timestamp in multiple_exits.index[:10]:
                    trades_at_time = df[df['exit_timestamp'] == timestamp]
                    print(f"  {timestamp}: {len(trades_at_time)} 笔交易")
                    for _, trade in trades_at_time.iterrows():
                        size_val = trade.get('size', 0)
                        profit_val = trade.get('return_pct', 0)
                        if pd.isna(profit_val):
                            profit_str = 'N/A'
                        else:
                            profit_str = f"{profit_val:.4%}"
                        print(f"    Entry[{trade['entry_level']}] -> Exit[{trade['exit_level']}], size={size_val:.4f}, profit={profit_str}")
    
    print()
    print("=" * 80)
    print("修复验证")
    print("=" * 80)
    print()
    print("预期效果:")
    print("1. 配对正确率: 50% → 90%+")
    print("2. 平均单笔收益: -0.16% → +0.12%+")
    print("3. 多次平仓情况: 40% → <5%")
    print()
    print("=" * 80)


if __name__ == "__main__":
    test_sell_size_limit_fix()
