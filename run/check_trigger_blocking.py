"""
检查订单触发被阻止的原因。
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

from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig

def main():
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        leverage=50.0,
        enable_console_log=False,
    )
    
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 17, 0, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 17, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    stats = {
        'total_checks': 0,
        'skipped_not_placed': 0,
        'skipped_triggered': 0,
        'skipped_last_checked': 0,
        'touched': 0,
        'not_touched': 0,
        'sell_no_inventory': 0,
        'triggered': 0,
    }
    
    buy_levels = runner.algorithm.grid_manager.buy_levels
    sell_levels = runner.algorithm.grid_manager.sell_levels
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 200:  # 只检查前100根K线
            break
        
        bar_high = row['high']
        bar_low = row['low']
        current_price = row['close']
        
        # 检查每个pending订单
        for order in runner.algorithm.grid_manager.pending_limit_orders:
            stats['total_checks'] += 1
            
            if not order.get('placed', False):
                stats['skipped_not_placed'] += 1
                continue
            
            if order.get('triggered', False):
                stats['skipped_triggered'] += 1
                continue
            
            if order.get('last_checked_bar') == i:
                stats['skipped_last_checked'] += 1
                continue
            
            direction = order['direction']
            limit_price = order['price']
            
            # 检查价格是否触及
            if bar_low is not None and bar_high is not None:
                touched = (bar_low <= limit_price <= bar_high)
            else:
                touched = False
            
            if touched:
                stats['touched'] += 1
                
                # 对于卖出订单，检查是否有库存
                if direction == 'sell':
                    inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
                    if inventory_state.long_exposure <= 0:
                        stats['sell_no_inventory'] += 1
                        continue
                
                stats['triggered'] += 1
            else:
                stats['not_touched'] += 1
    
    print("=" * 80)
    print("订单触发检查统计")
    print("=" * 80)
    print(f"总检查次数: {stats['total_checks']}")
    print(f"跳过（未放置）: {stats['skipped_not_placed']}")
    print(f"跳过（已触发）: {stats['skipped_triggered']}")
    print(f"跳过（last_checked_bar）: {stats['skipped_last_checked']}")
    print(f"价格触及: {stats['touched']}")
    print(f"价格未触及: {stats['not_touched']}")
    print(f"卖出订单无库存: {stats['sell_no_inventory']}")
    print(f"最终触发: {stats['triggered']}")
    
    print(f"\n分析:")
    if stats['total_checks'] > 0:
        print(f"  跳过（已触发）比例: {stats['skipped_triggered']/stats['total_checks']*100:.2f}%")
        print(f"  价格触及比例: {stats['touched']/stats['total_checks']*100:.2f}%")
        print(f"  触发比例: {stats['triggered']/stats['total_checks']*100:.2f}%")
    
    if stats['skipped_triggered'] > stats['triggered'] * 10:
        print(f"\n  ⚠️  关键问题：跳过（已触发）的数量远大于触发数量！")
        print(f"  这说明订单被触发后，triggered标志没有被正确重置，")
        print(f"  导致订单无法再次触发。")

if __name__ == "__main__":
    main()

