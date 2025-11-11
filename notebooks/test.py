from risk_management.risk_checker import RiskChecker
from utils.plots import ChartPlotter
from core.strategy_loader import load_all_strategies
from indicators.all_indicators import calculate_volume_heatmap
from indicators.support_resistance import SupportResistancePivotIndicator
from indicators.ema import EMAIndicator
from indicators.vol_heatmap import VolumeHeatmapIndicator
from indicators.sr_volume_boxes import SupportResistanceVolumeBoxesIndicator
from IPython.display import display, Markdown
import pandas as pd

from data import DataManager

# ------------------------------------------------------------------
# Load 15m OHLCV for the past 30 days from OKX
# ------------------------------------------------------------------
manager = DataManager()
end_time = pd.Timestamp.utcnow().floor("min")
start_time = end_time - pd.Timedelta(days=200)
symbol = 'BTCUSDT'
print(f"Getting {symbol} data from {start_time} to {end_time}")
btc_1d = manager.get_klines(
    symbol=symbol,
    timeframe="1d",
    start=start_time,
    end=end_time,
    source="okx",
)

sr = SupportResistanceVolumeBoxesIndicator()
df = sr.calculate(btc_1d.copy())
