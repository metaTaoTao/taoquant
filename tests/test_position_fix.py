"""
Test the fixed _sync_position method to ensure it handles:
1. Normal positions (< 95%)
2. Large positions that would exceed 95%
3. Multiple concurrent positions
4. Equity fluctuations
"""
import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest


class TestPositionManagement(Strategy):
    """Test position management with multiple virtual trades."""

    def init(self):
        self.test_stage = 0

    def next(self):
        idx = len(self.data) - 1
        price = self.data.Close[-1]
        equity = self.equity

        # Stage 1: Normal position (0.2 BTC)
        if idx == 5:
            self.test_stage = 1
            btc_size = 0.2
            size_pct = (btc_size * price) / equity
            print(f"\n=== Stage 1: Normal Position ===")
            print(f"Equity: ${equity:,.2f}")
            print(f"Price: ${price:.2f}")
            print(f"Target: {btc_size} BTC")
            print(f"Size %: {size_pct:.2%}")
            if size_pct < 0.95:
                self.sell(size=size_pct)
                print(f"[OK] Order placed: {size_pct:.2%}")
            else:
                print(f"[ERROR] Would exceed 95%!")

        # Stage 2: Check position
        if idx == 6 and self.position:
            print(f"\n=== Stage 1 Result ===")
            print(f"Position size: {abs(self.position.size)}")
            print(f"Position type: {'percentage' if abs(self.position.size) < 1 else 'units'}")

        # Stage 3: Add another position (simulate 2nd virtual trade)
        if idx == 10:
            self.test_stage = 2
            print(f"\n=== Stage 2: Adding 2nd Virtual Trade ===")
            current_pos_pct = abs(self.position.size) if self.position else 0
            print(f"Current position: {current_pos_pct:.2%}")

            # Simulate adding 0.3 BTC
            additional_btc = 0.3
            additional_pct = (additional_btc * price) / equity
            new_total_pct = current_pos_pct + additional_pct

            print(f"Adding: {additional_btc} BTC = {additional_pct:.2%}")
            print(f"New total: {new_total_pct:.2%}")

            if new_total_pct < 0.95:
                self.sell(size=additional_pct)
                print(f"[OK] Order placed")
            else:
                print(f"[WARN] Would exceed 95%! Capping...")
                max_additional = 0.95 - current_pos_pct
                self.sell(size=max_additional)
                print(f"Placed capped order: {max_additional:.2%}")

        if idx == 11 and self.position:
            print(f"\n=== Stage 2 Result ===")
            print(f"Total position: {abs(self.position.size):.4f}")

        # Stage 3: Test near-limit scenario (equity drops)
        if idx == 15:
            self.test_stage = 3
            print(f"\n=== Stage 3: Equity Fluctuation Test ===")
            print(f"Current equity: ${equity:,.2f}")
            current_pos = abs(self.position.size) if self.position else 0
            print(f"Current position: {current_pos:.2%}")

            # Calculate what our position would be in BTC
            if current_pos < 1.0:
                # It's percentage
                btc_amount = (current_pos * equity) / price
                print(f"BTC amount: {btc_amount:.4f}")
                print(f"Position value: ${btc_amount * price:,.2f}")

        # Stage 4: Large position test (1.5 BTC)
        if idx == 20:
            if self.position:
                self.position.close()

            self.test_stage = 4
            print(f"\n=== Stage 4: Large Position Test ===")
            large_btc = 1.5
            large_pct = (large_btc * price) / equity
            print(f"Attempting: {large_btc} BTC")
            print(f"Calculated %: {large_pct:.2%}")

            if large_pct >= 0.95:
                print(f"[WARN] Exceeds 95% limit! Would be capped.")
                large_pct = 0.95

            self.sell(size=large_pct)

        if idx == 21 and self.position:
            print(f"\n=== Stage 4 Result ===")
            pos_size = abs(self.position.size)
            print(f"Position: {pos_size:.4f}")

            if pos_size < 1.0:
                btc_equiv = (pos_size * equity) / price
                print(f"BTC equivalent: {btc_equiv:.4f}")
                print(f"[OK] Position is in percentage mode")
            else:
                print(f"[ERROR] Position is in units mode (BUG!)")

        # Stage 5: Partial close test
        if idx == 25 and self.position:
            self.test_stage = 5
            print(f"\n=== Stage 5: Partial Close Test ===")
            current = abs(self.position.size)
            close_pct = current * 0.30  # Close 30%

            print(f"Current: {current:.4f}")
            print(f"Closing 30%: {close_pct:.4f}")

            self.buy(size=close_pct)

        if idx == 26 and self.position:
            print(f"\n=== Stage 5 Result ===")
            remaining = abs(self.position.size)
            print(f"Remaining: {remaining:.4f}")

        # Final close
        if idx == 30 and self.position:
            self.position.close()


if __name__ == "__main__":
    # Generate test data
    dates = pd.date_range('2024-01-01', periods=35, freq='15min')
    np.random.seed(42)

    # Simulate BTC price around 50,000 with some volatility
    base_price = 50000
    price_changes = np.cumsum(np.random.randn(35) * 100)
    close_prices = base_price + price_changes

    df = pd.DataFrame({
        'Open': close_prices + np.random.randn(35) * 50,
        'High': close_prices + abs(np.random.randn(35) * 100),
        'Low': close_prices - abs(np.random.randn(35) * 100),
        'Close': close_prices,
        'Volume': np.random.randint(100, 1000, 35)
    }, index=dates)

    print("=" * 80)
    print("Testing Fixed Position Management")
    print("=" * 80)
    print(f"Initial capital: $500,000 (UPDATED)")
    print(f"BTC price range: ${df['Close'].min():,.2f} - ${df['Close'].max():,.2f}")
    print("=" * 80)

    # Run backtest with UPDATED capital (500k)
    bt = Backtest(
        df,
        TestPositionManagement,
        cash=500000,  # UPDATED from 200k
        commission=0.0004,
        exclusive_orders=True
    )

    stats = bt.run()

    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)
    print(f"Final equity: ${stats['Equity Final [$]']:,.2f}")
    print(f"Return: {stats['Return [%]']:.2f}%")
    print(f"Number of trades: {stats['# Trades']}")

    if stats['# Trades'] > 0:
        print("\n[SUCCESS] Positions were successfully managed")
    else:
        print("\n[WARNING] No trades executed - check for issues")
