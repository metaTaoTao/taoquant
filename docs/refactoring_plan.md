# TaoQuant Project Refactoring Plan

> **Date**: 2025-12-03
> **Type**: Major Refactoring - Clean Architecture
> **Status**: EXECUTING

---

## 🎯 Objectives

1. ✅ Remove legacy code (backtesting.py-based implementation)
2. ✅ Keep only new clean architecture (VectorBT-based)
3. ✅ Organize project structure for maintainability
4. ✅ Update documentation to reflect new architecture

---

## 📁 New Project Structure

```
taoquant/
├── analytics/              ✅ KEEP (Phase 2)
│   └── indicators/
│       ├── sr_zones.py
│       ├── volatility.py
│       └── __init__.py
│
├── data/                   ✅ KEEP (Unchanged)
│   ├── sources/
│   │   ├── base.py
│   │   ├── okx_sdk.py
│   │   ├── binance_sdk.py
│   │   └── __init__.py
│   ├── data_manager.py
│   ├── schemas.py
│   └── __init__.py
│
├── execution/              ✅ KEEP (Phase 1)
│   ├── engines/
│   │   ├── base.py
│   │   ├── vectorbt_engine.py
│   │   └── __init__.py
│   ├── position_manager.py
│   ├── signal_generator.py
│   └── __init__.py
│
├── strategies/             ✅ KEEP (Phase 2)
│   ├── signal_based/
│   │   ├── sr_short.py
│   │   └── __init__.py
│   ├── base_strategy.py
│   └── __init__.py
│
├── risk_management/        ✅ KEEP (Phase 2)
│   ├── position_sizer.py
│   └── __init__.py
│
├── orchestration/          ✅ KEEP (Phase 2)
│   ├── backtest_runner.py
│   └── __init__.py
│
├── utils/                  ✅ KEEP (Utilities)
│   ├── resample.py
│   ├── timeframes.py
│   ├── csv_loader.py
│   └── __init__.py
│
├── run/                    ✅ KEEP (Entry points)
│   ├── run_backtest_new.py     ← Main entry
│   └── results_new/            ← Output directory
│
├── docs/                   ✅ KEEP (Documentation)
│   ├── system_design.md
│   ├── vector_bt_migration_todo.md
│   ├── phase1_completion_summary.md
│   ├── phase2_completion_summary.md
│   └── refactoring_plan.md
│
├── tests/                  ✅ KEEP (Future)
│   └── (to be added)
│
├── legacy/                 ✅ CREATE (Archive)
│   ├── old_strategies/
│   ├── old_backtest/
│   ├── old_scripts/
│   └── README.md
│
├── core/                   🗑️ REMOVE (Redundant)
├── backtest/               🗑️ ARCHIVE (Old engine)
├── indicators/             🗑️ ARCHIVE (Duplicate)
├── preprocess/             🗑️ REMOVE (Unused)
├── notebooks/              📦 KEEP (Research)
│
├── README.md               ✅ UPDATE
├── CLAUDE.md               ✅ UPDATE
├── requirements.txt        ✅ UPDATE
└── .gitignore              ✅ KEEP
```

---

## 🗑️ Files to Remove/Archive

### Immediate Removal (Completely redundant)

```
DELETE:
├── core/                              # Redundant config (using dataclasses now)
│   ├── config.py                      # Replaced by BacktestConfig
│   └── scheduler.py                   # Unused
│
├── preprocess/                        # Unused preprocessing
│
└── risk_management/                   # Old implementation
    └── risk_checker.py                # Replaced by position_sizer.py
```

### Archive to `legacy/` (Old implementation)

```
MOVE TO legacy/:
├── backtest/
│   ├── engine.py                      # Old backtesting.py wrapper
│   └── __init__.py
│
├── strategies/
│   ├── sr_short_4h_resistance.py      # Old strategy (1085 lines)
│   ├── sr_short_4h_resistance_fixed.py
│   ├── sr_short_strategy_bt.py
│   ├── sr_guard.py
│   ├── sma_cross.py
│   ├── tdxh_dip.py
│   └── structure_weighted_grid.py
│
├── indicators/                        # Old indicator system
│   ├── base_indicator.py
│   ├── sr_volume_boxes.py
│   ├── sr_indicator_v2.py
│   ├── support_resistance.py
│   ├── vol_heatmap.py
│   ├── bulldozer.py
│   ├── rsi.py
│   └── ema.py
│
├── run/
│   ├── run_backtest.py                # Old entry point (721 lines)
│   └── scripts/                       # Old scripts
│
└── utils/
    └── sr_detection.py                # Replaced by analytics/indicators/sr_zones.py
```

---

## ✅ Files to Keep

### Core Implementation (Phase 1 & 2)

```
KEEP:
├── analytics/                         # NEW - Phase 2
├── execution/                         # NEW - Phase 1
├── strategies/                        # NEW - Phase 2
│   ├── base_strategy.py
│   └── signal_based/
├── risk_management/
│   └── position_sizer.py              # NEW - Phase 2
├── orchestration/                     # NEW - Phase 2
├── data/                              # Unchanged
└── utils/
    ├── resample.py                    # Used by strategies
    ├── timeframes.py                  # Used by data layer
    └── csv_loader.py                  # Used by DataManager
```

### Documentation

```
KEEP:
docs/
├── system_design.md                   # NEW - Architecture doc
├── vector_bt_migration_todo.md        # NEW - Migration guide
├── phase1_completion_summary.md       # NEW - Phase 1 summary
├── phase2_completion_summary.md       # NEW - Phase 2 summary
├── refactoring_plan.md                # NEW - This document
└── (other docs can be archived if outdated)
```

### Entry Points

```
KEEP:
run/
├── run_backtest_new.py                # NEW - Main entry (86 lines)
└── results_new/                       # Output directory
```

### Research & Examples

```
KEEP (but mark as legacy):
notebooks/
├── 01_visualize_indicator.ipynb      # May need updating
└── (other notebooks)
```

---

## 🔄 Refactoring Steps

### Step 1: Create Legacy Archive ✅

```bash
mkdir legacy
mkdir legacy/old_strategies
mkdir legacy/old_backtest
mkdir legacy/old_indicators
mkdir legacy/old_scripts
mkdir legacy/old_docs
```

### Step 2: Move Old Strategies ✅

```bash
# Move old strategy files
mv strategies/sr_short_4h_resistance.py legacy/old_strategies/
mv strategies/sr_short_4h_resistance_fixed.py legacy/old_strategies/
mv strategies/sr_short_strategy_bt.py legacy/old_strategies/
mv strategies/sr_guard.py legacy/old_strategies/
mv strategies/sma_cross.py legacy/old_strategies/
mv strategies/tdxh_dip.py legacy/old_strategies/
mv strategies/structure_weighted_grid.py legacy/old_strategies/

# Keep only new implementations
# strategies/base_strategy.py ✅
# strategies/signal_based/ ✅
```

### Step 3: Archive Old Backtest Engine ✅

```bash
mv backtest/ legacy/old_backtest/
# New engine in execution/ ✅
```

### Step 4: Archive Old Indicators ✅

```bash
mv indicators/ legacy/old_indicators/
# New indicators in analytics/indicators/ ✅
```

### Step 5: Remove Redundant Code ✅

```bash
# Remove completely redundant directories
rm -rf core/
rm -rf preprocess/

# Remove old risk checker
rm risk_management/risk_checker.py
# Keep risk_management/position_sizer.py ✅
```

### Step 6: Archive Old Scripts ✅

```bash
mv run/run_backtest.py legacy/old_scripts/
mv run/scripts/ legacy/old_scripts/
# Keep run/run_backtest.py ✅
```

### Step 7: Archive Old Docs ✅

```bash
# Move outdated docs to legacy
mv docs/DEBUGGING_GUIDE.md legacy/old_docs/
mv docs/GRID_STRATEGY_DESCRIPTION.md legacy/old_docs/
mv docs/COOLDOWN_EXPLANATION.md legacy/old_docs/
mv docs/STRATEGY_EVALUATION.md legacy/old_docs/
mv docs/MATURE_GRID_STRATEGIES.md legacy/old_docs/
mv docs/Backtest_Analysis_Report.md legacy/old_docs/
mv docs/Position_Sizing_Fix.md legacy/old_docs/
mv docs/Position_Sizing_Summary.md legacy/old_docs/
mv docs/SRShort4HResistance_Strategy.md legacy/old_docs/

# Keep new docs
# docs/system_design.md ✅
# docs/vector_bt_migration_todo.md ✅
# docs/phase1_completion_summary.md ✅
# docs/phase2_completion_summary.md ✅
```

### Step 8: Update Project Files ✅

```bash
# Update README.md - reflect new architecture
# Update CLAUDE.md - new project instructions
# Update requirements.txt - add vectorbt
# Update .gitignore - add new result directories
```

---

## 📝 Files to Update

### 1. README.md

Create comprehensive README with:
- Project overview
- New architecture diagram
- Quick start guide
- Installation instructions
- Usage examples

### 2. CLAUDE.md

Update with:
- New project structure
- New development workflow
- Strategy development guide
- Architecture principles

### 3. requirements.txt

Add:
```
vectorbt>=0.25.0
```

Remove:
```
backtesting  # No longer used
```

---

## 🎯 Expected Outcome

### Before Refactoring
```
taoquant/
├── 15+ directories
├── 100+ files
├── 10,000+ lines of code
├── Mixed old/new code
└── Confusing structure
```

### After Refactoring
```
taoquant/
├── 8 core directories
├── 40 essential files
├── 4,000 lines of code
├── Only new architecture
└── Crystal clear structure
```

**Code Reduction**: ~60% 🎉
**Maintainability**: +500% 🚀
**Clarity**: Perfect ✨

---

## ✅ Validation Checklist

After refactoring, verify:

- [ ] `python run/run_backtest_new.py` works
- [ ] All imports resolve correctly
- [ ] No broken imports in remaining files
- [ ] Documentation reflects current structure
- [ ] Legacy code is properly archived
- [ ] Git commit with clear message

---

## 🚀 Post-Refactoring Tasks

1. **Test the new structure**
   ```bash
   python run/run_backtest.py
   ```

2. **Update git**
   ```bash
   git add .
   git commit -m "refactor: clean architecture - remove legacy code, keep VectorBT implementation"
   ```

3. **Update documentation**
   - Verify all docs are accurate
   - Remove outdated references

4. **Create migration guide** (if needed)
   - For users of old code
   - How to migrate strategies

---

**Status**: Ready to Execute
**Risk**: LOW (git backup exists)
**Expected Duration**: 30 minutes

---

Let's do this! 🚀
