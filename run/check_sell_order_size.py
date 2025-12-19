"""
检查卖出订单大小计算逻辑。
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
        enable_console_log=True,  # 启用详细日志
    )
    
    # 只运行前1000根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 17, 0, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，记录卖出订单大小计算过程
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 17, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    sell_order_details = []
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 1100:
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
                    # 记录卖出订单详情
                    inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
                    sell_order_details.append({
                        'bar': i,
                        'timestamp': timestamp,
                        'level': order['level'],
                        'price': order['price'],
                        'size': order['quantity'],
                        'holdings': runner.holdings,
                        'long_exposure': inventory_state.long_exposure,
                        'available_holdings': max(runner.holdings, inventory_state.long_exposure),
                        'reason': order.get('reason', ''),
                    })
                
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                if executed:
                    runner.algorithm.on_order_filled(order)
            else:
                break
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("卖出订单大小分析")
    print("=" * 80)
    print(f"卖出订单数: {len(sell_order_details)}")
    
    if sell_order_details:
        print(f"\n卖出订单详情（前20个）:")
        for i, detail in enumerate(sell_order_details[:20]):
            print(f"  {i+1}. Bar {detail['bar']} @ {detail['timestamp']}")
            print(f"     SELL L{detail['level']+1} @ ${detail['price']:,.2f}, size={detail['size']:.4f}")
            print(f"     holdings={detail['holdings']:.4f}, long_exposure={detail['long_exposure']:.4f}")
            print(f"     available_holdings={detail['available_holdings']:.4f}")
            if detail['size'] == 0:
                print(f"     原因: {detail['reason']}")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()

