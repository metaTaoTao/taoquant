"""
检查卖出订单触发和执行逻辑。
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
    
    # 只运行前2000根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 14, 0, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，记录卖出订单触发和执行情况
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 14, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    sell_order_stats = {
        'price_touches': 0,
        'orders_triggered': 0,
        'orders_size_zero': 0,
        'orders_executed': 0,
        'orders_failed': 0,
        'no_inventory_blocks': 0,
        'insufficient_holdings_blocks': 0,
    }
    
    sell_levels = runner.algorithm.grid_manager.sell_levels
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 2100:
            break
        
        # 检查价格是否触及卖出网格价格
        bar_high = row['high']
        bar_low = row['low']
        for sell_price in sell_levels:
            if bar_low <= sell_price <= bar_high:
                sell_order_stats['price_touches'] += 1
                break
        
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
        
        # 检查卖出订单触发条件
        inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
        if inventory_state.long_exposure <= 0:
            sell_order_stats['no_inventory_blocks'] += 1
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        
        # 循环处理所有订单
        max_orders_per_bar = 20
        orders_processed_this_bar = 0
        
        while orders_processed_this_bar < max_orders_per_bar:
            # 更新portfolio_state
            current_equity = runner.cash + (runner.holdings * row['close'])
            current_value = runner.holdings * row['close']
            unrealized_pnl = current_value - runner.total_cost_basis
            portfolio_state = {
                'equity': current_equity,
                'cash': runner.cash,
                'holdings': runner.holdings,
                'unrealized_pnl': unrealized_pnl,
            }
            
            order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
            
            if order:
                orders_processed_this_bar += 1
                
                if order['direction'] == 'sell':
                    sell_order_stats['orders_triggered'] += 1
                    
                    if order['quantity'] == 0:
                        sell_order_stats['orders_size_zero'] += 1
                    else:
                        # 检查执行条件
                        if order['quantity'] > runner.holdings:
                            sell_order_stats['insufficient_holdings_blocks'] += 1
                        
                        executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                        if executed:
                            sell_order_stats['orders_executed'] += 1
                            runner.algorithm.on_order_filled(order)
                        else:
                            sell_order_stats['orders_failed'] += 1
                else:
                    # 买入订单
                    executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                    if executed:
                        runner.algorithm.on_order_filled(order)
            else:
                break
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("卖出订单触发和执行分析")
    print("=" * 80)
    print(f"价格触及卖出网格次数: {sell_order_stats['price_touches']}")
    print(f"卖出订单触发次数: {sell_order_stats['orders_triggered']}")
    print(f"卖出订单大小为0: {sell_order_stats['orders_size_zero']}")
    print(f"卖出订单执行成功: {sell_order_stats['orders_executed']}")
    print(f"卖出订单执行失败: {sell_order_stats['orders_failed']}")
    print(f"无库存阻止: {sell_order_stats['no_inventory_blocks']}")
    print(f"holdings不足阻止: {sell_order_stats['insufficient_holdings_blocks']}")
    
    print(f"\n分析:")
    if sell_order_stats['price_touches'] > 0:
        print(f"  价格触及率: {sell_order_stats['orders_triggered']/sell_order_stats['price_touches']*100:.2f}%")
    if sell_order_stats['orders_triggered'] > 0:
        print(f"  订单执行率: {sell_order_stats['orders_executed']/sell_order_stats['orders_triggered']*100:.2f}%")
    
    print(f"\n最终状态:")
    print(f"  holdings: {runner.holdings:.4f}")
    inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
    print(f"  long_exposure: {inventory_state.long_exposure:.4f}")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()
