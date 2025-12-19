"""
分析订单触发逻辑，找出为什么只有17笔交易。
关键问题：为什么19,882次价格触及只触发了17笔交易？
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
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.helpers.grid_manager import GridManager

def main():
    print("=" * 80)
    print("分析订单触发逻辑")
    print("=" * 80)
    
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
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
    
    # 初始化grid manager
    grid_manager = GridManager(config)
    historical_data = data.head(100)
    grid_manager.setup_grid(historical_data)
    
    print(f"\n初始状态:")
    print(f"  买入层数: {len(grid_manager.buy_levels)}")
    print(f"  卖出层数: {len(grid_manager.sell_levels)}")
    print(f"  初始pending订单数: {len(grid_manager.pending_limit_orders)}")
    
    # 统计
    stats = {
        'total_bars': 0,
        'price_touches': 0,
        'orders_checked': 0,
        'orders_triggered': 0,
        'orders_skipped_triggered': 0,
        'orders_skipped_last_checked': 0,
        'orders_skipped_not_placed': 0,
        'orders_not_touched': 0,
        'sell_orders_no_inventory': 0,
    }
    
    # 模拟检查过程（只检查前1000根K线，便于分析）
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 1100:  # 只检查前1000根K线
            break
        
        stats['total_bars'] += 1
        bar_high = row['high']
        bar_low = row['low']
        current_price = row['close']
        
        # 检查每个pending订单
        for order in grid_manager.pending_limit_orders:
            stats['orders_checked'] += 1
            
            # 检查是否跳过
            if not order.get('placed', False):
                stats['orders_skipped_not_placed'] += 1
                continue
            
            if order.get('triggered', False):
                stats['orders_skipped_triggered'] += 1
                continue
            
            # 检查last_checked_bar
            if order.get('last_checked_bar') == i:
                stats['orders_skipped_last_checked'] += 1
                continue
            
            direction = order['direction']
            limit_price = order['price']
            
            # 检查价格是否触及
            if bar_low is not None and bar_high is not None:
                touched = (bar_low <= limit_price <= bar_high)
            else:
                touched = False
            
            if touched:
                stats['price_touches'] += 1
                
                # 对于卖出订单，检查是否有库存
                if direction == 'sell':
                    inventory_state = grid_manager.inventory_tracker.get_state()
                    if inventory_state.long_exposure <= 0:
                        stats['sell_orders_no_inventory'] += 1
                        continue
                
                # 订单应该被触发
                stats['orders_triggered'] += 1
                
                # 模拟触发：标记为triggered
                order['triggered'] = True
                order['last_checked_bar'] = i
            else:
                stats['orders_not_touched'] += 1
    
    print(f"\n统计结果（前1000根K线）:")
    print(f"  总K线数: {stats['total_bars']}")
    print(f"  订单检查次数: {stats['orders_checked']}")
    print(f"  价格触及次数: {stats['price_touches']}")
    print(f"  订单触发次数: {stats['orders_triggered']}")
    print(f"  跳过（已触发）: {stats['orders_skipped_triggered']}")
    print(f"  跳过（last_checked_bar）: {stats['orders_skipped_last_checked']}")
    print(f"  跳过（未放置）: {stats['orders_skipped_not_placed']}")
    print(f"  未触及: {stats['orders_not_touched']}")
    print(f"  卖出订单无库存: {stats['sell_orders_no_inventory']}")
    
    print(f"\n分析:")
    print(f"  平均每根K线检查订单数: {stats['orders_checked']/stats['total_bars']:.1f}")
    print(f"  价格触及率: {stats['price_touches']/stats['orders_checked']*100:.2f}%")
    print(f"  订单触发率: {stats['orders_triggered']/stats['price_touches']*100:.2f}%" if stats['price_touches'] > 0 else "N/A")
    
    # 检查pending订单状态
    print(f"\n当前pending订单状态:")
    triggered_count = sum(1 for o in grid_manager.pending_limit_orders if o.get('triggered', False))
    print(f"  总订单数: {len(grid_manager.pending_limit_orders)}")
    print(f"  已触发订单数: {triggered_count}")
    print(f"  未触发订单数: {len(grid_manager.pending_limit_orders) - triggered_count}")

if __name__ == "__main__":
    main()

