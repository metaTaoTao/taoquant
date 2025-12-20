"""
可视化 TaoGrid 网格布局

显示：
1. 网格层级（buy/sell levels）
2. 当前价格位置
3. 每个层级的距离和编号
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


def visualize_grid(config: TaoGridLeanConfig, symbol: str = "BTCUSDT", current_price: float = None):
    """
    可视化网格布局
    
    Parameters
    ----------
    config : TaoGridLeanConfig
        策略配置
    symbol : str
        交易对
    current_price : float, optional
        当前价格（如果不提供，会从交易所获取）
    """
    print("=" * 80)
    print("TaoGrid 网格可视化")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Support: ${config.support:,.0f}")
    print(f"Resistance: ${config.resistance:,.0f}")
    print(f"Mid: ${(config.support + config.resistance) / 2:,.0f}")
    print(f"Regime: {config.regime}")
    print()
    
    # 获取历史数据用于计算 ATR
    print("正在获取历史数据...")
    data_source = BitgetSDKDataSource()
    try:
        # 获取最近 200 根 K 线（用于计算 ATR）
        end_date = pd.Timestamp.now(tz="UTC")
        start_date = end_date - pd.Timedelta(days=7)
        historical_data = data_source.get_klines(
            symbol=symbol,
            timeframe="15m",
            start=start_date,
            end=end_date,
        )
        
        if len(historical_data) < 14:
            print(f"[WARNING] 历史数据不足 ({len(historical_data)} 根)，使用默认 ATR")
            # 创建模拟数据
            base_price = (config.support + config.resistance) / 2
            dates = pd.date_range(end=end_date, periods=100, freq="15min")
            historical_data = pd.DataFrame({
                'open': base_price * (1 + np.random.randn(100) * 0.01),
                'high': base_price * (1 + np.abs(np.random.randn(100)) * 0.01),
                'low': base_price * (1 - np.abs(np.random.randn(100)) * 0.01),
                'close': base_price * (1 + np.random.randn(100) * 0.01),
                'volume': np.random.rand(100) * 1000,
            }, index=dates)
        
        # 获取当前价格
        if current_price is None:
            latest_bar = data_source.get_latest_bar(symbol=symbol, timeframe="15m")
            if latest_bar is not None:
                current_price = latest_bar['close']
            else:
                current_price = (config.support + config.resistance) / 2
                print(f"[WARNING] 无法获取当前价格，使用 mid 价格: ${current_price:,.0f}")
        else:
            print(f"使用提供的当前价格: ${current_price:,.0f}")
        
    except Exception as e:
        print(f"[ERROR] 获取数据失败: {e}")
        print("使用模拟数据...")
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
    
    # 初始化网格管理器
    grid_manager = GridManager(config)
    grid_manager.setup_grid(historical_data)
    
    buy_levels = grid_manager.buy_levels
    sell_levels = grid_manager.sell_levels
    mid = (config.support + config.resistance) / 2
    
    print()
    print("=" * 80)
    print("网格布局")
    print("=" * 80)
    print()
    
    # 计算价格范围用于可视化
    all_prices = np.concatenate([buy_levels, sell_levels, [current_price, mid, config.support, config.resistance]])
    price_min = all_prices.min() * 0.995
    price_max = all_prices.max() * 1.005
    
    # 创建 ASCII 图表
    chart_height = 40
    chart_width = 80
    
    # 价格到行索引的映射
    def price_to_row(price):
        return int((price - price_min) / (price_max - price_min) * (chart_height - 1))
    
    # 创建图表矩阵
    chart = [[' ' for _ in range(chart_width)] for _ in range(chart_height)]
    
    # 绘制价格轴标签
    price_step = (price_max - price_min) / chart_height
    price_labels = []
    for i in range(0, chart_height, 5):
        price = price_max - i * price_step
        price_labels.append((i, f"${price:,.0f}"))
    
    # 绘制网格线
    for i in range(chart_height):
        chart[i][0] = '|'
        chart[i][chart_width - 1] = '|'
    
    # 绘制 mid 线
    mid_row = price_to_row(mid)
    if 0 <= mid_row < chart_height:
        for j in range(chart_width):
            chart[mid_row][j] = '-'
        chart[mid_row][chart_width // 2] = 'M'
    
    # 绘制 support/resistance 线
    support_row = price_to_row(config.support)
    resistance_row = price_to_row(config.resistance)
    for j in range(10, chart_width):
        if 0 <= support_row < chart_height:
            chart[support_row][j] = '='
        if 0 <= resistance_row < chart_height:
            chart[resistance_row][j] = '='
    
    # 绘制 buy levels（从高到低，L1 是最高的）
    buy_x = 15
    for i, price in enumerate(buy_levels):
        row = price_to_row(price)
        if 0 <= row < chart_height:
            # 绘制点
            chart[row][buy_x] = 'B'
            # 绘制标签
            label = f"L{i+1}"
            for k, char in enumerate(label):
                if buy_x + k + 2 < chart_width:
                    chart[row][buy_x + k + 2] = char
    
    # 绘制 sell levels
    sell_x = 50
    for i, price in enumerate(sell_levels):
        row = price_to_row(price)
        if 0 <= row < chart_height:
            # 绘制点
            chart[row][sell_x] = 'S'
            # 绘制标签
            label = f"L{i+1}"
            for k, char in enumerate(label):
                if sell_x + k + 2 < chart_width:
                    chart[row][sell_x + k + 2] = char
    
    # 绘制当前价格
    current_row = price_to_row(current_price)
    if 0 <= current_row < chart_height:
        for j in range(chart_width):
            if chart[current_row][j] == ' ':
                chart[current_row][j] = '.'
        chart[current_row][chart_width // 2 - 5] = 'C'
        chart[current_row][chart_width // 2 - 4] = 'U'
        chart[current_row][chart_width // 2 - 3] = 'R'
        chart[current_row][chart_width // 2 - 2] = 'R'
    
    # 打印图表
    print("图例:")
    print("  B = Buy Level (买单)")
    print("  S = Sell Level (卖单)")
    print("  M = Mid Price (中间价)")
    print("  === = Support/Resistance (支撑/阻力)")
    print("  ... = Current Price (当前价格)")
    print()
    print("价格 (从高到低)")
    print("-" * chart_width)
    
    for i in range(chart_height):
        # 打印价格标签
        label_str = ""
        for label_row, label_price in price_labels:
            if abs(i - label_row) < 1:
                label_str = f"{label_price:>12}"
                break
        
        row_str = "".join(chart[i])
        print(f"{label_str:>12} {row_str}")
    
    print("-" * chart_width)
    print()
    
    # 打印详细信息表格
    print("=" * 80)
    print("网格层级详情")
    print("=" * 80)
    print()
    
    # Buy levels 表格
    print("BUY LEVELS (买单层级 - 从高到低，L1 是最高的买单价位)")
    print("-" * 80)
    print(f"{'Level':<8} {'Price':<15} {'Distance from Mid':<20} {'Distance from Current':<25}")
    print("-" * 80)
    
    for i, price in enumerate(buy_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 标记最接近当前价格的层级
        marker = ""
        if i == 0:
            marker = " (最高买单价)"
        if abs(distance_from_current) == min([abs(p - current_price) for p in buy_levels]):
            marker += " [最接近当前价格]"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%){marker}")
    
    print()
    
    # Sell levels 表格
    print("SELL LEVELS (卖单层级 - 从低到高，L1 是最低的卖单价位)")
    print("-" * 80)
    print(f"{'Level':<8} {'Price':<15} {'Distance from Mid':<20} {'Distance from Current':<25}")
    print("-" * 80)
    
    for i, price in enumerate(sell_levels):
        level = f"L{i+1}"
        distance_from_mid = price - mid
        distance_from_current = price - current_price
        distance_from_mid_pct = (distance_from_mid / mid) * 100
        distance_from_current_pct = (distance_from_current / current_price) * 100
        
        # 标记最接近当前价格的层级
        marker = ""
        if i == 0:
            marker = " (最低卖单价)"
        if abs(distance_from_current) == min([abs(p - current_price) for p in sell_levels]):
            marker += " [最接近当前价格]"
        
        print(f"{level:<8} ${price:>12,.0f}  {distance_from_mid:>8.0f} ({distance_from_mid_pct:>6.2f}%)  "
              f"{distance_from_current:>8.0f} ({distance_from_current_pct:>6.2f}%){marker}")
    
    print()
    print("=" * 80)
    print("关键信息")
    print("=" * 80)
    print(f"当前价格: ${current_price:,.0f}")
    print(f"Mid 价格: ${mid:,.0f}")
    print(f"Support: ${config.support:,.0f}")
    print(f"Resistance: ${config.resistance:,.0f}")
    print()
    
    # 分析当前价格位置
    if current_price < buy_levels.min():
        print("[INFO] 当前价格低于所有买单价位，不会触发任何买单")
        closest_buy = buy_levels[np.argmin(np.abs(buy_levels - current_price))]
        print(f"       最接近的买单价位: ${closest_buy:,.0f} (距离: ${current_price - closest_buy:,.0f})")
    elif current_price > buy_levels.max():
        print("[INFO] 当前价格高于所有买单价位，不会触发任何买单")
        closest_buy = buy_levels[np.argmin(np.abs(buy_levels - current_price))]
        print(f"       最接近的买单价位: ${closest_buy:,.0f} (距离: ${current_price - closest_buy:,.0f})")
    else:
        print("[INFO] 当前价格在买单价位范围内，可能触发买单")
    
    if current_price < sell_levels.min():
        print("[INFO] 当前价格低于所有卖单价位，不会触发任何卖单")
    elif current_price > sell_levels.max():
        print("[INFO] 当前价格高于所有卖单价位，不会触发任何卖单")
    else:
        print("[INFO] 当前价格在卖单价位范围内，可能触发卖单（如果有持仓）")
    
    print()
    print("=" * 80)


def main():
    """主函数"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="可视化 TaoGrid 网格布局")
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
        # 加载可选参数
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
        # 使用默认配置
        config = TaoGridLeanConfig(
            name="TaoGrid Live",
            support=80000.0,
            resistance=94000.0,
            regime="NEUTRAL_RANGE",
            grid_layers_buy=35,
            grid_layers_sell=35,
        )
    
    visualize_grid(config, symbol=args.symbol, current_price=args.current_price)


if __name__ == "__main__":
    main()
