"""
详细解释网格间距计算过程

展示：
1. 基础间距计算 (min_return + trading_costs)
2. 波动率调整
3. 上下限保护
4. 最终间距
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
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing


def explain_spacing_calculation(config: TaoGridLeanConfig, symbol: str = "BTCUSDT"):
    """
    详细解释网格间距计算
    """
    print("=" * 80)
    print("网格间距计算详解")
    print("=" * 80)
    print()
    
    # 获取历史数据
    print("正在获取历史数据...")
    from data.sources.bitget_sdk import BitgetSDKDataSource
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
    
    print(f"历史数据: {len(historical_data)} 根 K 线")
    print()
    
    # 计算 ATR
    atr = calculate_atr(
        historical_data["high"],
        historical_data["low"],
        historical_data["close"],
        period=config.atr_period,
    )
    
    current_atr = atr.iloc[-1]
    avg_atr = atr.mean()
    
    print("=" * 80)
    print("步骤 1: 计算 ATR (Average True Range)")
    print("=" * 80)
    print(f"ATR Period: {config.atr_period}")
    print(f"当前 ATR: ${current_atr:,.2f}")
    print(f"平均 ATR: ${avg_atr:,.2f}")
    print()
    
    # 计算交易成本
    slippage = 0.0  # 限价单无滑点
    trading_costs = (2 * config.maker_fee) + (2 * slippage)  # 双向成本
    
    print("=" * 80)
    print("步骤 2: 计算交易成本")
    print("=" * 80)
    print(f"Maker Fee: {config.maker_fee:.4%} ({config.maker_fee * 100:.4f}%)")
    print(f"Slippage: {slippage:.4%} (限价单无滑点)")
    print(f"Trading Costs (双向): {trading_costs:.4%} ({trading_costs * 100:.4f}%)")
    print("  说明: 买入和卖出各收一次手续费，所以是 2 × maker_fee")
    print()
    
    # 计算基础间距
    base_spacing = config.min_return + trading_costs
    
    print("=" * 80)
    print("步骤 3: 计算基础间距 (Base Spacing)")
    print("=" * 80)
    print(f"Min Return: {config.min_return:.4%} ({config.min_return * 100:.4f}%)")
    print(f"Trading Costs: {trading_costs:.4%} ({trading_costs * 100:.4f}%)")
    print(f"Base Spacing = Min Return + Trading Costs")
    print(f"Base Spacing = {config.min_return:.4%} + {trading_costs:.4%} = {base_spacing:.4%} ({base_spacing * 100:.4f}%)")
    print("  说明: 基础间距必须覆盖最小利润和交易成本")
    print()
    
    # 计算波动率调整
    atr_rolling_mean = atr.rolling(window=20, min_periods=1).mean()
    atr_pct = atr / atr_rolling_mean
    current_atr_pct = atr_pct.iloc[-1]
    
    volatility_adjustment = config.volatility_k * (current_atr_pct - 1.0)
    
    print("=" * 80)
    print("步骤 4: 计算波动率调整 (Volatility Adjustment)")
    print("=" * 80)
    print(f"ATR Rolling Mean (20期): ${atr_rolling_mean.iloc[-1]:,.2f}")
    print(f"当前 ATR / 平均 ATR = {current_atr_pct:.4f}")
    print(f"Volatility K: {config.volatility_k}")
    print(f"Volatility Adjustment = Volatility_K × (ATR_PCT - 1.0)")
    print(f"Volatility Adjustment = {config.volatility_k} × ({current_atr_pct:.4f} - 1.0) = {volatility_adjustment:.4%} ({volatility_adjustment * 100:.4f}%)")
    print("  说明: 如果当前波动率高于平均，增加间距；低于平均，减少间距")
    print()
    
    # 计算调整后的间距
    spacing_before_clip = base_spacing + volatility_adjustment
    
    print("=" * 80)
    print("步骤 5: 计算调整后间距 (Before Clipping)")
    print("=" * 80)
    print(f"Spacing = Base Spacing + Volatility Adjustment")
    print(f"Spacing = {base_spacing:.4%} + {volatility_adjustment:.4%} = {spacing_before_clip:.4%} ({spacing_before_clip * 100:.4f}%)")
    print()
    
    # 应用下限保护
    spacing_after_lower = max(spacing_before_clip, base_spacing)
    
    print("=" * 80)
    print("步骤 6: 应用下限保护 (Lower Bound)")
    print("=" * 80)
    print(f"下限: Base Spacing = {base_spacing:.4%} ({base_spacing * 100:.4f}%)")
    print(f"调整前: {spacing_before_clip:.4%} ({spacing_before_clip * 100:.4f}%)")
    if spacing_after_lower > spacing_before_clip:
        print(f"应用下限保护后: {spacing_after_lower:.4%} ({spacing_after_lower * 100:.4f}%)")
        print("  说明: 间距不能低于基础间距，确保最小利润")
    else:
        print(f"无需调整: {spacing_after_lower:.4%} ({spacing_after_lower * 100:.4f}%)")
    print()
    
    # 应用上限保护
    MAX_SPACING = 0.05  # 5%
    spacing_after_upper = min(spacing_after_lower, MAX_SPACING)
    
    print("=" * 80)
    print("步骤 7: 应用上限保护 (Upper Bound)")
    print("=" * 80)
    print(f"上限: MAX_SPACING = {MAX_SPACING:.4%} ({MAX_SPACING * 100:.4f}%)")
    print(f"调整前: {spacing_after_lower:.4%} ({spacing_after_lower * 100:.4f}%)")
    if spacing_after_upper < spacing_after_lower:
        print(f"应用上限保护后: {spacing_after_upper:.4%} ({spacing_after_upper * 100:.4f}%)")
        print("  说明: 间距不能超过 5%，避免交易频率过低")
    else:
        print(f"无需调整: {spacing_after_upper:.4%} ({spacing_after_upper * 100:.4f}%)")
    print()
    
    # 应用 spacing_multiplier
    final_spacing = spacing_after_upper * config.spacing_multiplier
    
    print("=" * 80)
    print("步骤 8: 应用间距倍数 (Spacing Multiplier)")
    print("=" * 80)
    print(f"Spacing Multiplier: {config.spacing_multiplier}")
    print(f"调整前: {spacing_after_upper:.4%} ({spacing_after_upper * 100:.4f}%)")
    print(f"最终间距 = {spacing_after_upper:.4%} × {config.spacing_multiplier} = {final_spacing:.4%} ({final_spacing * 100:.4f}%)")
    print()
    
    # 总结
    print("=" * 80)
    print("总结")
    print("=" * 80)
    print(f"最终网格间距: {final_spacing:.4%} ({final_spacing * 100:.4f}%)")
    print()
    print("计算公式总结:")
    print("  1. Base Spacing = Min Return + Trading Costs")
    print("  2. Volatility Adjustment = Volatility_K × (ATR_PCT - 1.0)")
    print("  3. Spacing = Base Spacing + Volatility Adjustment")
    print("  4. Spacing = max(Spacing, Base Spacing)  # 下限保护")
    print("  5. Spacing = min(Spacing, 0.05)  # 上限保护 (5%)")
    print("  6. Final Spacing = Spacing × Spacing_Multiplier")
    print()
    
    # 分析为什么是 3.68%
    print("=" * 80)
    print("为什么是 3.68%?")
    print("=" * 80)
    if final_spacing >= MAX_SPACING * 0.9:
        print(f"[INFO] 最终间距 ({final_spacing:.2%}) 接近上限 ({MAX_SPACING:.2%})")
        print("       可能原因:")
        print("       1. 波动率调整很大，导致间距接近上限")
        print("       2. 基础间距本身较大")
        print("       3. 被 MAX_SPACING = 5% 限制")
    elif volatility_adjustment > 0.01:
        print(f"[INFO] 波动率调整较大 ({volatility_adjustment:.2%})")
        print(f"       当前波动率高于平均水平，增加了间距")
    else:
        print(f"[INFO] 间距主要由基础间距决定")
        print(f"       基础间距: {base_spacing:.2%}")
        print(f"       波动率调整: {volatility_adjustment:.2%}")
    
    print()
    print("=" * 80)


def main():
    """主函数"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="解释网格间距计算")
    parser.add_argument("--config-file", type=str, help="配置文件路径 (JSON)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="交易对")
    
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
    
    explain_spacing_calculation(config, symbol=args.symbol)


if __name__ == "__main__":
    main()
