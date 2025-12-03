"""
Test if backtesting.py supports fractional position sizes for crypto trading.
"""
import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest


class TestFractionalSize(Strategy):
    """Test strategy to verify fractional position sizing."""

    def init(self):
        self.trade_count = 0

    def next(self):
        # Test 1: Fractional size (like 0.1667 BTC)
        if len(self.data) == 10 and not self.position:
            print(f"Test 1: Attempting to sell 0.1667 units (fractional BTC)")
            self.sell(size=0.1667)

        # Test 2: Check actual position size
        if len(self.data) == 11 and self.position:
            print(f"Position size after sell(0.1667): {self.position.size}")
            print(f"Position size type: {type(self.position.size)}")

        # Test 3: Adjust position
        if len(self.data) == 20 and self.position:
            print(f"\nTest 2: Attempting to increase to 0.25 units")
            current_size = abs(self.position.size)
            diff = 0.25 - current_size
            if diff > 0:
                self.sell(size=diff)

        if len(self.data) == 21 and self.position:
            print(f"Position size after adjustment: {self.position.size}")

        # Test 4: Partial close
        if len(self.data) == 30 and self.position:
            print(f"\nTest 3: Attempting to reduce by 0.05 units")
            self.buy(size=0.05)

        if len(self.data) == 31 and self.position:
            print(f"Position size after partial close: {self.position.size}")

        # Close all at end
        if len(self.data) == 40 and self.position:
            self.position.close()


if __name__ == "__main__":
    # Generate dummy BTCUSDT data
    dates = pd.date_range('2024-01-01', periods=50, freq='15min')

    # Simulate BTC price around 50000
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
    print("Testing backtesting.py Fractional Position Support")
    print("=" * 80)
    print(f"\nInitial data shape: {df.shape}")
    print(f"Price range: {df['Close'].min():.2f} - {df['Close'].max():.2f}")
    print("\n" + "=" * 80)

    # Run backtest
    bt = Backtest(
        df,
        TestFractionalSize,
        cash=10000,
        commission=0.0004,
        exclusive_orders=True
    )

    try:
        stats = bt.run()
        print("\n" + "=" * 80)
        print("Backtest completed successfully!")
        print("=" * 80)
        print(f"\nNumber of trades: {stats['# Trades']}")
        print(f"Final equity: ${stats['Equity Final [$]']:.2f}")
        print(f"Return: {stats['Return [%]']:.2f}%")

        # Check trade details
        if hasattr(bt, '_results') and hasattr(bt._results, '_trades'):
            trades = bt._results._trades
            if len(trades) > 0:
                print("\nTrade details:")
                for i, trade in enumerate(trades):
                    print(f"  Trade {i+1}: Size = {trade.size}, Entry = ${trade.entry_price:.2f}, Exit = ${trade.exit_price:.2f}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("ERROR during backtest!")
        print("=" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        traceback.print_exc()
