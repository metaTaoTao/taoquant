"""
分析网格设置和实际价格的关系。
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
from algorithms.taogrid.config import TaoGridLeanConfig
from analytics.indicators.grid_generator import generate_grid_levels, calculate_grid_spacing
from analytics.indicators.volatility import calculate_atr

def main():
    print("=" * 80)
    print("网格设置分析")
    print("=" * 80)
    
    # 配置
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        spacing_multiplier=1.0,
        volatility_k=0.0,  # Disable volatility adjustment to match home computer
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
    
    if data.empty:
        print("❌ 数据为空！")
        return
    
    print(f"\n数据范围: {data.index.min()} 到 {data.index.max()}")
    print(f"数据条数: {len(data)}")
    print(f"价格范围: {data['close'].min():.2f} 到 {data['close'].max():.2f}")
    print(f"开始价格: {data['close'].iloc[0]:.2f}")
    print(f"结束价格: {data['close'].iloc[-1]:.2f}")
    
    # 计算ATR
    atr = calculate_atr(
        data["high"],
        data["low"],
        data["close"],
        period=config.atr_period,
    )
    current_atr = atr.iloc[-1]
    avg_atr = atr.mean()
    
    print(f"\nATR: {current_atr:.2f} (平均: {avg_atr:.2f})")
    
    # 计算网格间距
    spacing_pct_series = calculate_grid_spacing(
        atr=atr,
        min_return=config.min_return,
        maker_fee=config.maker_fee,
        slippage=0.0,
        volatility_k=config.volatility_k,
        use_limit_orders=True,
    )
    spacing_pct_base = spacing_pct_series.iloc[-1]
    spacing_pct = spacing_pct_base * config.spacing_multiplier
    
    print(f"网格间距: {spacing_pct:.4%} (base: {spacing_pct_base:.4%})")
    
    # 计算mid和cushion
    mid = (config.support + config.resistance) / 2
    cushion = current_atr * config.cushion_multiplier
    
    print(f"\n支撑/阻力:")
    print(f"  Support: {config.support:,.0f}")
    print(f"  Resistance: {config.resistance:,.0f}")
    print(f"  Mid: {mid:,.0f}")
    print(f"  Cushion: {cushion:.2f}")
    
    # 生成网格
    grid_result = generate_grid_levels(
        mid_price=mid,
        support=config.support,
        resistance=config.resistance,
        cushion=cushion,
        spacing_pct=spacing_pct,
        layers_buy=config.grid_layers_buy,
        layers_sell=config.grid_layers_sell,
    )
    
    buy_levels = grid_result["buy_levels"]
    sell_levels = grid_result["sell_levels"]
    
    print(f"\n网格生成结果:")
    print(f"  买入层数: {len(buy_levels)}")
    print(f"  卖出层数: {len(sell_levels)}")
    print(f"  最高买入价 (BUY L1): {buy_levels[0]:,.2f}")
    print(f"  最低买入价 (BUY L{len(buy_levels)}): {buy_levels[-1]:,.2f}")
    print(f"  最低卖出价 (SELL L1): {sell_levels[0]:,.2f}")
    print(f"  最高卖出价 (SELL L{len(sell_levels)}): {sell_levels[-1]:,.2f}")
    
    # 检查价格是否在网格范围内
    price_min = data['close'].min()
    price_max = data['close'].max()
    
    print(f"\n价格覆盖分析:")
    print(f"  数据最低价: {price_min:,.2f}")
    print(f"  数据最高价: {price_max:,.2f}")
    print(f"  网格最低买入价: {buy_levels[-1]:,.2f}")
    print(f"  网格最高卖出价: {sell_levels[-1]:,.2f}")
    
    if price_min < buy_levels[-1]:
        print(f"  ⚠️  警告: 数据最低价 ({price_min:,.2f}) 低于网格最低买入价 ({buy_levels[-1]:,.2f})")
    if price_max > sell_levels[-1]:
        print(f"  ⚠️  警告: 数据最高价 ({price_max:,.2f}) 高于网格最高卖出价 ({sell_levels[-1]:,.2f})")
    
    # 检查有多少价格在网格范围内
    prices_in_buy_range = ((data['close'] >= buy_levels[-1]) & (data['close'] <= buy_levels[0])).sum()
    prices_in_sell_range = ((data['close'] >= sell_levels[0]) & (data['close'] <= sell_levels[-1])).sum()
    
    print(f"\n价格分布:")
    print(f"  在买入网格范围内: {prices_in_buy_range} / {len(data)} ({prices_in_buy_range/len(data)*100:.1f}%)")
    print(f"  在卖出网格范围内: {prices_in_sell_range} / {len(data)} ({prices_in_sell_range/len(data)*100:.1f}%)")
    
    # 检查开始价格
    start_price = data['close'].iloc[0]
    print(f"\n开始价格分析:")
    print(f"  开始价格: {start_price:,.2f}")
    print(f"  距离mid: {(start_price - mid):,.2f} ({(start_price - mid)/mid*100:.2f}%)")
    
    if start_price < buy_levels[-1]:
        print(f"  ❌ 开始价格低于网格最低买入价！")
    elif start_price > buy_levels[0]:
        print(f"  ❌ 开始价格高于网格最高买入价！")
    else:
        print(f"  ✓ 开始价格在买入网格范围内")
    
    if start_price < sell_levels[0]:
        print(f"  ✓ 开始价格低于最低卖出价（可以买入）")
    elif start_price > sell_levels[-1]:
        print(f"  ❌ 开始价格高于最高卖出价！")
    else:
        print(f"  ✓ 开始价格在卖出网格范围内（可以卖出）")

if __name__ == "__main__":
    main()

