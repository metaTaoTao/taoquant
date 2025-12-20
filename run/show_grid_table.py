"""
输出网格层级表格（Buy 和 Sell Levels）

简单清晰的表格输出，方便查看所有网格层级
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


def show_grid_table(config: TaoGridLeanConfig, symbol: str = "BTCUSDT", current_price: float = None):
    """
    显示网格层级表格
    """
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
    print("=" * 100)
    print("网格配置")
    print("=" * 100)
    print(f"Symbol: {symbol}")
    print(f"Support: ${config.support:,.0f}")
    print(f"Resistance: ${config.resistance:,.0f}")
    print(f"Mid: ${mid:,.0f}")
    print(f"当前价格: ${current_price:,.0f}")
    print()
    
    # 计算间距信息
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
    print(f"网格间距: {actual_spacing:.2%}")
    print(f"Buy Levels 数量: {len(buy_levels)}")
    print(f"Sell Levels 数量: {len(sell_levels)}")
    print()
    
    # 输出 Buy Levels 表格
    print("=" * 100)
    print("BUY LEVELS (买单层级)")
    print("=" * 100)
    print(f"{'Level':<8} {'Price (USD)':<15} {'Distance from Mid':<20} {'Distance from Current':<25} {'Status':<15}")
    print("-" * 100)
    
    for i, price in enumerate(buy_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 判断状态
        if current_price <= price:
            status = "可触发"
        else:
            status = "等待下跌"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%)  {status:<15}")
    
    print()
    
    # 输出 Sell Levels 表格
    print("=" * 100)
    print("SELL LEVELS (卖单层级)")
    print("=" * 100)
    print(f"{'Level':<8} {'Price (USD)':<15} {'Distance from Mid':<20} {'Distance from Current':<25} {'Status':<15}")
    print("-" * 100)
    
    for i, price in enumerate(sell_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 判断状态
        if current_price >= price:
            status = "可触发"
        else:
            status = "等待上涨"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%)  {status:<15}")
    
    print()
    print("=" * 100)
    
    # 输出配对信息（如果 sell_levels 是从 buy_levels 生成的）
    if len(buy_levels) == len(sell_levels):
        print("网格配对 (Buy[i] -> Sell[i])")
        print("=" * 100)
        print(f"{'Pair':<8} {'Buy Price':<15} {'Sell Price':<15} {'Profit %':<12} {'Spacing':<12}")
        print("-" * 100)
        
        for i in range(len(buy_levels)):
            buy_price = buy_levels[i]
            sell_price = sell_levels[i]
            profit_pct = ((sell_price - buy_price) / buy_price) * 100
            spacing_pct = actual_spacing * 100
            
            print(f"Pair {i+1:<3} ${buy_price:>12,.0f}  ${sell_price:>12,.0f}  {profit_pct:>10.2f}%  {spacing_pct:>10.2f}%")
        
        print()
        print("=" * 100)


def main():
    """主函数"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="显示网格层级表格")
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
    
    show_grid_table(config, symbol=args.symbol, current_price=args.current_price)


if __name__ == "__main__":
    main()
