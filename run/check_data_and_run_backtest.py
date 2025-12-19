"""
检查数据完整性并运行回测，启用详细日志。
"""

import sys
import io
from pathlib import Path
from datetime import datetime, timezone

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig

def check_data_completeness():
    """检查数据完整性"""
    print("=" * 80)
    print("1. 检查数据完整性")
    print("=" * 80)
    
    start_date = datetime(2025, 9, 26, tzinfo=timezone.utc)
    end_date = datetime(2025, 10, 26, tzinfo=timezone.utc)
    
    dm = DataManager()
    
    # 检查缓存
    cache_file = project_root / "data" / "cache" / "okx_btcusdt_1m.parquet"
    if cache_file.exists():
        cached_data = pd.read_parquet(cache_file)
        if not cached_data.empty:
            print(f"缓存数据:")
            print(f"  时间范围: {cached_data.index.min()} 到 {cached_data.index.max()}")
            print(f"  数据条数: {len(cached_data)}")
            
            # 检查目标时间范围
            target_data = cached_data.loc[
                (cached_data.index >= start_date) & (cached_data.index < end_date)
            ]
            print(f"  目标范围数据条数: {len(target_data)}")
            print(f"  目标范围: {target_data.index.min() if not target_data.empty else 'N/A'} 到 {target_data.index.max() if not target_data.empty else 'N/A'}")
            
            # 检查是否有缺失
            expected_bars = (end_date - start_date).total_seconds() / 60  # 1分钟K线
            print(f"  预期条数: {expected_bars:.0f}")
            print(f"  实际条数: {len(target_data)}")
            print(f"  缺失率: {(1 - len(target_data) / expected_bars) * 100:.2f}%")
            
            if len(target_data) < expected_bars * 0.9:
                print("  ⚠️  警告: 数据可能不完整！")
    else:
        print("未找到缓存数据文件")
    
    print()
    
    # 从API获取数据
    print("从API获取数据（不使用缓存）...")
    try:
        data = dm.get_klines(
            symbol="BTCUSDT",
            timeframe="1m",
            start=start_date,
            end=end_date,
            source="okx",
            use_cache=False,  # 强制从API获取
        )
        if not data.empty:
            print(f"API数据:")
            print(f"  时间范围: {data.index.min()} 到 {data.index.max()}")
            print(f"  数据条数: {len(data)}")
            
            # 检查是否有缺失
            expected_bars = (end_date - start_date).total_seconds() / 60
            print(f"  预期条数: {expected_bars:.0f}")
            print(f"  实际条数: {len(data)}")
            print(f"  缺失率: {(1 - len(data) / expected_bars) * 100:.2f}%")
            
            # 检查数据质量
            print(f"  缺失值: {data.isnull().sum().sum()}")
            print(f"  价格范围: {data['close'].min():.2f} 到 {data['close'].max():.2f}")
        else:
            print("  ⚠️  警告: API返回空数据！")
    except Exception as e:
        print(f"  ❌ 获取数据失败: {e}")
    
    print()

def run_backtest_with_logging():
    """运行回测并启用详细日志"""
    print("=" * 80)
    print("2. 运行回测（启用详细日志）")
    print("=" * 80)
    
    config = TaoGridLeanConfig(
        name="TaoGrid Optimized - Max ROE (Perp)",
        description="Inventory-aware grid (perp maker fee 0.02%), focus on max ROE",

        # ========== S/R Levels ==========
        support=107000.0,
        resistance=123000.0,
        regime="NEUTRAL_RANGE",

        # ========== Grid Parameters ==========
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        enable_mr_trend_factor=False,
        # Breakout risk factor
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,
        # Range position asymmetry v2
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,

        # ========== Risk / Execution ==========
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=50.0,
        enable_mm_risk_zone=False,
        enable_console_log=True,  # 启用控制台日志
    )

    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        verbose=True,
        progress_every=1000,  # 每1000条打印一次进度
    )
    
    print("开始回测...")
    results = runner.run()
    
    print()
    print("=" * 80)
    print("回测结果")
    print("=" * 80)
    runner.print_summary(results)
    
    # 保存结果
    output_dir = Path("run/results_lean_taogrid_debug")
    output_dir.mkdir(parents=True, exist_ok=True)
    runner.save_results(results, output_dir)
    
    print()
    print(f"结果已保存到: {output_dir}")
    
    # 检查交易记录
    if 'trades' in results and len(results['trades']) > 0:
        trades_df = results['trades']
        print(f"\n交易记录分析:")
        print(f"  总交易数: {len(trades_df)}")
        print(f"  第一笔交易时间: {trades_df.iloc[0]['entry_time'] if 'entry_time' in trades_df.columns else 'N/A'}")
        print(f"  最后一笔交易时间: {trades_df.iloc[-1]['exit_time'] if 'exit_time' in trades_df.columns else 'N/A'}")
    else:
        print("\n⚠️  警告: 没有交易记录！")
    
    return results

def main():
    check_data_completeness()
    results = run_backtest_with_logging()
    
    print()
    print("=" * 80)
    print("诊断完成")
    print("=" * 80)

if __name__ == "__main__":
    main()

