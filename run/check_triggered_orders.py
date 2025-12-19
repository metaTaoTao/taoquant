"""
检查triggered订单的状态，找出为什么订单无法再次触发。
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
        enable_console_log=False,
    )
    
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 27, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 运行回测，但记录triggered订单的状态
    triggered_orders_history = []
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 200:  # 只检查前100根K线
            break
        
        # 准备bar数据
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
        
        # 准备portfolio state
        current_equity = runner.cash + (runner.holdings * row['close'])
        current_value = runner.holdings * row['close']
        unrealized_pnl = current_value - runner.total_cost_basis
        portfolio_state = {
            'equity': current_equity,
            'cash': runner.cash,
            'holdings': runner.holdings,
            'unrealized_pnl': unrealized_pnl,
        }
        
        # 记录triggered订单的状态
        triggered_count = sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o.get('triggered', False))
        if triggered_count > 0:
            triggered_orders_history.append({
                'bar': i,
                'timestamp': timestamp,
                'triggered_count': triggered_count,
                'pending_count': len(runner.algorithm.grid_manager.pending_limit_orders),
            })
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            executed = runner.execute_order(order, row['open'], row['close'], timestamp)
            if executed:
                runner.algorithm.on_order_filled(order)
        
        # 更新equity
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("Triggered订单状态历史")
    print("=" * 80)
    if triggered_orders_history:
        print(f"发现 {len(triggered_orders_history)} 个时间点有triggered订单")
        for entry in triggered_orders_history[:10]:
            print(f"  Bar {entry['bar']} @ {entry['timestamp']}: {entry['triggered_count']}/{entry['pending_count']} 订单处于triggered状态")
    else:
        print("没有发现triggered订单")
    
    # 检查最终状态
    print(f"\n最终状态:")
    print(f"  Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    triggered_count = sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o.get('triggered', False))
    print(f"  Triggered订单数: {triggered_count}")
    print(f"  未触发订单数: {len(runner.algorithm.grid_manager.pending_limit_orders) - triggered_count}")

if __name__ == "__main__":
    main()

