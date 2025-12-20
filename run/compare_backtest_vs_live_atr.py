"""
对比回测和实盘的 ATR 差异

分析：
1. 回测使用的数据源和时间框架
2. 实盘使用的数据源和时间框架
3. ATR 计算差异
4. 为什么会有差距
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from analytics.indicators.volatility import calculate_atr
from data.sources.bitget_sdk import BitgetSDKDataSource
from data import DataManager


def compare_atr(symbol: str = "BTCUSDT", backtest_date: datetime = None):
    """
    对比回测和实盘的 ATR
    """
    print("=" * 80)
    print("回测 vs 实盘 ATR 对比分析")
    print("=" * 80)
    print()
    
    # 如果没有指定回测日期，使用7月1日作为示例
    if backtest_date is None:
        backtest_date = datetime(2024, 7, 1, tzinfo=timezone.utc)
    
    print(f"回测日期: {backtest_date.date()}")
    print(f"当前日期: {datetime.now(timezone.utc).date()}")
    print()
    
    # 实盘数据源（Bitget）
    bitget_source = BitgetSDKDataSource()
    
    # 回测数据源（可能是 OKX 或其他）
    data_manager = DataManager()
    
    # 测试不同的时间框架
    timeframes = ["1m", "15m", "1h", "4h"]
    
    print("=" * 80)
    print("1. 实盘 ATR (Bitget, 最近7天)")
    print("=" * 80)
    
    # 实盘：最近7天，1m 数据
    live_end = datetime.now(timezone.utc)
    live_start = live_end - timedelta(days=7)
    
    print(f"时间范围: {live_start.date()} 到 {live_end.date()}")
    print()
    
    live_atr_results = {}
    for tf in timeframes:
        try:
            print(f"获取 {tf} 数据...")
            live_data = bitget_source.get_klines(
                symbol=symbol,
                timeframe=tf,
                start=live_start,
                end=live_end,
            )
            
            if len(live_data) > 14:
                atr = calculate_atr(
                    live_data["high"],
                    live_data["low"],
                    live_data["close"],
                    period=14,
                )
                current_atr = atr.iloc[-1]
                avg_atr = atr.mean()
                atr_pct = (current_atr / live_data["close"].iloc[-1]) * 100
                
                live_atr_results[tf] = {
                    "current_atr": current_atr,
                    "avg_atr": avg_atr,
                    "atr_pct": atr_pct,
                    "bars": len(live_data),
                }
                
                print(f"  {tf:>4}: 当前 ATR = ${current_atr:,.2f}, 平均 ATR = ${avg_atr:,.2f}, ATR% = {atr_pct:.2f}%, 数据量 = {len(live_data)}")
            else:
                print(f"  {tf:>4}: 数据不足 ({len(live_data)} 根)")
        except Exception as e:
            print(f"  {tf:>4}: 错误 - {e}")
    
    print()
    
    # 回测数据：7月的数据
    print("=" * 80)
    print("2. 回测 ATR (7月数据)")
    print("=" * 80)
    
    backtest_start = backtest_date
    backtest_end = backtest_start + timedelta(days=7)
    
    print(f"时间范围: {backtest_start.date()} 到 {backtest_end.date()}")
    print()
    
    backtest_atr_results = {}
    for tf in timeframes:
        try:
            print(f"获取 {tf} 数据...")
            # 尝试从 OKX 获取（回测常用数据源）
            backtest_data = data_manager.get_klines(
                symbol=symbol,
                timeframe=tf,
                start=backtest_start,
                end=backtest_end,
                source="okx",
            )
            
            if len(backtest_data) > 14:
                atr = calculate_atr(
                    backtest_data["high"],
                    backtest_data["low"],
                    backtest_data["close"],
                    period=14,
                )
                current_atr = atr.iloc[-1]
                avg_atr = atr.mean()
                atr_pct = (current_atr / backtest_data["close"].iloc[-1]) * 100
                
                backtest_atr_results[tf] = {
                    "current_atr": current_atr,
                    "avg_atr": avg_atr,
                    "atr_pct": atr_pct,
                    "bars": len(backtest_data),
                }
                
                print(f"  {tf:>4}: 当前 ATR = ${current_atr:,.2f}, 平均 ATR = ${avg_atr:,.2f}, ATR% = {atr_pct:.2f}%, 数据量 = {len(backtest_data)}")
            else:
                print(f"  {tf:>4}: 数据不足 ({len(backtest_data)} 根)")
        except Exception as e:
            print(f"  {tf:>4}: 错误 - {e}")
    
    print()
    
    # 对比分析
    print("=" * 80)
    print("3. 对比分析")
    print("=" * 80)
    print()
    
    print(f"{'Timeframe':<10} {'回测 ATR':<15} {'实盘 ATR':<15} {'差异':<15} {'差异%':<15}")
    print("-" * 80)
    
    for tf in timeframes:
        if tf in live_atr_results and tf in backtest_atr_results:
            live_atr = live_atr_results[tf]["current_atr"]
            backtest_atr = backtest_atr_results[tf]["current_atr"]
            diff = live_atr - backtest_atr
            diff_pct = (diff / backtest_atr) * 100
            
            print(f"{tf:<10} ${backtest_atr:>12,.2f}  ${live_atr:>12,.2f}  ${diff:>12,.2f}  {diff_pct:>13.2f}%")
    
    print()
    
    # 关键发现
    print("=" * 80)
    print("4. 关键发现")
    print("=" * 80)
    print()
    
    if "1m" in live_atr_results:
        live_1m_atr = live_atr_results["1m"]["current_atr"]
        print(f"实盘使用 1m 数据，ATR = ${live_1m_atr:,.2f}")
        print()
        print("问题分析：")
        print("1. 实盘使用 1m 数据计算 ATR")
        print("   - 1m 数据的 ATR 通常比 15m/1h 数据小很多")
        print("   - 因为 1m K 线的价格波动范围更小")
        print()
        print("2. 回测可能使用 15m 或其他时间框架")
        print("   - 15m 数据的 ATR 通常比 1m 大 3-4 倍")
        print("   - 这会导致网格间距计算差异巨大")
        print()
        print("3. 解决方案：")
        print("   a) 实盘也应该使用 15m 数据计算 ATR（推荐）")
        print("   b) 或者调整 ATR 计算的时间框架")
        print("   c) 或者使用固定倍数调整（1m ATR × 倍数 ≈ 15m ATR）")
        print()
    
    # 检查实盘代码
    print("=" * 80)
    print("5. 实盘代码检查")
    print("=" * 80)
    print()
    print("实盘代码 (bitget_live_runner.py) 使用：")
    print("  - timeframe='1m' (第 117 行)")
    print("  - 最近 7 天数据")
    print()
    print("建议修改：")
    print("  - 将 timeframe 改为 '15m' 或与回测一致")
    print("  - 或者增加历史数据长度（例如 30 天）")
    print()
    
    print("=" * 80)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="对比回测和实盘的 ATR")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="交易对")
    parser.add_argument("--backtest-date", type=str, default=None, help="回测日期 (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    backtest_date = None
    if args.backtest_date:
        backtest_date = datetime.strptime(args.backtest_date, "%Y-%m-%d")
        backtest_date = backtest_date.replace(tzinfo=timezone.utc)
    
    compare_atr(symbol=args.symbol, backtest_date=backtest_date)


if __name__ == "__main__":
    main()
