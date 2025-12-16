"""分析网格关闭的触发原因"""
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

# 读取数据
equity_file = Path("run/results_lean_taogrid_stress_test_2025_09_26/equity_curve.csv")
equity_df = pd.read_csv(equity_file)
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])

# 配置参数
support = 107000.0
resistance = 123000.0
cushion_multiplier = 0.8
max_risk_atr_mult = 3.0
atr_period = 14

# 计算 ATR（使用前100根K线）
from data import DataManager
dm = DataManager()
data = dm.get_klines(
    symbol="BTCUSDT",
    timeframe="1m",
    start=datetime(2025, 9, 26, tzinfo=timezone.utc),
    end=datetime(2025, 9, 26, 2, tzinfo=timezone.utc),
    source="okx",
)

from analytics.indicators.volatility import calculate_atr
atr_series = calculate_atr(data['high'], data['low'], data['close'], period=atr_period)
current_atr = atr_series.iloc[-1] if len(atr_series) > 0 else 63.69

print("=" * 80)
print("网格关闭触发原因分析")
print("=" * 80)
print()

print(f"支撑: ${support:,.0f}")
print(f"阻力: ${resistance:,.0f}")
print(f"ATR: ${current_atr:,.2f}")
print(f"Cushion: ${current_atr * cushion_multiplier:,.2f}")
print()

# 计算各种阈值
risk_zone_threshold = support + (current_atr * cushion_multiplier)
level3_threshold = support - (2.0 * current_atr)
shutdown_price_threshold = support - (max_risk_atr_mult * current_atr)

print("风控阈值:")
print(f"  Risk Zone 触发价格: ${risk_zone_threshold:,.2f}")
print(f"  Level 3 触发价格: ${level3_threshold:,.2f}")
print(f"  Shutdown 价格阈值: ${shutdown_price_threshold:,.2f}")
print()

# 检查 00:55 时的价格
shutdown_time = pd.Timestamp("2025-09-26 00:55:00", tz='UTC')
shutdown_data = equity_df[equity_df['timestamp'] == shutdown_time]
if len(shutdown_data) == 0:
    shutdown_data = equity_df[equity_df['timestamp'] <= shutdown_time].iloc[-1:]

# 从权益曲线估算价格（holdings_value / holdings）
if len(shutdown_data) > 0:
    row = shutdown_data.iloc[0]
    holdings = row['holdings']
    holdings_value = row['holdings_value']
    if holdings > 0:
        estimated_price = holdings_value / holdings
        print(f"00:55 时的状态:")
        print(f"  持仓: {holdings:.4f} BTC")
        print(f"  持仓市值: ${holdings_value:,.2f}")
        print(f"  估算价格: ${estimated_price:,.2f}")
        print()
        
        # 检查是否触发价格阈值
        print("价格阈值检查:")
        print(f"  当前价格 ${estimated_price:,.2f} < Shutdown阈值 ${shutdown_price_threshold:,.2f} ? {estimated_price < shutdown_price_threshold}")
        print(f"  当前价格 ${estimated_price:,.2f} < Level3阈值 ${level3_threshold:,.2f} ? {estimated_price < level3_threshold}")
        print(f"  当前价格 ${estimated_price:,.2f} < Risk Zone阈值 ${risk_zone_threshold:,.2f} ? {estimated_price < risk_zone_threshold}")
        print()
        
        if estimated_price < shutdown_price_threshold:
            print("⚠️ 触发原因: 价格低于 Shutdown 阈值（support - 3×ATR）")
        elif estimated_price < level3_threshold:
            print("⚠️ 触发原因: 价格低于 Level3 阈值（support - 2×ATR）")
        elif estimated_price < risk_zone_threshold:
            print("⚠️ 触发原因: 价格低于 Risk Zone 阈值（support + cushion）")

print()
print("=" * 80)
