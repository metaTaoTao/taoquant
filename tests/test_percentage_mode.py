"""
Test backtesting.py with percentage-based position sizing (current approach).
"""
import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest


class TestPercentageSize(Strategy):
    """Test strategy using percentage-based sizing."""

    def init(self):
        self.entry_count = 0

    def next(self):
        current_price = self.data.Close[-1]
        equity = self.equity

        # Test 1: Open position using 10% of equity
        if len(self.data) == 10 and not self.position:
            size_pct = 0.10  # 10% of equity
            print(f"\n=== Test 1: Opening Position ===")
            print(f"Equity: ${equity:.2f}")
            print(f"Price: ${current_price:.2f}")
            print(f"Size (percentage): {size_pct}")
            print(f"Equivalent BTC: {(equity * size_pct) / current_price:.6f}")
            self.sell(size=size_pct)

        # Check position after entry
        if len(self.data) == 11 and self.position:
            print(f"\n=== After Entry ===")
            print(f"Position size (from backtesting): {self.position.size}")
            print(f"Position is_short: {self.position.is_short}")
            # Calculate actual BTC amount
            actual_btc = abs(self.position.size)
            print(f"Actual BTC amount: {actual_btc:.6f}")
            print(f"Position value: ${actual_btc * current_price:.2f}")

        # Test 2: Increase position by another 5%
        if len(self.data) == 20 and self.position:
            size_pct = 0.05
            print(f"\n=== Test 2: Increasing Position ===")
            print(f"Current equity: ${equity:.2f}")
            print(f"Adding: {size_pct} ({size_pct*100}%)")
            self.sell(size=size_pct)

        if len(self.data) == 21 and self.position:
            print(f"\n=== After Increase ===")
            print(f"Position size: {self.position.size}")
            actual_btc = abs(self.position.size)
            print(f"Actual BTC amount: {actual_btc:.6f}")

        # Test 3: Partial close (buy back 3%)
        if len(self.data) == 30 and self.position:
            size_pct = 0.03
            print(f"\n=== Test 3: Partial Close ===")
            print(f"Closing {size_pct*100}% of equity")
            self.buy(size=size_pct)

        if len(self.data) == 31 and self.position:
            print(f"\n=== After Partial Close ===")
            print(f"Position size: {self.position.size}")
            actual_btc = abs(self.position.size)
            print(f"Actual BTC amount: {actual_btc:.6f}")

        # Test 4: Simulate split virtual trades (30% + 70%)
        if len(self.data) == 40:
            if self.position:
                self.position.close()
            print(f"\n=== Test 4: Split Virtual Trades ===")

            # Calculate total position like the strategy does
            risk_pct = 0.005  # 0.5% risk
            entry_price = current_price
            atr_200 = 100  # Assume ATR(200) = 100
            sl_distance = 3 * atr_200  # 300
            sl_price = entry_price + sl_distance

            # Calculate position size based on risk
            risk_amount = equity * risk_pct
            total_qty = risk_amount / sl_distance  # In BTC units

            print(f"Equity: ${equity:.2f}")
            print(f"Risk amount: ${risk_amount:.2f}")
            print(f"SL distance: ${sl_distance:.2f}")
            print(f"Total BTC qty (calculated): {total_qty:.6f}")

            # Split: 30% fixed, 70% trailing
            q_fixed = total_qty * 0.30
            q_trailing = total_qty * 0.70

            print(f"  Fixed TP part: {q_fixed:.6f} BTC")
            print(f"  Trailing part: {q_trailing:.6f} BTC")

            # Convert total to percentage
            total_value = total_qty * entry_price
            total_pct = total_value / equity

            print(f"Total position value: ${total_value:.2f}")
            print(f"Total position %: {total_pct:.4f} ({total_pct*100:.2f}%)")

            # Open position using percentage
            self.sell(size=total_pct)

        if len(self.data) == 41 and self.position:
            print(f"\n=== After Split Trade Entry ===")
            actual_btc = abs(self.position.size)
            print(f"Actual BTC in position: {actual_btc:.6f}")

            # Now simulate closing 30% (fixed TP part)
            equity_now = self.equity
            q_to_close = actual_btc * 0.30
            close_value = q_to_close * current_price
            close_pct = close_value / equity_now

            print(f"\nSimulating 30% TP close:")
            print(f"  BTC to close: {q_to_close:.6f}")
            print(f"  Close value: ${close_value:.2f}")
            print(f"  Close %: {close_pct:.4f}")

        # Close everything at end
        if len(self.data) == 45 and self.position:
            self.position.close()


if __name__ == "__main__":
    # Generate dummy data
    dates = pd.date_range('2024-01-01', periods=50, freq='15min')
    np.random.seed(42)
    close_prices = 50000 + np.cumsum(np.random.randn(50) * 100)

    df = pd.DataFrame({
        'Open': close_prices + np.random.randn(50) * 50,
        'High': close_prices + abs(np.random.randn(50) * 100),
        'Low': close_prices - abs(np.random.randn(50) * 100),
        'Close': close_prices,
        'Volume': np.random.randint(100, 1000, 50)
    }, index=dates)

    print("=" * 80)
    print("Testing Percentage-Based Position Sizing")
    print("=" * 80)

    # Run backtest with large cash to avoid warnings
    bt = Backtest(
        df,
        TestPercentageSize,
        cash=100000,  # Large enough to avoid fractional warning
        commission=0.0004,
        exclusive_orders=True
    )

    stats = bt.run()

    print("\n" + "=" * 80)
    print("Final Results")
    print("=" * 80)
    print(f"Number of trades: {stats['# Trades']}")
    print(f"Final equity: ${stats['Equity Final [$]']:.2f}")
    print(f"Return: {stats['Return [%]']:.2f}%")
