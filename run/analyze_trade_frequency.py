"""
详细分析为什么交易笔数这么少。
检查：
1. 网格价格范围 vs 实际价格范围
2. 价格是否经常触及网格价格
3. 订单触发逻辑
4. 风险控制是否阻止订单
5. 网格是否被关闭
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

def analyze_grid_price_coverage(data, buy_levels, sell_levels):
    """分析价格是否触及网格价格"""
    print("\n" + "=" * 80)
    print("1. 网格价格覆盖分析")
    print("=" * 80)
    
    # 检查每个K线的high/low是否触及网格价格
    buy_touches = []
    sell_touches = []
    
    for idx, (timestamp, row) in enumerate(data.iterrows()):
        bar_high = row['high']
        bar_low = row['low']
        
        # 检查买入价格是否被触及（价格下跌触及买入价）
        for buy_price in buy_levels:
            if bar_low <= buy_price <= bar_high:
                buy_touches.append({
                    'timestamp': timestamp,
                    'price': buy_price,
                    'bar_high': bar_high,
                    'bar_low': bar_low,
                })
        
        # 检查卖出价格是否被触及（价格上涨触及卖出价）
        for sell_price in sell_levels:
            if bar_low <= sell_price <= bar_high:
                sell_touches.append({
                    'timestamp': timestamp,
                    'price': sell_price,
                    'bar_high': bar_high,
                    'bar_low': bar_low,
                })
    
    buy_touches_df = pd.DataFrame(buy_touches)
    sell_touches_df = pd.DataFrame(sell_touches)
    
    print(f"  买入价格被触及次数: {len(buy_touches)}")
    print(f"  卖出价格被触及次数: {len(sell_touches)}")
    print(f"  总K线数: {len(data)}")
    print(f"  触及率: {(len(buy_touches) + len(sell_touches)) / len(data) * 100:.2f}%")
    
    if len(buy_touches) > 0:
        print(f"\n  买入价格触及统计:")
        buy_price_counts = buy_touches_df['price'].value_counts().sort_index(ascending=False)
        print(f"    最常被触及的买入价格 (前10):")
        for price, count in buy_price_counts.head(10).items():
            print(f"      ${price:,.2f}: {count}次")
    
    if len(sell_touches) > 0:
        print(f"\n  卖出价格触及统计:")
        sell_price_counts = sell_touches_df['price'].value_counts().sort_index()
        print(f"    最常被触及的卖出价格 (前10):")
        for price, count in sell_price_counts.head(10).items():
            print(f"      ${price:,.2f}: {count}次")
    
    return buy_touches_df, sell_touches_df

def analyze_price_movement(data, grid_spacing_pct):
    """分析价格移动模式"""
    print("\n" + "=" * 80)
    print("2. 价格移动分析")
    print("=" * 80)
    
    # 计算价格变化
    price_changes = data['close'].pct_change().abs()
    
    # 统计不同幅度的价格变化
    spacing_threshold = grid_spacing_pct
    small_moves = (price_changes < spacing_threshold).sum()
    medium_moves = ((price_changes >= spacing_threshold) & (price_changes < spacing_threshold * 2)).sum()
    large_moves = (price_changes >= spacing_threshold * 2).sum()
    
    print(f"  网格间距: {spacing_threshold*100:.4f}%")
    print(f"  价格变化 < 网格间距: {small_moves} ({small_moves/len(data)*100:.2f}%)")
    print(f"  价格变化 1-2倍网格间距: {medium_moves} ({medium_moves/len(data)*100:.2f}%)")
    print(f"  价格变化 >= 2倍网格间距: {large_moves} ({large_moves/len(data)*100:.2f}%)")
    
    # 检查价格是否在网格范围内移动
    price_in_range = ((data['close'] >= data['close'].min()) & 
                      (data['close'] <= data['close'].max())).sum()
    print(f"\n  价格在数据范围内: {price_in_range}/{len(data)} ({price_in_range/len(data)*100:.2f}%)")
    
    # 检查价格是否经常回到之前的价格
    price_levels = data['close'].round(decimals=-2)  # 四舍五入到百位
    unique_levels = price_levels.nunique()
    print(f"  价格水平数（四舍五入到百位）: {unique_levels}")
    print(f"  平均每个价格水平的K线数: {len(data)/unique_levels:.1f}")

def analyze_grid_range(data, buy_levels, sell_levels):
    """分析网格价格范围 vs 实际价格范围"""
    print("\n" + "=" * 80)
    print("3. 网格价格范围分析")
    print("=" * 80)
    
    data_min = data['close'].min()
    data_max = data['close'].max()
    data_mean = data['close'].mean()
    
    buy_min = buy_levels.min() if len(buy_levels) > 0 else 0
    buy_max = buy_levels.max() if len(buy_levels) > 0 else 0
    sell_min = sell_levels.min() if len(sell_levels) > 0 else 0
    sell_max = sell_levels.max() if len(sell_levels) > 0 else 0
    
    print(f"  实际价格范围: ${data_min:,.2f} - ${data_max:,.2f}")
    print(f"  实际价格均值: ${data_mean:,.2f}")
    print(f"  买入网格范围: ${buy_min:,.2f} - ${buy_max:,.2f}")
    print(f"  卖出网格范围: ${sell_min:,.2f} - ${sell_max:,.2f}")
    
    # 检查覆盖情况
    price_in_buy_range = ((data['close'] >= buy_min) & (data['close'] <= buy_max)).sum()
    price_in_sell_range = ((data['close'] >= sell_min) & (data['close'] <= sell_max)).sum()
    
    print(f"\n  价格在买入网格范围内: {price_in_buy_range}/{len(data)} ({price_in_buy_range/len(data)*100:.2f}%)")
    print(f"  价格在卖出网格范围内: {price_in_sell_range}/{len(data)} ({price_in_sell_range/len(data)*100:.2f}%)")
    
    # 检查是否有价格超出网格范围
    below_buy_min = (data['close'] < buy_min).sum()
    above_sell_max = (data['close'] > sell_max).sum()
    
    if below_buy_min > 0:
        print(f"  ⚠️  警告: {below_buy_min} 根K线价格低于买入网格最低价")
    if above_sell_max > 0:
        print(f"  ⚠️  警告: {above_sell_max} 根K线价格高于卖出网格最高价")

def main():
    print("=" * 80)
    print("交易频率详细分析")
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
        volatility_k=0.0,
        cushion_multiplier=0.8,
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
    
    print(f"\n数据加载完成:")
    print(f"  时间范围: {data.index.min()} 到 {data.index.max()}")
    print(f"  总K线数: {len(data)}")
    
    # 计算ATR和网格
    atr = calculate_atr(
        data["high"],
        data["low"],
        data["close"],
        period=config.atr_period,
    )
    current_atr = atr.iloc[-1]
    
    spacing_pct_series = calculate_grid_spacing(
        atr=atr,
        min_return=config.min_return,
        maker_fee=config.maker_fee,
        slippage=0.0,
        volatility_k=config.volatility_k,
        use_limit_orders=True,
    )
    spacing_pct = spacing_pct_series.iloc[-1]
    
    mid = (config.support + config.resistance) / 2
    cushion = current_atr * config.cushion_multiplier
    
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
    
    print(f"\n网格生成完成:")
    print(f"  网格间距: {spacing_pct*100:.4f}%")
    print(f"  买入层数: {len(buy_levels)}")
    print(f"  卖出层数: {len(sell_levels)}")
    
    # 执行分析
    analyze_grid_range(data, buy_levels, sell_levels)
    analyze_price_movement(data, spacing_pct)
    buy_touches, sell_touches = analyze_grid_price_coverage(data, buy_levels, sell_levels)
    
    # 总结
    print("\n" + "=" * 80)
    print("总结和建议")
    print("=" * 80)
    
    total_touches = len(buy_touches) + len(sell_touches)
    expected_trades = total_touches  # 理论上每次触及都应该触发交易
    
    print(f"  网格价格被触及总次数: {total_touches}")
    print(f"  实际交易数: 16")
    print(f"  交易触发率: {16/total_touches*100:.2f}%" if total_touches > 0 else "  交易触发率: N/A")
    
    if total_touches > 0 and 16 < total_touches * 0.1:
        print(f"\n  ⚠️  问题: 网格价格被触及很多次，但交易数很少！")
        print(f"  可能的原因:")
        print(f"    1. 订单被风险控制阻止")
        print(f"    2. 网格被关闭（grid shutdown）")
        print(f"    3. 订单大小被限制为0")
        print(f"    4. 订单触发逻辑有问题（filled_levels阻止重复触发）")
        print(f"    5. 库存限制阻止了新订单")

if __name__ == "__main__":
    main()

