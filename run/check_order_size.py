"""
检查订单大小计算，看看为什么订单执行失败
"""

import sys
import io
from pathlib import Path
from datetime import datetime, timezone

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
    print("订单大小检查")
    print("=" * 80)
    print()
    
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
        enable_console_log=False,  # 关闭日志，只看关键信息
    )
    
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        verbose=False,
    )
    
    # 加载数据
    data = runner.load_data()
    
    # 初始化算法
    historical_data = data.head(100)
    runner.algorithm.initialize(
        symbol=runner.symbol,
        start_date=runner.start_date,
        end_date=runner.end_date,
        historical_data=historical_data,
    )
    
    # 检查前10个订单
    order_count = 0
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if order_count >= 10:
            break
        
        runner.algorithm._current_bar_index = i
        
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
        
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            order_count += 1
            direction = order['direction']
            size = order['quantity']
            price = order['price']
            
            print(f"\n订单 #{order_count} @ {timestamp}")
            print(f"  方向: {direction.upper()}")
            print(f"  价格: ${price:,.2f}")
            print(f"  大小: {size:.6f} BTC")
            print(f"  当前现金: ${runner.cash:,.2f}")
            print(f"  当前持仓: {runner.holdings:.6f} BTC")
            print(f"  当前权益: ${current_equity:,.2f}")
            
            if direction == 'buy':
                cost = size * price
                commission = cost * config.maker_fee
                total_cost = cost + commission
                print(f"  订单成本: ${total_cost:,.2f} (价格 ${cost:,.2f} + 手续费 ${commission:,.2f})")
                
                max_notional = current_equity * config.leverage
                new_notional = abs(runner.holdings + size) * row['close']
                print(f"  最大名义价值: ${max_notional:,.2f} (权益 ${current_equity:,.2f} × 杠杆 {config.leverage}x)")
                print(f"  新名义价值: ${new_notional:,.2f}")
                
                if new_notional > max_notional:
                    print(f"  ❌ 超过杠杆限制")
                elif runner.cash < total_cost:
                    print(f"  ❌ 现金不足 (需要 ${total_cost:,.2f}, 只有 ${runner.cash:,.2f})")
                else:
                    print(f"  ✅ 可以执行")
            
            # 尝试执行
            executed = runner.execute_order(
                order, 
                bar_open=row['open'], 
                market_price=row['close'], 
                timestamp=timestamp
            )
            
            if executed:
                print(f"  ✅ 执行成功")
            else:
                print(f"  ❌ 执行失败")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

