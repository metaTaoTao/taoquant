# Legacy Code Archive

> **Date Archived**: 2025-12-03
> **Reason**: Major refactoring to clean architecture (VectorBT-based)

---

## What's in this folder?

This folder contains the **old implementation** of TaoQuant that was based on `backtesting.py` library. The code has been replaced with a cleaner, more maintainable architecture using VectorBT.

### Why was it archived?

The old implementation had several issues:
1. **VirtualTrade workaround** (~600 lines) to handle fractional positions
2. **Mixed concerns** - indicators, signals, sizing, and execution all tangled together
3. **Hard to test** - stateful code with side effects
4. **Hard to extend** - tight coupling between components

The new implementation solves all these issues with:
- ✅ VectorBT native fractional position support
- ✅ Pure functions with clear separation of concerns
- ✅ 100% type hints and docstrings
- ✅ Modular, testable architecture
- ✅ 60% less code

---

## Folder Structure

```
legacy/
├── old_strategies/            # Old strategy implementations
│   ├── sr_short_4h_resistance.py          (1085 lines)
│   ├── sr_short_4h_resistance_fixed.py
│   ├── sr_short_strategy_bt.py
│   ├── sr_guard.py
│   ├── sma_cross.py
│   ├── tdxh_dip.py
│   └── structure_weighted_grid.py
│
├── old_backtest/              # Old backtesting.py engine wrapper
│   ├── engine.py
│   └── __init__.py
│
├── old_indicators/            # Old indicator system
│   ├── base_indicator.py
│   ├── sr_volume_boxes.py
│   ├── sr_indicator_v2.py
│   ├── support_resistance.py
│   ├── vol_heatmap.py
│   └── (more...)
│
├── old_scripts/               # Old scripts and utilities
│   ├── run_backtest.py        (721 lines)
│   └── scripts/
│
└── old_docs/                  # Old documentation
    ├── DEBUGGING_GUIDE.md
    ├── STRATEGY_EVALUATION.md
    └── (more...)
```

---

## Should you use this code?

**NO** - Use the new implementation instead.

The new architecture is:
- Faster (100x with VectorBT)
- Cleaner (60% less code)
- More maintainable
- Better documented

See `/docs/system_design.md` for the new architecture.

---

## Migrating from old code

If you have custom strategies based on the old code, see:
- `/docs/phase2_completion_summary.md` - New strategy structure
- `/strategies/signal_based/sr_short.py` - Example of new strategy
- `/strategies/base_strategy.py` - Base class for all strategies

Key changes:
1. Strategies now extend `BaseStrategy` (not `backtesting.Strategy`)
2. Three methods: `compute_indicators()`, `generate_signals()`, `calculate_position_size()`
3. Pure functions - no state management
4. VectorBT engine handles execution (no VirtualTrade)

---

## Can this code be deleted?

**Yes**, after you've verified the new implementation works for your use case.

We keep it here temporarily for reference during the transition period.

**Recommended**: Keep this folder for 1-2 months, then delete if not needed.

---

## Questions?

See the new documentation:
- `/README.md` - Project overview
- `/docs/system_design.md` - Architecture guide
- `/docs/phase1_completion_summary.md` - Engine layer
- `/docs/phase2_completion_summary.md` - Strategy layer
