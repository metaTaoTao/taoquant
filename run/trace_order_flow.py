"""
追踪订单流程，找出为什么只有17笔交易。
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
stats = {
    'bars_processed': 0,
    'orders_triggered': 0,
    'orders_size_zero': 0,
    'orders_executed': 0,
    'orders_failed': 0,
    'triggered_but_blocked': 0,
    'price_touches': 0,
}

def main():
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        enable_console_log=False,  # 关闭详细日志，只统计
    )
    
    # 只运行第一天，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 27, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行回测，统计每一步
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 27, tzinfo=timezone.utc),
        historical_data
    )
    
    print("=" * 80)
    print("追踪订单流程")
    print("=" * 80)
    print(f"初始pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    print(f"买入层数: {len(runner.algorithm.grid_manager.buy_levels)}")
    print(f"卖出层数: {len(runner.algorithm.grid_manager.sell_levels)}")
    print()
    
    # 统计价格触及
    buy_levels = runner.algorithm.grid_manager.buy_levels
    sell_levels = runner.algorithm.grid_manager.sell_levels
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:  # 跳过初始化用的数据
            continue
        
        stats['bars_processed'] += 1
        
        bar_high = row['high']
        bar_low = row['low']
        current_price = row['close']
        
        # 检查价格是否触及网格价格
        for buy_price in buy_levels:
            if bar_low <= buy_price <= bar_high:
                stats['price_touches'] += 1
                break
        
        for sell_price in sell_levels:
            if bar_low <= sell_price <= bar_high:
                stats['price_touches'] += 1
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
        
        # 检查订单触发
        runner.algorithm._current_bar_index = i
        triggered_order = runner.algorithm.grid_manager.check_pending_order_triggers(
            current_price=current_price,
            prev_price=getattr(runner.algorithm, '_prev_price', None),
            bar_high=bar_high,
            bar_low=bar_low,
            bar_index=i,
        )
        
        if triggered_order:
            stats['orders_triggered'] += 1
            
            # 计算订单大小
            direction = triggered_order['direction']
            level_index = triggered_order['level_index']
            level_price = triggered_order['price']
            
            size, throttle_status = runner.algorithm.grid_manager.calculate_order_size(
                direction=direction,
                level_index=level_index,
                level_price=level_price,
                equity=current_equity,
                daily_pnl=runner.algorithm.daily_pnl,
                risk_budget=runner.algorithm.risk_budget,
                holdings_btc=runner.holdings,
                current_price=current_price,
                mr_z=bar_data.get('mr_z'),
                trend_score=bar_data.get('trend_score'),
                breakout_risk_down=bar_data.get('breakout_risk_down'),
                breakout_risk_up=bar_data.get('breakout_risk_up'),
                range_pos=bar_data.get('range_pos'),
                funding_rate=bar_data.get('funding_rate'),
                minutes_to_funding=bar_data.get('minutes_to_funding'),
                vol_score=bar_data.get('vol_score'),
            )
            
            if size == 0:
                stats['orders_size_zero'] += 1
                stats['triggered_but_blocked'] += 1
            else:
                # 尝试执行订单
                order = {
                    'direction': direction,
                    'quantity': size,
                    'price': level_price,
                    'level': level_index,
                }
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                
                if executed:
                    stats['orders_executed'] += 1
                    runner.algorithm.on_order_filled(order)
                else:
                    stats['orders_failed'] += 1
        
        # 处理订单（正常流程）
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        if order:
            executed = runner.execute_order(order, row['open'], row['close'], timestamp)
            if executed:
                runner.algorithm.on_order_filled(order)
        
        # 更新equity
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
        
        if stats['bars_processed'] % 1000 == 0:
            print(f"处理了 {stats['bars_processed']} 根K线...")
    
    print("\n" + "=" * 80)
    print("统计结果")
    print("=" * 80)
    print(f"处理的K线数: {stats['bars_processed']}")
    print(f"价格触及网格次数: {stats['price_touches']}")
    print(f"订单触发次数: {stats['orders_triggered']}")
    print(f"订单大小为0的次数: {stats['orders_size_zero']}")
    print(f"订单执行成功次数: {stats['orders_executed']}")
    print(f"订单执行失败次数: {stats['orders_failed']}")
    print(f"触发但被阻止的次数: {stats['triggered_but_blocked']}")
    print(f"\n触发率: {stats['orders_triggered']/stats['price_touches']*100:.2f}%" if stats['price_touches'] > 0 else "N/A")
    print(f"执行率: {stats['orders_executed']/stats['orders_triggered']*100:.2f}%" if stats['orders_triggered'] > 0 else "N/A")

if __name__ == "__main__":
    main()

