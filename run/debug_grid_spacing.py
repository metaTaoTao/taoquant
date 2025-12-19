"""
调试网格间距计算。
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
from analytics.indicators.grid_generator import calculate_grid_spacing
from analytics.indicators.volatility import calculate_atr

def main():
    print("=" * 80)
    print("网格间距计算调试")
    print("=" * 80)
    
    config = TaoGridLeanConfig(
        min_return=0.0012,
        maker_fee=0.0002,
        spacing_multiplier=1.0,
        volatility_k=0.1,  # Reduced to prevent excessive spacing
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
    
    # 计算ATR
    atr = calculate_atr(
        data["high"],
        data["low"],
        data["close"],
        period=config.atr_period,
    )
    
    current_atr = atr.iloc[-1]
    atr_mean = atr.mean()
    atr_rolling_mean = atr.rolling(window=20, min_periods=1).mean()
    atr_pct = atr / atr_rolling_mean
    
    print(f"\nATR统计:")
    print(f"  当前ATR: {current_atr:.2f}")
    print(f"  平均ATR: {atr_mean:.2f}")
    print(f"  最后20期滚动平均: {atr_rolling_mean.iloc[-1]:.2f}")
    print(f"  最后ATR百分比: {atr_pct.iloc[-1]:.4f}")
    
    # 计算交易成本
    trading_costs = 2 * config.maker_fee
    base_spacing = config.min_return + trading_costs
    volatility_adjustment = config.volatility_k * (atr_pct.iloc[-1] - 1.0)
    spacing_pct = base_spacing + volatility_adjustment
    
    print(f"\n间距计算:")
    print(f"  min_return: {config.min_return:.4%}")
    print(f"  maker_fee: {config.maker_fee:.4%}")
    print(f"  trading_costs (2×maker_fee): {trading_costs:.4%}")
    print(f"  base_spacing (min_return + trading_costs): {base_spacing:.4%}")
    print(f"  volatility_k: {config.volatility_k}")
    print(f"  volatility_adjustment: {volatility_adjustment:.4%}")
    print(f"  spacing_pct (before clip): {spacing_pct:.4%}")
    
    # 调用函数
    spacing_series = calculate_grid_spacing(
        atr=atr,
        min_return=config.min_return,
        maker_fee=config.maker_fee,
        slippage=0.0,
        volatility_k=config.volatility_k,
        use_limit_orders=True,
    )
    
    final_spacing = spacing_series.iloc[-1]
    print(f"  final_spacing (after clip): {final_spacing:.4%}")
    
    # 检查是否被上限限制
    MAX_SPACING = 0.05
    if final_spacing >= MAX_SPACING - 0.0001:
        print(f"\n  ⚠️  警告: 间距被上限 ({MAX_SPACING:.2%}) 限制了！")
        print(f"  这会导致网格层数过少，无法覆盖价格范围。")
        print(f"  建议: 降低 volatility_k 或增加 min_return")

if __name__ == "__main__":
    main()

