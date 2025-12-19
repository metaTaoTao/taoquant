"""
检查杠杆使用率和库存管理逻辑。
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
    
    # 手动运行，记录杠杆使用率和库存状态
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 17, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    leverage_stats = {
        'max_leverage_used': 0.0,
        'avg_leverage_used': 0.0,
        'leverage_samples': [],
        'inventory_ratio_samples': [],
        'order_blocks': {
            'inventory': 0,
            'breakout': 0,
            'trend': 0,
            'funding': 0,
            'throttle': 0,
        },
    }
    
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
        
        # 计算杠杆使用率
        position_notional = abs(runner.holdings * row['close'])
        max_notional = current_equity * config.leverage
        leverage_used = (position_notional / current_equity) if current_equity > 0 else 0.0
        leverage_stats['leverage_samples'].append(leverage_used)
        leverage_stats['max_leverage_used'] = max(leverage_stats['max_leverage_used'], leverage_used)
        
        # 计算库存比例
        inventory_state = runner.algorithm.grid_manager.inventory_tracker.get_state()
        inv_ratio = (abs(float(runner.holdings)) * float(row['close']) / float(current_equity)) if current_equity > 0 else 0.0
        inv_ratio_threshold = float(config.inventory_capacity_threshold_pct) * float(config.leverage)
        leverage_stats['inventory_ratio_samples'].append({
            'inv_ratio': inv_ratio,
            'threshold': inv_ratio_threshold,
            'blocked': inv_ratio >= inv_ratio_threshold,
        })
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            if order['quantity'] == 0:
                reason = order.get('reason', 'Unknown')
                if 'Inventory' in reason:
                    leverage_stats['order_blocks']['inventory'] += 1
                elif 'Breakout' in reason:
                    leverage_stats['order_blocks']['breakout'] += 1
                elif 'trend' in reason.lower():
                    leverage_stats['order_blocks']['trend'] += 1
                elif 'Funding' in reason:
                    leverage_stats['order_blocks']['funding'] += 1
                elif 'throttle' in reason.lower():
                    leverage_stats['order_blocks']['throttle'] += 1
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
        
        if i % 500 == 0:
            print(f"处理了 {i-100} 根K线...")
    
    # 计算平均杠杆使用率
    if leverage_stats['leverage_samples']:
        leverage_stats['avg_leverage_used'] = sum(leverage_stats['leverage_samples']) / len(leverage_stats['leverage_samples'])
    
    print("\n" + "=" * 80)
    print("杠杆使用率和库存管理分析")
    print("=" * 80)
    print(f"最大杠杆使用率: {leverage_stats['max_leverage_used']:.2f}x")
    print(f"平均杠杆使用率: {leverage_stats['avg_leverage_used']:.2f}x")
    print(f"配置杠杆: {config.leverage}x")
    
    # 检查库存比例
    blocked_count = sum(1 for s in leverage_stats['inventory_ratio_samples'] if s['blocked'])
    print(f"\n库存比例分析:")
    print(f"  库存比例超过阈值的次数: {blocked_count}/{len(leverage_stats['inventory_ratio_samples'])}")
    if leverage_stats['inventory_ratio_samples']:
        max_inv_ratio = max(s['inv_ratio'] for s in leverage_stats['inventory_ratio_samples'])
        avg_inv_ratio = sum(s['inv_ratio'] for s in leverage_stats['inventory_ratio_samples']) / len(leverage_stats['inventory_ratio_samples'])
        print(f"  最大库存比例: {max_inv_ratio:.2f}")
        print(f"  平均库存比例: {avg_inv_ratio:.2f}")
        print(f"  库存阈值: {leverage_stats['inventory_ratio_samples'][0]['threshold']:.2f}")
    
    print(f"\n订单被阻止的原因:")
    for reason, count in leverage_stats['order_blocks'].items():
        if count > 0:
            print(f"  {reason}: {count}次")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()

