"""
检查10.10-10.11期间的实际市场价格
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from data.data_manager import DataManager

dm = DataManager()

# 检查暴跌期间的实际价格
start = pd.Timestamp("2025-10-10 20:00:00", tz='UTC')
end = pd.Timestamp("2025-10-11 10:00:00", tz='UTC')

print("=" * 80)
print("检查10.10-10.11期间的实际市场价格")
print("=" * 80)

try:
    data = dm.get_klines('BTCUSDT', '1m', start=start, end=end, use_cache=False)
    
    print(f"\n数据时间范围: {data.index.min()} 至 {data.index.max()}")
    print(f"数据条数: {len(data)}")
    
    print(f"\n价格统计:")
    print(f"  最低价: ${data['low'].min():,.2f}")
    print(f"  最高价: ${data['high'].max():,.2f}")
    print(f"  最低价时间: {data.loc[data['low'].idxmin()].name}")
    
    # 找出最低价格附近的数据
    min_idx = data['low'].idxmin()
    print(f"\n最低价格附近的数据（前后10分钟）:")
    start_idx = max(data.index[0], min_idx - pd.Timedelta(minutes=10))
    end_idx = min(data.index[-1], min_idx + pd.Timedelta(minutes=10))
    sample = data.loc[start_idx:end_idx, ['low', 'high', 'close']]
    print(sample)
    
    # 检查是否有价格低于107K（网格底部）
    below_support = data[data['low'] < 107000]
    if len(below_support) > 0:
        print(f"\n发现价格跌破网格底部107K的记录:")
        print(f"  共{len(below_support)}根K线最低价低于107K")
        print(f"  最低价格: ${below_support['low'].min():,.2f}")
        print(f"  最低价格时间: {below_support.loc[below_support['low'].idxmin()].name}")
        
        print(f"\n价格低于107K的K线样本（前10根）:")
        print(below_support[['low', 'high', 'close']].head(10))
        
        # 分析价格在低位的停留时间
        below_107k_duration = len(below_support)
        print(f"\n价格在107K以下停留时间: {below_107k_duration}分钟")
        
        # 检查价格在101K附近的持续时间
        near_101k = data[(data['low'] >= 100000) & (data['low'] <= 103000)]
        print(f"价格在101K-103K区间的K线数: {len(near_101k)}分钟")
        
        if len(near_101k) > 0:
            print(f"价格在101K附近的时间范围:")
            print(f"  开始: {near_101k.index.min()}")
            print(f"  结束: {near_101k.index.max()}")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
