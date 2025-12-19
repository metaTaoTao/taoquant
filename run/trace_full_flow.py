"""
完整追踪订单流程，找出为什么只有6笔交易。
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

# 统计变量
class Stats:
    def __init__(self):
        self.bars = 0
        self.price_touches = 0
        self.orders_checked = 0
        self.orders_triggered = 0
        self.orders_size_zero = 0
        self.orders_executed = 0
        self.orders_failed = 0
        self.triggered_but_skipped = 0
        
stats = Stats()

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
    
    # 只运行前2000根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 14, 0, tzinfo=timezone.utc),  # 约2000根K线
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，统计每一步
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 14, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    buy_levels = runner.algorithm.grid_manager.buy_levels
    sell_levels = runner.algorithm.grid_manager.sell_levels
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 2100:
            break
        
        stats.bars += 1
        
        # 统计价格触及
        bar_high = row['high']
        bar_low = row['low']
        for buy_price in buy_levels:
            if bar_low <= buy_price <= bar_high:
                stats.price_touches += 1
                break
        for sell_price in sell_levels:
            if bar_low <= sell_price <= bar_high:
                stats.price_touches += 1
                break
        
        # 检查订单触发
        for order in runner.algorithm.grid_manager.pending_limit_orders:
            stats.orders_checked += 1
            
            if not order.get('placed', False):
                continue
            
            if order.get('triggered', False):
                stats.triggered_but_skipped += 1
                continue
            
            if order.get('last_checked_bar') == i:
                continue
            
            direction = order['direction']
            limit_price = order['price']
            
            if bar_low is not None and bar_high is not None:
                touched = (bar_low <= limit_price <= bar_high)
            else:
                touched = False
            
            if touched:
                if direction == 'sell':
                    inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
                    if inventory_state.long_exposure <= 0:
                        continue
                
                stats.orders_triggered += 1
        
        # 准备数据
        bar_data = {
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'trend_score': row.get('trend_score', 0.0),
            'mr_z': row.get('mr_z', 0.0),
            'breakout_risk_down': row.get('breakout_risk_down', 0.0),
            'breakout_risk_up': row.get('breakout_risk_up', 0.0),
            'range_pos': row.get('range_pos', 0.5),
            'vol_score': row.get('vol_score', 0.0),
            'funding_rate': row.get('funding_rate', 0.0),
            'minutes_to_funding': row.get('minutes_to_funding', 0.0),
        }
        
        current_equity = runner.cash + (runner.holdings * row['close'])
        current_value = runner.holdings * row['close']
        unrealized_pnl = current_value - runner.total_cost_basis
        portfolio_state = {
            'equity': current_equity,
            'cash': runner.cash,
            'holdings': runner.holdings,
            'unrealized_pnl': unrealized_pnl,
        }
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            if order['quantity'] == 0:
                stats.orders_size_zero += 1
            else:
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                if executed:
                    stats.orders_executed += 1
                    runner.algorithm.on_order_filled(order)
                else:
                    stats.orders_failed += 1
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
        
        if stats.bars % 500 == 0:
            print(f"处理了 {stats.bars} 根K线...")
    
    print("\n" + "=" * 80)
    print("完整流程统计")
    print("=" * 80)
    print(f"处理的K线数: {stats.bars}")
    print(f"价格触及次数: {stats.price_touches}")
    print(f"订单检查次数: {stats.orders_checked}")
    print(f"订单触发次数: {stats.orders_triggered}")
    print(f"跳过（已触发）: {stats.triggered_but_skipped}")
    print(f"订单大小为0的次数: {stats.orders_size_zero}")
    print(f"订单执行成功次数: {stats.orders_executed}")
    print(f"订单执行失败次数: {stats.orders_failed}")
    
    print(f"\n分析:")
    if stats.price_touches > 0:
        print(f"  价格触及率: {stats.orders_triggered/stats.price_touches*100:.2f}%")
    if stats.orders_triggered > 0:
        print(f"  订单执行率: {stats.orders_executed/stats.orders_triggered*100:.2f}%")
        print(f"  订单大小为0的比例: {stats.orders_size_zero/stats.orders_triggered*100:.2f}%")
        print(f"  跳过（已触发）的比例: {stats.triggered_but_skipped/stats.orders_checked*100:.2f}%")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")
    print(f"  Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")

if __name__ == "__main__":
    main()

