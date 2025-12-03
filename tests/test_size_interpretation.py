"""
Test to understand backtesting.py's size parameter interpretation.
"""
import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest


class TestSizeInterpretation(Strategy):
    """Test different size values."""

    def init(self):
        pass

    def next(self):
        current_price = self.data.Close[-1]
        equity = self.equity

        # Test Series: Different size values
        if len(self.data) == 10 and not self.position:
            # Test: What if we use a very small number like 0.0001667?
            # This represents 0.1667 BTC when cash=10000, price=50000
            # 0.1667 BTC * 50000 = 8335 USDT
            # 8335 / 100000 equity = 0.08335

            # But let's test even smaller
            test_size = 0.0001667
            print(f"\n=== Test: Tiny size (should be percentage) ===")
            print(f"Equity: ${equity:.2f}")
            print(f"Price: ${current_price:.2f}")
            print(f"Size parameter: {test_size}")
            print(f"Expected: {test_size} is < 1, so should be % of equity")
            print(f"Expected position value: ${equity * test_size:.2f}")
            print(f"Expected BTC amount: {(equity * test_size) / current_price:.6f}")

            self.sell(size=test_size)

        if len(self.data) == 11 and self.position:
            actual_size = abs(self.position.size)
            actual_value = actual_size * current_price
            print(f"\n=== Actual Result ===")
            print(f"Position size: {actual_size}")
            print(f"Position value: ${actual_value:.2f}")

            # Is it BTC units or % of equity?
            if actual_size < 1.0:
                # Could be percentage
                implied_equity = actual_value  # If size is %, then value = equity * size, so equity = value / size
                print(f"If interpreted as %: implied equity would be ${implied_equity:.2f}")
            else:
                # Definitely units
                print(f"Interpreted as {actual_size:.6f} BTC units")


if __name__ == "__main__":
    dates = pd.date_range('2024-01-01', periods=20, freq='15min')
    np.random.seed(42)
    close_prices = 50000 + np.cumsum(np.random.randn(20) * 50)

    df = pd.DataFrame({
        'Open': close_prices + np.random.randn(20) * 25,
        'High': close_prices + abs(np.random.randn(20) * 50),
        'Low': close_prices - abs(np.random.randn(20) * 50),
        'Close': close_prices,
        'Volume': np.random.randint(100, 1000, 20)
    }, index=dates)

    print("=" * 80)
    print("Testing Size Parameter Interpretation")
    print("=" * 80)

    # Use realistic crypto capital
    bt = Backtest(
        df,
        TestSizeInterpretation,
        cash=100000,  # 100k USDT
        commission=0.0004,
        exclusive_orders=True
    )

    stats = bt.run()
    print("\n" + "=" * 80)
    print(f"Final equity: ${stats['Equity Final [$]']:.2f}")
