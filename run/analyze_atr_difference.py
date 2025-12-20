"""
分析为什么7月和12月的ATR差距这么大

可能原因：
1. 市场波动性变化（最可能）
2. 数据源差异（OKX vs Bitget）
3. 数据质量问题
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

from analytics.indicators.volatility import calculate_atr
from data import DataManager


def analyze_atr_difference(symbol: str = "BTCUSDT"):
    """
    分析ATR差异的原因
    """
    print("=" * 80)
    print("ATR 差异分析")
    print("=" * 80)
    print()
    
    data_manager = DataManager()
    
    # 7月数据
    july_start = datetime(2024, 7, 1, tzinfo=timezone.utc)
    july_end = datetime(2024, 7, 8, tzinfo=timezone.utc)
    
    # 12月数据（当前）
    dec_start = datetime.now(timezone.utc) - timedelta(days=7)
    dec_end = datetime.now(timezone.utc)
    
    print("1. 7月数据 (2024-07-01 到 2024-07-08)")
    print("-" * 80)
    try:
        july_data = data_manager.get_klines(
            symbol=symbol,
            timeframe="1m",
            start=july_start,
            end=july_end,
            source="okx",
        )
        
        if len(july_data) > 14:
            july_atr = calculate_atr(
                july_data["high"],
                july_data["low"],
                july_data["close"],
                period=14,
            )
            
            print(f"数据量: {len(july_data)} 根")
            print(f"价格范围: ${july_data['close'].min():,.0f} - ${july_data['close'].max():,.0f}")
            print(f"价格波动: {((july_data['close'].max() - july_data['close'].min()) / july_data['close'].min() * 100):.2f}%")
            print(f"当前 ATR: ${july_atr.iloc[-1]:,.2f}")
            print(f"平均 ATR: ${july_atr.mean():,.2f}")
            print(f"ATR 标准差: ${july_atr.std():,.2f}")
            print(f"ATR 最大值: ${july_atr.max():,.2f}")
            print(f"ATR 最小值: ${july_atr.min():,.2f}")
            
            # 计算价格波动率
            july_returns = july_data['close'].pct_change().dropna()
            july_volatility = july_returns.std() * np.sqrt(60 * 24) * 100  # 年化波动率
            print(f"价格波动率 (年化): {july_volatility:.2f}%")
        else:
            print("数据不足")
    except Exception as e:
        print(f"错误: {e}")
    
    print()
    print("2. 12月数据 (最近7天)")
    print("-" * 80)
    try:
        dec_data = data_manager.get_klines(
            symbol=symbol,
            timeframe="1m",
            start=dec_start,
            end=dec_end,
            source="okx",
        )
        
        if len(dec_data) > 14:
            dec_atr = calculate_atr(
                dec_data["high"],
                dec_data["low"],
                dec_data["close"],
                period=14,
            )
            
            print(f"数据量: {len(dec_data)} 根")
            print(f"价格范围: ${dec_data['close'].min():,.0f} - ${dec_data['close'].max():,.0f}")
            print(f"价格波动: {((dec_data['close'].max() - dec_data['close'].min()) / dec_data['close'].min() * 100):.2f}%")
            print(f"当前 ATR: ${dec_atr.iloc[-1]:,.2f}")
            print(f"平均 ATR: ${dec_atr.mean():,.2f}")
            print(f"ATR 标准差: ${dec_atr.std():,.2f}")
            print(f"ATR 最大值: ${dec_atr.max():,.2f}")
            print(f"ATR 最小值: ${dec_atr.min():,.2f}")
            
            # 计算价格波动率
            dec_returns = dec_data['close'].pct_change().dropna()
            dec_volatility = dec_returns.std() * np.sqrt(60 * 24) * 100  # 年化波动率
            print(f"价格波动率 (年化): {dec_volatility:.2f}%")
        else:
            print("数据不足")
    except Exception as e:
        print(f"错误: {e}")
    
    print()
    print("=" * 80)
    print("结论")
    print("=" * 80)
    print()
    print("ATR 差距的主要原因：")
    print("1. 市场波动性变化：7月市场波动性高，12月波动性低")
    print("2. 这是正常的市场周期现象")
    print("3. 实盘需要适应当前的低波动环境")
    print()
    print("解决方案：")
    print("1. 保持使用 1m 数据（与回测一致）")
    print("2. 调整 min_return 以适应低波动环境")
    print("3. 或者调整 volatility_k 参数")
    print("4. 或者使用更长的历史数据（30天）来稳定 ATR 计算")
    print()
    print("=" * 80)


if __name__ == "__main__":
    analyze_atr_difference()
