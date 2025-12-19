"""
诊断为什么交易数这么少。
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
import numpy as np
from data import DataManager
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig

def main():
    print("=" * 80)
    print("诊断低交易数问题")
    print("=" * 80)
    
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        enable_console_log=False,  # 关闭详细日志，只关注关键信息
    )
    
    # 加载数据
    start_date = datetime(2025, 9, 26, tzinfo=timezone.utc)
    end_date = datetime(2025, 10, 26, tzinfo=timezone.utc)
    
    dm = DataManager()
    data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=start_date,
        end=end_date,
        source="okx",
        use_cache=True,
    )
    
    print(f"\n数据统计:")
    print(f"  总K线数: {len(data)}")
    print(f"  价格范围: {data['close'].min():.2f} - {data['close'].max():.2f}")
    print(f"  价格波动: {(data['close'].max() - data['close'].min()) / data['close'].mean() * 100:.2f}%")
    
    # 检查价格是否经常触及网格价格
    # 这里我们需要知道网格价格，但为了简化，我们检查价格变化频率
    price_changes = data['close'].diff().abs()
    significant_moves = (price_changes > data['close'].mean() * 0.0016).sum()  # 0.16% = grid spacing
    
    print(f"\n价格变化分析:")
    print(f"  价格变化 > 0.16% (网格间距) 的次数: {significant_moves}")
    print(f"  占比: {significant_moves / len(data) * 100:.2f}%")
    
    # 检查是否有连续的价格区间
    price_ranges = []
    current_range_start = None
    current_range_end = None
    
    for idx, (timestamp, row) in enumerate(data.iterrows()):
        price = row['close']
        if current_range_start is None:
            current_range_start = price
            current_range_end = price
        else:
            if abs(price - current_range_end) / current_range_end < 0.0016:  # 在网格间距内
                current_range_end = price
            else:
                price_ranges.append((current_range_start, current_range_end))
                current_range_start = price
                current_range_end = price
    
    if current_range_start is not None:
        price_ranges.append((current_range_start, current_range_end))
    
    print(f"\n价格区间分析:")
    print(f"  价格区间数: {len(price_ranges)}")
    if len(price_ranges) <= 10:
        for i, (start, end) in enumerate(price_ranges[:10]):
            print(f"    区间 {i+1}: {start:.2f} - {end:.2f} (变化: {(end-start)/start*100:.2f}%)")
    
    print("\n" + "=" * 80)
    print("可能的原因:")
    print("1. 价格波动不够大，无法频繁触及网格价格")
    print("2. 网格价格范围设置不当（support/resistance）")
    print("3. 风险控制阻止了订单")
    print("4. 订单触发逻辑有问题（限价单需要价格触及）")

if __name__ == "__main__":
    main()

