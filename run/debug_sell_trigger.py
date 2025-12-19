"""
详细调试卖出订单触发逻辑。
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
    
    # 只运行前500根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，详细记录卖出订单触发检查
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    sell_trigger_details = []
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 600:
            break
        
        bar_high = row['high']
        bar_low = row['low']
        current_price = row['close']
        
        # 检查每个卖出pending订单
        for order in runner.algorithm.grid_manager.pending_limit_orders:
            if order['direction'] != 'sell':
                continue
            
            if not order.get('placed', False):
                continue
            
            if order.get('triggered', False):
                continue
            
            if order.get('last_checked_bar') == i:
                continue
            
            limit_price = order['price']
            level_index = order['level_index']
            
            # 检查价格是否触及
            if bar_low is not None and bar_high is not None:
                touched = (bar_low <= limit_price <= bar_high)
            else:
                touched = False
            
            if touched:
                # 检查库存
                inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
                
                sell_trigger_details.append({
                    'bar': i,
                    'timestamp': timestamp,
                    'level': level_index,
                    'price': limit_price,
                    'current_price': current_price,
                    'bar_range': f"{bar_low:.2f}-{bar_high:.2f}",
                    'long_exposure': inventory_state.long_exposure,
                    'holdings': runner.holdings,
                    'should_trigger': inventory_state.long_exposure > 0,
                })
        
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
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                if executed:
                    runner.algorithm.on_order_filled(order)
            else:
                break
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("卖出订单触发详细分析")
    print("=" * 80)
    print(f"价格触及且应该触发的次数: {len(sell_trigger_details)}")
    
    if sell_trigger_details:
        print(f"\n前10个应该触发但未触发的情况:")
        for i, detail in enumerate(sell_trigger_details[:10]):
            print(f"  {i+1}. Bar {detail['bar']} @ {detail['timestamp']}")
            print(f"     SELL L{detail['level']+1} @ ${detail['price']:,.2f}")
            print(f"     当前价格: ${detail['current_price']:,.2f}, K线范围: {detail['bar_range']}")
            print(f"     long_exposure: {detail['long_exposure']:.4f}, holdings: {detail['holdings']:.4f}")
            print(f"     应该触发: {detail['should_trigger']}")
    
    print(f"\n最终状态:")
    print(f"  holdings: {runner.holdings:.4f}")
    inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
    print(f"  long_exposure: {inventory_state.long_exposure:.4f}")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()

