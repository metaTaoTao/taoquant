"""
检查网格生成逻辑，确认卖出价格是否正确生成。
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

import numpy as np
from data import DataManager
from algorithms.taogrid.config import TaoGridLeanConfig
from analytics.indicators.grid_generator import generate_grid_levels, calculate_grid_spacing
from analytics.indicators.volatility import calculate_atr

def main():
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
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
    
    print("=" * 80)
    print("网格生成检查")
    print("=" * 80)
    print(f"网格间距: {spacing_pct:.4%}")
    print(f"买入层数: {len(buy_levels)}")
    print(f"卖出层数: {len(sell_levels)}")
    print(f"\n买入价格范围: ${buy_levels.min():,.2f} - ${buy_levels.max():,.2f}")
    print(f"卖出价格范围: ${sell_levels.min():,.2f} - ${sell_levels.max():,.2f}")
    
    # 检查卖出价格是否正确生成
    print(f"\n检查卖出价格生成逻辑:")
    print(f"  前5个买入价格和对应的卖出价格:")
    for i in range(min(5, len(buy_levels))):
        buy_price = buy_levels[i]
        if i < len(sell_levels):
            sell_price = sell_levels[i]
            expected_sell = buy_price * (1 + spacing_pct)
            print(f"    BUY L{i+1}: ${buy_price:,.2f} -> SELL L{i+1}: ${sell_price:,.2f} (预期: ${expected_sell:,.2f})")
    
    # 检查价格覆盖
    data_min = data['close'].min()
    data_max = data['close'].max()
    data_mean = data['close'].mean()
    
    print(f"\n价格覆盖分析:")
    print(f"  数据价格范围: ${data_min:,.2f} - ${data_max:,.2f}")
    print(f"  数据价格均值: ${data_mean:,.2f}")
    print(f"  买入网格范围: ${buy_levels.min():,.2f} - ${buy_levels.max():,.2f}")
    print(f"  卖出网格范围: ${sell_levels.min():,.2f} - ${sell_levels.max():,.2f}")
    
    # 检查价格是否在网格范围内
    price_in_buy_range = ((data['close'] >= buy_levels.min()) & (data['close'] <= buy_levels.max())).sum()
    price_in_sell_range = ((data['close'] >= sell_levels.min()) & (data['close'] <= sell_levels.max())).sum()
    
    print(f"\n价格分布:")
    print(f"  在买入网格范围内: {price_in_buy_range}/{len(data)} ({price_in_buy_range/len(data)*100:.2f}%)")
    print(f"  在卖出网格范围内: {price_in_sell_range}/{len(data)} ({price_in_sell_range/len(data)*100:.2f}%)")
    
    # 检查价格是否触及网格价格
    buy_touches = 0
    sell_touches = 0
    
    for idx, row in data.iterrows():
        bar_high = row['high']
        bar_low = row['low']
        
        for buy_price in buy_levels:
            if bar_low <= buy_price <= bar_high:
                buy_touches += 1
                break
        
        for sell_price in sell_levels:
            if bar_low <= sell_price <= bar_high:
                sell_touches += 1
                break
    
    print(f"\n价格触及统计:")
    print(f"  买入价格被触及: {buy_touches} 次")
    print(f"  卖出价格被触及: {sell_touches} 次")
    print(f"  总触及次数: {buy_touches + sell_touches} 次")
    print(f"  触及率: {(buy_touches + sell_touches)/len(data)*100:.2f}%")

if __name__ == "__main__":
    main()

