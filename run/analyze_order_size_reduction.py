"""
分析订单大小被减少的原因。
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
    
    # 手动运行，记录订单大小计算过程
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    order_size_stats = {
        'total_orders': 0,
        'size_zero': 0,
        'size_reduced': 0,
        'size_normal': 0,
        'reasons': {},
    }
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 600:
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
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            order_size_stats['total_orders'] += 1
            
            if order['quantity'] == 0:
                order_size_stats['size_zero'] += 1
                reason = order.get('reason', 'Unknown')
                order_size_stats['reasons'][reason] = order_size_stats['reasons'].get(reason, 0) + 1
            else:
                # 检查订单大小是否被减少
                # 计算基础订单大小（不考虑因子）
                direction = order['direction']
                level_index = order['level']
                level_price = order['price']
                
                if direction == 'buy':
                    weight = runner.algorithm.grid_manager.buy_weights[level_index]
                else:
                    weight = runner.algorithm.grid_manager.sell_weights[level_index]
                
                total_budget_usd = current_equity * config.risk_budget_pct
                this_level_budget_usd = total_budget_usd * weight
                base_size_btc = (this_level_budget_usd / level_price) * config.leverage
                
                if order['quantity'] < base_size_btc * 0.9:  # 如果减少了10%以上
                    order_size_stats['size_reduced'] += 1
                else:
                    order_size_stats['size_normal'] += 1
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("订单大小分析")
    print("=" * 80)
    print(f"总订单数: {order_size_stats['total_orders']}")
    print(f"订单大小为0: {order_size_stats['size_zero']}")
    print(f"订单大小被减少: {order_size_stats['size_reduced']}")
    print(f"订单大小正常: {order_size_stats['size_normal']}")
    
    if order_size_stats['reasons']:
        print(f"\n订单大小为0的原因:")
        for reason, count in sorted(order_size_stats['reasons'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}次")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()

