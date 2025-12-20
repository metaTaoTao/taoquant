"""
解释网格编号逻辑并显示详细信息

关键点：
1. L1 是最接近 mid 的层级（最高买单价位），不是最接近当前价格的
2. 从 mid 向下：L1 (最高) → L2 → L3 → ... → L15 (最低)
3. 当前价格如果高于所有买单价位，不会触发任何买单
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.helpers.grid_manager import GridManager
from data.sources.bitget_sdk import BitgetSDKDataSource


def explain_grid_numbering(config: TaoGridLeanConfig, symbol: str = "BTCUSDT", current_price: float = None):
    """
    解释网格编号逻辑
    """
    print("=" * 80)
    print("网格编号逻辑说明")
    print("=" * 80)
    print()
    print("重要概念：")
    print("  1. L1 是最接近 MID 的层级（最高买单价位），不是最接近当前价格的")
    print("  2. 网格从 MID 向下生成：L1 (最高) → L2 → L3 → ... → L15 (最低)")
    print("  3. 当前价格必须触及或低于买单价位，才会触发买单")
    print("  4. 当前价格必须触及或高于卖单价位，才会触发卖单（如果有持仓）")
    print()
    
    # 获取历史数据
    print("正在获取历史数据...")
    data_source = BitgetSDKDataSource()
    try:
        end_date = pd.Timestamp.now(tz="UTC")
        start_date = end_date - pd.Timedelta(days=7)
        historical_data = data_source.get_klines(
            symbol=symbol,
            timeframe="15m",
            start=start_date,
            end=end_date,
        )
        
        if len(historical_data) < 14:
            base_price = (config.support + config.resistance) / 2
            dates = pd.date_range(end=end_date, periods=100, freq="15min")
            historical_data = pd.DataFrame({
                'open': base_price * (1 + np.random.randn(100) * 0.01),
                'high': base_price * (1 + np.abs(np.random.randn(100)) * 0.01),
                'low': base_price * (1 - np.abs(np.random.randn(100)) * 0.01),
                'close': base_price * (1 + np.random.randn(100) * 0.01),
                'volume': np.random.rand(100) * 1000,
            }, index=dates)
        
        if current_price is None:
            latest_bar = data_source.get_latest_bar(symbol=symbol, timeframe="15m")
            if latest_bar is not None:
                current_price = latest_bar['close']
            else:
                current_price = (config.support + config.resistance) / 2
    except Exception as e:
        print(f"[ERROR] 获取数据失败: {e}")
        base_price = (config.support + config.resistance) / 2
        dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=100, freq="15min")
        historical_data = pd.DataFrame({
            'open': base_price * (1 + np.random.randn(100) * 0.01),
            'high': base_price * (1 + np.abs(np.random.randn(100)) * 0.01),
            'low': base_price * (1 - np.abs(np.random.randn(100)) * 0.01),
            'close': base_price * (1 + np.random.randn(100) * 0.01),
            'volume': np.random.rand(100) * 1000,
        }, index=dates)
        current_price = base_price
    
    # 初始化网格
    grid_manager = GridManager(config)
    grid_manager.setup_grid(historical_data)
    
    buy_levels = grid_manager.buy_levels
    sell_levels = grid_manager.sell_levels
    mid = (config.support + config.resistance) / 2
    
    print()
    print("=" * 80)
    print("网格配置信息")
    print("=" * 80)
    print(f"Support: ${config.support:,.0f}")
    print(f"Resistance: ${config.resistance:,.0f}")
    print(f"Mid: ${mid:,.0f}")
    print(f"当前价格: ${current_price:,.0f}")
    print(f"网格间距: {grid_manager.current_atr:,.2f} ATR")
    print()
    
    # 计算实际 spacing
    from analytics.indicators.grid_generator import calculate_grid_spacing
    from analytics.indicators.volatility import calculate_atr
    
    atr = calculate_atr(
        historical_data["high"],
        historical_data["low"],
        historical_data["close"],
        period=config.atr_period,
    )
    spacing_series = calculate_grid_spacing(
        atr=atr,
        min_return=config.min_return,
        maker_fee=config.maker_fee,
        slippage=0.0,
        volatility_k=config.volatility_k,
        use_limit_orders=True,
    )
    actual_spacing = spacing_series.iloc[-1] * config.spacing_multiplier
    print(f"实际网格间距: {actual_spacing:.2%}")
    print()
    
    print("=" * 80)
    print("BUY LEVELS (买单层级)")
    print("=" * 80)
    print("编号说明：L1 是最接近 MID 的层级（最高买单价位）")
    print()
    print(f"{'Level':<8} {'Price':<15} {'Distance from Mid':<25} {'Distance from Current':<25} {'Status':<20}")
    print("-" * 100)
    
    for i, price in enumerate(buy_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 判断状态
        if current_price <= price:
            status = "[可触发]"
        else:
            status = "[等待价格下跌]"
        
        marker = ""
        if i == 0:
            marker = " (最高买单价)"
        if abs(distance_from_current) == min([abs(p - current_price) for p in buy_levels]):
            marker += " [最接近当前价格]"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%)  {status:<20}{marker}")
    
    print()
    print("=" * 80)
    print("SELL LEVELS (卖单层级)")
    print("=" * 80)
    print("编号说明：L1 是最接近 MID 的层级（最低卖单价位）")
    print()
    print(f"{'Level':<8} {'Price':<15} {'Distance from Mid':<25} {'Distance from Current':<25} {'Status':<20}")
    print("-" * 100)
    
    for i, price in enumerate(sell_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 判断状态
        if current_price >= price:
            status = "[可触发(需持仓)]"
        else:
            status = "[等待价格上涨]"
        
        marker = ""
        if i == 0:
            marker = " (最低卖单价)"
        if abs(distance_from_current) == min([abs(p - current_price) for p in sell_levels]):
            marker += " [最接近当前价格]"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%)  {status:<20}{marker}")
    
    print()
    print("=" * 80)
    print("当前价格分析")
    print("=" * 80)
    
    if len(buy_levels) > 0:
        highest_buy = buy_levels[0]  # L1
        lowest_buy = buy_levels[-1]  # 最低买单价
        
        if current_price > highest_buy:
            print(f"[INFO] 当前价格 ${current_price:,.0f} 高于所有买单价位")
            print(f"       最高买单价位 (L1): ${highest_buy:,.0f}")
            print(f"       需要价格下跌 ${current_price - highest_buy:,.0f} ({((current_price - highest_buy) / current_price * 100):.2f}%) 才能触发 L1")
            print(f"       或者等待价格自然波动到买单价位附近")
        elif current_price < lowest_buy:
            print(f"[INFO] 当前价格 ${current_price:,.0f} 低于所有买单价位")
            print(f"       最低买单价位: ${lowest_buy:,.0f}")
            print(f"       当前价格已经可以触发买单，但需要价格反弹到买单价位")
        else:
            print(f"[INFO] 当前价格在买单价位范围内")
            # 找到最接近的买单价位
            closest_buy_idx = np.argmin(np.abs(buy_levels - current_price))
            closest_buy = buy_levels[closest_buy_idx]
            print(f"       最接近的买单价位: L{closest_buy_idx+1} @ ${closest_buy:,.0f}")
    
    if len(sell_levels) > 0:
        lowest_sell = sell_levels[0]  # L1
        highest_sell = sell_levels[-1]  # 最高卖单价
        
        if current_price < lowest_sell:
            print(f"[INFO] 当前价格 ${current_price:,.0f} 低于所有卖单价位")
            print(f"       最低卖单价位 (L1): ${lowest_sell:,.0f}")
            print(f"       需要价格上涨 ${lowest_sell - current_price:,.0f} ({((lowest_sell - current_price) / current_price * 100):.2f}%) 才能触发 L1")
        elif current_price > highest_sell:
            print(f"[INFO] 当前价格 ${current_price:,.0f} 高于所有卖单价位")
            print(f"       最高卖单价位: ${highest_sell:,.0f}")
            print(f"       当前价格已经可以触发卖单（如果有持仓）")
        else:
            print(f"[INFO] 当前价格在卖单价位范围内")
            # 找到最接近的卖单价位
            closest_sell_idx = np.argmin(np.abs(sell_levels - current_price))
            closest_sell = sell_levels[closest_sell_idx]
            print(f"       最接近的卖单价位: L{closest_sell_idx+1} @ ${closest_sell:,.0f}")
    
    print()
    print("=" * 80)


def main():
    """主函数"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="解释网格编号逻辑")
    parser.add_argument("--config-file", type=str, help="配置文件路径 (JSON)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="交易对")
    parser.add_argument("--current-price", type=float, default=None, help="当前价格（可选）")
    
    args = parser.parse_args()
    
    # 加载配置
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        strategy_config = config_data.get("strategy", {})
        config = TaoGridLeanConfig(
            name=strategy_config.get("name", "TaoGrid Live"),
            support=float(strategy_config.get("support", 80000.0)),
            resistance=float(strategy_config.get("resistance", 94000.0)),
            regime=strategy_config.get("regime", "NEUTRAL_RANGE"),
            grid_layers_buy=int(strategy_config.get("grid_layers_buy", 35)),
            grid_layers_sell=int(strategy_config.get("grid_layers_sell", 35)),
            initial_cash=float(strategy_config.get("initial_cash", 100.0)),
        )
        if "min_return" in strategy_config:
            config.min_return = float(strategy_config["min_return"])
        if "spacing_multiplier" in strategy_config:
            config.spacing_multiplier = float(strategy_config["spacing_multiplier"])
        if "maker_fee" in strategy_config:
            config.maker_fee = float(strategy_config["maker_fee"])
        if "volatility_k" in strategy_config:
            config.volatility_k = float(strategy_config["volatility_k"])
        if "cushion_multiplier" in strategy_config:
            config.cushion_multiplier = float(strategy_config["cushion_multiplier"])
        if "atr_period" in strategy_config:
            config.atr_period = int(strategy_config["atr_period"])
    else:
        config = TaoGridLeanConfig(
            name="TaoGrid Live",
            support=80000.0,
            resistance=94000.0,
            regime="NEUTRAL_RANGE",
            grid_layers_buy=35,
            grid_layers_sell=35,
        )
    
    explain_grid_numbering(config, symbol=args.symbol, current_price=args.current_price)


if __name__ == "__main__":
    main()
