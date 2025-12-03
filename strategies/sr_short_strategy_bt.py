import pandas as pd
import numpy as np
from backtesting import Strategy
from backtesting.lib import crossover

from indicators.sr_indicator_v2 import SupportResistanceVolumeBoxesIndicatorV2

def calculate_atr(high, low, close, period=14):
    high = pd.Series(high)
    low = pd.Series(low)
    close = pd.Series(close)
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean() # Simple Moving Average for ATR
    return atr.bfill().values

class SRShortStrategy(Strategy):
    # Parameters matching the indicator
    lookback = 90
    confirmation = 10
    merge_atr = 3.5
    break_tol = 0.5
    sl_atr_mult = 1.0
    tp_risk_reward = 2.0  # Target 2R
    
    def init(self):
        # 1. Calculate Indicator
        indicator = SupportResistanceVolumeBoxesIndicatorV2(
            lookback=self.lookback,
            confirmation=self.confirmation,
            merge_atr_factor=self.merge_atr,
            break_tol_factor=self.break_tol,
            sl_atr_mult=self.sl_atr_mult,
            use_close_sl=True,
        )
        
        # Convert Backtesting Data to DataFrame
        df = pd.DataFrame({
            'open': self.data.Open,
            'high': self.data.High,
            'low': self.data.Low,
            'close': self.data.Close,
            'volume': self.data.Volume,
        }, index=self.data.index)
        
        # Run calculation
        self.sr_df = indicator.calculate(df)
        
        # Expose indicator arrays for use in next()
        self.signal_s = self.I(lambda: self.sr_df['signal_s'].values, name='Signal S')
        self.signal_2b = self.I(lambda: self.sr_df['signal_2b'].values, name='Signal 2B')
        
        # Calculate ATR independently
        self.atr = self.I(calculate_atr, self.data.High, self.data.Low, self.data.Close, 14, name='ATR')
        
        # Track last signal bar to avoid duplicate entries on same bar
        self.last_signal_bar = -1
        
    def next(self):
        # Check for Signals
        is_signal_s = not np.isnan(self.signal_s[-1])
        is_signal_2b = not np.isnan(self.signal_2b[-1])
        
        # Only enter if we have a signal and haven't already entered on this bar
        if (is_signal_s or is_signal_2b) and len(self.data) - 1 != self.last_signal_bar:
            # Signal Found!
            entry_price = self.data.Close[-1]
            curr_atr = self.atr[-1]
            
            if np.isnan(curr_atr) or curr_atr <= 0:
                return  # Skip if ATR is invalid
            
            # Dynamic SL based on ATR
            sl_price = self.data.High[-1] + curr_atr * self.sl_atr_mult
            
            # TP based on Risk
            risk = sl_price - entry_price
            if risk <= 0:
                return  # Skip if risk is invalid
            
            tp_price = entry_price - (risk * self.tp_risk_reward)
            
            # Close any existing long position first
            if self.position.is_long:
                self.position.close()
            
            # Open Short (allow multiple shorts if exclusive_orders=False)
            # If exclusive_orders=True, this will close previous short and open new one
            self.sell(sl=sl_price, tp=tp_price)
            
            # Mark this bar as processed
            self.last_signal_bar = len(self.data) - 1
