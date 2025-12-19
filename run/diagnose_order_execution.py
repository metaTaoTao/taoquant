"""
诊断订单执行问题：检查订单触发、执行和填充的完整流程
"""

import sys
import io
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# Set UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig
from data import DataManager

def main():
    print("=" * 80)
    print("订单执行诊断")
    print("=" * 80)
    print()
    
    # 使用相同的配置
    config = TaoGridLeanConfig(
        name="TaoGrid Optimized - Max ROE (Perp)",
        description="Inventory-aware grid (perp maker fee 0.02%), focus on max ROE",
        support=107000.0,
        resistance=123000.0,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        enable_mr_trend_factor=False,
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=50.0,
        enable_funding_factor=False,
        enable_mm_risk_zone=False,
        enable_console_log=True,
    )
    
    # 创建 runner
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        verbose=False,
    )
    
    # 加载数据
    print("加载数据...")
    data = runner.load_data()
    print(f"数据条数: {len(data)}")
    print()
    
    # 初始化算法
    print("初始化算法...")
    historical_data = data.head(100)
    runner.algorithm.initialize(
        symbol=runner.symbol,
        start_date=runner.start_date,
        end_date=runner.end_date,
        historical_data=historical_data,
    )
    print(f"初始 pending_orders: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    print()
    
    # 统计变量
    orders_triggered = 0
    orders_executed = 0
    orders_failed = 0
    buy_orders_triggered = 0
    sell_orders_triggered = 0
    buy_orders_executed = 0
    sell_orders_executed = 0
    
    failure_reasons = {}
    
    # 只检查前1000根K线，避免输出过多
    check_bars = min(1000, len(data))
    print(f"检查前 {check_bars} 根K线的订单执行情况...")
    print()
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i >= check_bars:
            break
        
        # 设置当前 bar index
        runner.algorithm._current_bar_index = i
        
        # 准备 bar data
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
        
        # 准备 portfolio state
        current_equity = runner.cash + (runner.holdings * row['close'])
        current_value = runner.holdings * row['close']
        unrealized_pnl = current_value - runner.total_cost_basis
        portfolio_state = {
            'equity': current_equity,
            'cash': runner.cash,
            'holdings': runner.holdings,
            'unrealized_pnl': unrealized_pnl,
        }
        
        # 调用 on_data
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            orders_triggered += 1
            direction = order['direction']
            size = order['quantity']
            
            if direction == 'buy':
                buy_orders_triggered += 1
            else:
                sell_orders_triggered += 1
            
            # 尝试执行订单
            executed = runner.execute_order(
                order, 
                bar_open=row['open'], 
                market_price=row['close'], 
                timestamp=timestamp
            )
            
            if executed:
                orders_executed += 1
                if direction == 'buy':
                    buy_orders_executed += 1
                else:
                    sell_orders_executed += 1
                
                # 调用 on_order_filled
                runner.algorithm.on_order_filled(order)
                
                if direction == 'sell':
                    runner.algorithm.grid_manager.match_sell_order(
                        sell_level_index=order['level'],
                        sell_size=order['quantity']
                    )
            else:
                orders_failed += 1
                # 分析失败原因
                reason = "unknown"
                if direction == 'buy':
                    # 检查杠杆限制
                    equity = portfolio_state['equity']
                    max_notional = equity * config.leverage
                    new_notional = (runner.holdings + size) * row['close']
                    if new_notional > max_notional:
                        reason = "leverage_limit"
                    elif runner.cash < size * order['price']:
                        reason = "insufficient_cash"
                    else:
                        reason = "other"
                else:  # sell
                    if runner.holdings < size:
                        reason = "insufficient_holdings"
                    else:
                        reason = "other"
                
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    
    print("=" * 80)
    print("诊断结果")
    print("=" * 80)
    print()
    print(f"检查的K线数: {check_bars}")
    print(f"订单触发数: {orders_triggered}")
    print(f"  - 买入订单触发: {buy_orders_triggered}")
    print(f"  - 卖出订单触发: {sell_orders_triggered}")
    print()
    print(f"订单执行数: {orders_executed}")
    print(f"  - 买入订单执行: {buy_orders_executed}")
    print(f"  - 卖出订单执行: {sell_orders_executed}")
    print()
    print(f"订单失败数: {orders_failed}")
    print(f"失败原因分布:")
    for reason, count in failure_reasons.items():
        print(f"  - {reason}: {count}")
    print()
    
    if orders_triggered > 0:
        execution_rate = orders_executed / orders_triggered * 100
        print(f"订单执行率: {execution_rate:.2f}%")
    else:
        print("⚠️  没有订单被触发！")
        print()
        print("可能的原因:")
        print("1. 网格价格没有覆盖实际价格范围")
        print("2. filled_levels 阻止了订单触发")
        print("3. 订单被风险因子阻止（size=0）")
        print("4. 卖出订单没有持仓（long_exposure=0）")
    
    print("=" * 80)

if __name__ == "__main__":
    main()

