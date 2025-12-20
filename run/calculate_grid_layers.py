"""
快速计算实盘网格层数（grid_layers_buy/sell）

使用方法：
    python run/calculate_grid_layers.py --support 104000 --resistance 126000 --symbol BTCUSDT
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data.sources.bitget_sdk import BitgetSDKDataSource
from analytics.indicators.volatility import calculate_atr
import pandas as pd


def calculate_recommended_layers(
    support: float,
    resistance: float,
    symbol: str = "BTCUSDT",
    min_return: float = 0.005,
    maker_fee: float = 0.0002,
    volatility_k: float = 0.6,
    cushion_multiplier: float = 0.8,
    atr_period: int = 14,
    lookback_days: int = 7,
) -> dict:
    """
    计算推荐的网格层数。

    Parameters
    ----------
    support : float
        支撑位价格
    resistance : float
        阻力位价格
    symbol : str
        交易对符号
    min_return : float
        最小净利润（默认 0.5%）
    maker_fee : float
        单边 maker 手续费（默认 0.02%）
    volatility_k : float
        波动率系数（默认 0.6）
    cushion_multiplier : float
        缓冲倍数（默认 0.8）
    atr_period : int
        ATR 周期（默认 14）
    lookback_days : int
        历史数据回看天数（默认 7 天）

    Returns
    -------
    dict
        包含推荐层数、计算过程等信息
    """
    print("=" * 80)
    print("网格层数计算器")
    print("=" * 80)
    print(f"交易对: {symbol}")
    print(f"支撑位: ${support:,.0f}")
    print(f"阻力位: ${resistance:,.0f}")
    print(f"区间宽度: ${resistance - support:,.0f} ({((resistance - support) / support * 100):.2f}%)")
    print()

    # 验证输入
    if support >= resistance:
        raise ValueError(f"支撑位 ({support}) 必须 < 阻力位 ({resistance})")

    # 获取历史数据计算 ATR
    print("正在获取历史数据...")
    data_source = BitgetSDKDataSource(debug=False)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=lookback_days)

    try:
        historical_data = data_source.get_klines(
            symbol=symbol,
            timeframe="1m",
            start=start_date,
            end=end_date,
        )

        if historical_data.empty:
            raise ValueError("无法获取历史数据")

        print(f"[OK] 获取到 {len(historical_data)} 根K线")
        print(f"  时间范围: {historical_data.index[0]} 到 {historical_data.index[-1]}")
        print()

    except Exception as e:
        print(f"[FAIL] 获取历史数据失败: {e}")
        print("使用默认 ATR 估算...")
        # 使用价格区间的 1.5% 作为 ATR 的粗略估算
        mid_price = (support + resistance) / 2
        estimated_atr = mid_price * 0.015
        historical_data = None

    # 计算 ATR
    if historical_data is not None:
        atr_series = calculate_atr(
            historical_data["high"],
            historical_data["low"],
            historical_data["close"],
            period=atr_period,
        )
        current_atr = float(atr_series.iloc[-1])
        avg_atr = float(atr_series.mean())
    else:
        current_atr = estimated_atr
        avg_atr = estimated_atr

    mid_price = (support + resistance) / 2
    atr_pct = (current_atr / mid_price) * 100

    print("ATR 分析:")
    print(f"  当前 ATR: ${current_atr:,.2f} ({atr_pct:.2f}%)")
    if historical_data is not None:
        print(f"  平均 ATR: ${avg_atr:,.2f} ({(avg_atr / mid_price * 100):.2f}%)")
    print()

    # 计算网格间距
    # spacing = min_return + 2×maker_fee + k×volatility
    trading_costs = 2 * maker_fee
    volatility_component = volatility_k * (atr_pct / 100)
    spacing_pct = min_return + trading_costs + volatility_component

    print("网格间距计算:")
    print(f"  最小净利润: {min_return:.2%}")
    print(f"  交易成本 (2×maker_fee): {trading_costs:.2%}")
    print(f"  波动率调整 (k×ATR%): {volatility_component:.2%}")
    print(f"  → 网格间距: {spacing_pct:.2%} (${spacing_pct * mid_price:,.0f})")
    print()

    # 计算可用区间
    cushion = current_atr * cushion_multiplier
    usable_range = (resistance - support) - (2 * cushion)
    usable_range_pct = (usable_range / mid_price) * 100

    print("可用区间计算:")
    print(f"  总区间: ${resistance - support:,.0f}")
    print(f"  缓冲 (2×cushion): ${2 * cushion:,.0f}")
    print(f"  → 可用区间: ${usable_range:,.0f} ({usable_range_pct:.2f}%)")
    print()

    # 计算格子数量
    spacing_dollar = spacing_pct * mid_price
    num_layers = usable_range / spacing_dollar

    print("=" * 80)
    print("推荐配置")
    print("=" * 80)
    print(f"计算出的理论层数: {num_layers:.1f} 层")
    print()

    # 给出不同风险偏好的建议
    conservative_layers = max(5, int(num_layers * 0.7))
    balanced_layers = max(8, int(num_layers))
    aggressive_layers = min(50, int(num_layers * 1.5))

    print("不同风险偏好的推荐:")
    print(f"  保守型: {conservative_layers} 层 (理论值 × 0.7)")
    print(f"     → 交易频率: 低 (每天 1-5 笔)")
    print(f"     → 单笔利润: 高 (0.5-1%+)")
    print(f"     → 适合: 大资金、低波动市场")
    print()
    print(f"  平衡型: {balanced_layers} 层 (理论值 × 1.0) [推荐]")
    print(f"     → 交易频率: 中 (每天 5-20 笔)")
    print(f"     → 单笔利润: 中 (0.3-0.5%)")
    print(f"     → 适合: 中等资金 ($1k-$10k)、正常波动")
    print()
    print(f"  激进型: {aggressive_layers} 层 (理论值 × 1.5)")
    print(f"     → 交易频率: 高 (每天 20-50 笔)")
    print(f"     → 单笔利润: 低 (0.1-0.3%)")
    print(f"     → 适合: 小资金、高波动、追求高周转")
    print()

    # 验证成本覆盖
    net_profit_per_trade = spacing_pct - trading_costs
    if net_profit_per_trade < 0:
        print("[WARNING] 网格间距 < 交易成本，单笔交易会亏损！")
        print(f"   建议增加 min_return 到至少 {trading_costs + 0.001:.2%}")
    else:
        print(f"[OK] 成本验证通过: 单笔净利润 ≈ {net_profit_per_trade:.2%}")
    print()

    # 验证区间合理性
    range_width_pct = ((resistance - support) / support) * 100
    min_recommended_width = 3 * atr_pct
    if range_width_pct < min_recommended_width:
        print(f"[WARNING] 区间宽度 ({range_width_pct:.2f}%) < 推荐最小值 ({min_recommended_width:.2f}%)")
        print(f"   建议区间宽度至少 = 3×ATR% = {min_recommended_width:.2f}%")
        print(f"   或调整 support/resistance 留出更多安全边际")
    else:
        print(f"[OK] 区间宽度验证通过: {range_width_pct:.2f}% >= {min_recommended_width:.2f}%")
    print()

    return {
        "theoretical_layers": num_layers,
        "conservative": conservative_layers,
        "balanced": balanced_layers,
        "aggressive": aggressive_layers,
        "spacing_pct": spacing_pct,
        "spacing_dollar": spacing_dollar,
        "usable_range": usable_range,
        "current_atr": current_atr,
        "atr_pct": atr_pct,
        "net_profit_per_trade": net_profit_per_trade,
    }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="计算实盘网格层数推荐值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python run/calculate_grid_layers.py --support 104000 --resistance 126000

  # 指定交易对
  python run/calculate_grid_layers.py --support 104000 --resistance 126000 --symbol ETHUSDT

  # 自定义手续费和最小利润
  python run/calculate_grid_layers.py --support 104000 --resistance 126000 \\
      --min-return 0.003 --maker-fee 0.0002
        """,
    )

    parser.add_argument(
        "--support",
        type=float,
        required=True,
        help="支撑位价格",
    )
    parser.add_argument(
        "--resistance",
        type=float,
        required=True,
        help="阻力位价格",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="交易对符号（默认: BTCUSDT）",
    )
    parser.add_argument(
        "--min-return",
        type=float,
        default=0.005,
        help="最小净利润（默认: 0.005 = 0.5%%）",
    )
    parser.add_argument(
        "--maker-fee",
        type=float,
        default=0.0002,
        help="单边 maker 手续费（默认: 0.0002 = 0.02%%）",
    )
    parser.add_argument(
        "--volatility-k",
        type=float,
        default=0.6,
        help="波动率系数（默认: 0.6）",
    )

    args = parser.parse_args()

    try:
        result = calculate_recommended_layers(
            support=args.support,
            resistance=args.resistance,
            symbol=args.symbol,
            min_return=args.min_return,
            maker_fee=args.maker_fee,
            volatility_k=args.volatility_k,
        )

        print("=" * 80)
        print("最终推荐")
        print("=" * 80)
        print(f"建议使用平衡型配置:")
        print(f'  "grid_layers_buy": {result["balanced"]},')
        print(f'  "grid_layers_sell": {result["balanced"]},')
        print()
        print("如果交易频率太高（>20 笔/天），减少到保守型")
        print("如果交易频率太低（<3 笔/天），增加到激进型")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
