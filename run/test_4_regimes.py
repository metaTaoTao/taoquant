"""
批量测试4个策略配置
测试期间: 2024-11-27 to 2025-01-25 (约60天)
S/R: 90K - 108K

测试策略:
1. NEUTRAL_RANGE (50/50)
2. BULLISH_RANGE (70/30)
3. BEARISH_RANGE with short (30/70, enable_short_in_bearish=True)
4. BEARISH_RANGE long-only (30/70, enable_short_in_bearish=False)
"""

from pathlib import Path
from datetime import datetime, timezone
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def create_base_config(regime: str, enable_short: bool = False, support: float = 90000.0, resistance: float = 108000.0) -> TaoGridLeanConfig:
    """Create base configuration with specified regime."""
    return TaoGridLeanConfig(
        name=f"TaoGrid {regime} {'(Short)' if enable_short else '(Long-only)'}",
        description=f"Stress test: {regime}, short={'enabled' if enable_short else 'disabled'}",

        # ========== S/R Levels ==========
        support=support,
        resistance=resistance,
        regime=regime,

        # ========== Short Mode (BEARISH only) ==========
        enable_short_in_bearish=enable_short,
        short_breakout_block_threshold=0.95,

        # ========== Grid Parameters ==========
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,

        # ========== P0 Fix: Inventory regime scaling ==========
        inventory_regime_gamma=1.2,  # Scale capacity by (sell_ratio/buy_ratio)^gamma

        # ========== P0 Fix: Cost-basis risk zone ==========
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,  # Trigger when price < cost * (1-3%)
        cost_risk_buy_mult=0.0,  # Stop adding inventory in cost-risk zone

        # ========== Risk Controls ==========
        # MR+Trend factor
        enable_mr_trend_factor=True,
        mr_z_lookback=240,
        mr_z_ref=2.0,
        mr_min_mult=1.0,
        trend_ema_period=120,
        trend_slope_lookback=60,
        trend_slope_ref=0.001,
        trend_block_threshold=0.80,
        trend_buy_k=0.40,
        trend_buy_floor=0.50,

        # Breakout risk factor
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,

        # Range position asymmetry v2
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,

        # Funding factor
        enable_funding_factor=True,

        # Volatility regime factor
        enable_vol_regime_factor=True,

        # ========== Risk / Execution ==========
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=5.0,

        # ========== MM RISK ZONE ==========
        enable_mm_risk_zone=True,
        mm_risk_level1_buy_mult=0.2,
        mm_risk_level1_sell_mult=3.0,
        mm_risk_inventory_penalty=0.5,
        mm_risk_level2_buy_mult=0.1,
        mm_risk_level2_sell_mult=4.0,
        mm_risk_level3_atr_mult=2.0,
        mm_risk_level3_buy_mult=0.05,
        mm_risk_level3_sell_mult=5.0,
        max_risk_atr_mult=3.0,
        max_risk_loss_pct=0.30,
        max_risk_inventory_pct=0.80,
        enable_profit_buffer=True,
        profit_buffer_ratio=0.5,

        # Disable console log for speed
        enable_console_log=False,
    )


def run_single_test(config: TaoGridLeanConfig, output_dir: str, test_name: str, start_date: datetime, end_date: datetime):
    """Run a single backtest."""
    days = (end_date - start_date).days
    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print("=" * 80)
    print(f"Regime: {config.regime}")
    print(f"Short Mode: {'ENABLED' if config.enable_short_in_bearish else 'DISABLED'}")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (~{days} days)")
    print(f"S/R: ${config.support:,.0f} - ${config.resistance:,.0f}")
    print(f"Leverage: {config.leverage}x")
    print(f"P0 Fixes: inventory_regime_gamma={config.inventory_regime_gamma}, cost_basis_risk_zone={config.enable_cost_basis_risk_zone}")
    print("=" * 80)
    print()

    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=start_date,
        end_date=end_date,
        verbose=True,
        progress_every=10000,
        output_dir=Path(output_dir),
    )

    results = runner.run()
    runner.print_summary(results)

    output_path = Path(output_dir)
    runner.save_results(results, output_path)

    print(f"\n[OK] Results saved to: {output_dir}")
    print("=" * 80)

    return results


def main():
    """Run all 4 tests."""
    # Test parameters
    start_date = datetime(2024, 7, 3, tzinfo=timezone.utc)
    end_date = datetime(2024, 8, 10, tzinfo=timezone.utc)
    support = 56000.0
    resistance = 72000.0
    days = (end_date - start_date).days

    print("\n" + "=" * 80)
    print("STRESS TEST: 2024 Aug Flash Crash")
    print("=" * 80)
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (~{days} days)")
    print(f"S/R: ${support:,.0f} - ${resistance:,.0f} ({(resistance-support)/support*100:.1f}% range)")
    print(f"Market Event: 8/5 Flash Crash ($70k -> $49k, -30%)")
    print("Leverage: 5x")
    print()
    print("Testing:")
    print("  1. NEUTRAL_RANGE (50/50, long-only)")
    print("  2. BULLISH_RANGE (70/30, long-only)")
    print("  3. BEARISH_RANGE (30/70, short enabled)")
    print("  4. BEARISH_RANGE (30/70, long-only)")
    print()
    print("CRITICAL: Verify risk management prevents blowup in flash crash!")
    print("=" * 80)

    # Test 1: NEUTRAL_RANGE
    config1 = create_base_config("NEUTRAL_RANGE", enable_short=False, support=support, resistance=resistance)
    results1 = run_single_test(
        config1,
        "run/results_crash_neutral",
        "1. NEUTRAL_RANGE (50/50)",
        start_date,
        end_date
    )

    # Test 2: BULLISH_RANGE
    config2 = create_base_config("BULLISH_RANGE", enable_short=False, support=support, resistance=resistance)
    results2 = run_single_test(
        config2,
        "run/results_crash_bullish",
        "2. BULLISH_RANGE (70/30)",
        start_date,
        end_date
    )

    # Test 3: BEARISH_RANGE with short
    config3 = create_base_config("BEARISH_RANGE", enable_short=True, support=support, resistance=resistance)
    results3 = run_single_test(
        config3,
        "run/results_crash_bearish_short",
        "3. BEARISH_RANGE (30/70, SHORT)",
        start_date,
        end_date
    )

    # Test 4: BEARISH_RANGE long-only
    config4 = create_base_config("BEARISH_RANGE", enable_short=False, support=support, resistance=resistance)
    results4 = run_single_test(
        config4,
        "run/results_crash_bearish_longonly",
        "4. BEARISH_RANGE (30/70, LONG-ONLY)",
        start_date,
        end_date
    )

    # Print comparison summary
    print("\n" + "=" * 80)
    print("FLASH CRASH STRESS TEST RESULTS")
    print("=" * 80)
    print(f"Market Event: 8/5/2024 Flash Crash ($70k -> $49k, -30%)")
    print(f"Test Period: {days} days")
    print()
    print(f"{'Strategy':<30} {'Return':<12} {'MaxDD':<12} {'Sharpe':<10} {'Blowup?':<10} {'Trades':<10}")
    print("-" * 90)

    strategies = [
        ("NEUTRAL (50/50)", results1),
        ("BULLISH (70/30)", results2),
        ("BEARISH Short (30/70)", results3),
        ("BEARISH Long-only (30/70)", results4),
    ]

    for name, res in strategies:
        ret = res['metrics']['total_return']
        dd = res['metrics']['max_drawdown']
        sharpe = res['metrics']['sharpe_ratio']
        trades = res['metrics']['total_trades']
        blowup = "YES" if dd < -0.80 else "NO"  # 80%+ drawdown = blowup
        print(f"{name:<30} {ret:>10.2%}  {dd:>10.2%}  {sharpe:>8.2f}  {blowup:<10} {trades:>8.0f}")

    print("=" * 90)
    print()
    print("RISK ASSESSMENT:")
    print("  - MaxDD < -50%: CRITICAL RISK (unacceptable for live trading)")
    print("  - MaxDD -30% to -50%: HIGH RISK (reduce leverage)")
    print("  - MaxDD -15% to -30%: MODERATE RISK (acceptable with caution)")
    print("  - MaxDD < -15%: LOW RISK (safe for live trading)")
    print()
    print("Results saved to:")
    print("  - run/results_crash_neutral/")
    print("  - run/results_crash_bullish/")
    print("  - run/results_crash_bearish_short/")
    print("  - run/results_crash_bearish_longonly/")
    print("=" * 90)


if __name__ == "__main__":
    main()
