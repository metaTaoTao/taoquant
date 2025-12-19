"""
测试不同的volatility_k值对网格间距和层数的影响。
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
    print("测试不同的volatility_k值")
    print("=" * 80)
    
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
    
    # 计算ATR
    atr = calculate_atr(
        data["high"],
        data["low"],
        data["close"],
        period=14,
    )
    current_atr = atr.iloc[-1]
    atr_rolling_mean = atr.rolling(window=20, min_periods=1).mean()
    atr_pct = atr / atr_rolling_mean
    
    print(f"\nATR统计:")
    print(f"  当前ATR: {current_atr:.2f}")
    print(f"  最后20期滚动平均: {atr_rolling_mean.iloc[-1]:.2f}")
    print(f"  最后ATR百分比: {atr_pct.iloc[-1]:.4f}")
    
    # 测试不同的volatility_k值
    volatility_k_values = [0.0, 0.05, 0.1, 0.2, 0.6]
    
    print(f"\n{'volatility_k':<15} {'间距':<12} {'买入层数':<10} {'卖出层数':<10} {'最低买入价':<15} {'最高卖出价':<15}")
    print("-" * 80)
    
    for vk in volatility_k_values:
        config = TaoGridLeanConfig(
            support=107000.0,
            resistance=123000.0,
            grid_layers_buy=40,
            grid_layers_sell=40,
            min_return=0.0012,
            maker_fee=0.0002,
            spacing_multiplier=1.0,
            volatility_k=vk,
            cushion_multiplier=0.8,
        )
        
        # 计算间距
        spacing_pct_series = calculate_grid_spacing(
            atr=atr,
            min_return=config.min_return,
            maker_fee=config.maker_fee,
            slippage=0.0,
            volatility_k=config.volatility_k,
            use_limit_orders=True,
        )
        spacing_pct = spacing_pct_series.iloc[-1]
        
        # 生成网格
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
        
        print(f"{vk:<15} {spacing_pct*100:>10.4f}% {len(buy_levels):<10} {len(sell_levels):<10} {buy_levels[-1] if len(buy_levels) > 0 else 0:>13,.2f} {sell_levels[-1] if len(sell_levels) > 0 else 0:>13,.2f}")
    
    print("\n" + "=" * 80)
    print("建议：")
    print("  - 如果家里电脑有1200+笔交易，volatility_k应该接近0.0")
    print("  - 或者家里电脑的ATR计算不同（可能使用了不同的数据范围）")

if __name__ == "__main__":
    main()

