# VectorBT Migration TODO List

> **Project**: TaoQuant VectorBT Migration
> **Date**: 2025-12-03
> **Lead**: System Architect & Quant Research Lead
> **Objective**: Migrate from backtesting.py to VectorBT with clean, maintainable architecture

---

## 📋 Migration Overview

### Current State
- **Engine**: backtesting.py (limited to integer positions)
- **Workaround**: Custom VirtualTrade system (~600 lines)
- **Pain Points**:
  - Fractional position support requires complex workarounds
  - Lost native backtesting.py features (stats, plotting)
  - Maintaining two parallel systems

### Target State
- **Engine**: VectorBT Pro (native fractional positions, 100x faster)
- **Architecture**: Clean separation of signal generation and execution
- **Benefits**:
  - Native fractional position support
  - Vectorized backtesting (100x speedup)
  - Clean, maintainable codebase
  - Extensible for multi-factor alpha research

---

## 🎯 Migration Phases

### Phase 1: Core Engine Refactoring (Priority: CRITICAL)

**Objective**: Build a clean, production-grade backtesting abstraction layer

#### 1.1 Design Backtest Engine Interface
- [ ] **File**: `backtest/engine_interface.py`
  - [ ] Define `BacktestEngine` abstract base class
  - [ ] Define `BacktestResult` dataclass
  - [ ] Define `PositionManager` interface
  - [ ] Ensure engine-agnostic design (future: Nautilus, custom engine)

#### 1.2 Implement VectorBT Engine
- [ ] **File**: `backtest/vectorbt_engine.py`
  - [ ] `VectorBTEngine` class implementation
  - [ ] Signal-to-portfolio conversion logic
  - [ ] Position sizing utilities
  - [ ] Commission/slippage handling
  - [ ] Multi-position tracking (replace VirtualTrade)

#### 1.3 Position Management System
- [ ] **File**: `backtest/position_manager.py`
  - [ ] `Position` dataclass (clean replacement for VirtualTrade)
  - [ ] `PositionTracker` class (tracks multiple concurrent positions)
  - [ ] Entry/exit logic separation
  - [ ] SL/TP management utilities

#### 1.4 Signal Generation Framework
- [ ] **File**: `backtest/signal_generator.py`
  - [ ] `SignalGenerator` abstract base class
  - [ ] `Signal` dataclass (entry/exit/size/reason)
  - [ ] Signal validation utilities
  - [ ] Signal aggregation for multi-strategy

---

### Phase 2: Strategy Refactoring (Priority: HIGH)

**Objective**: Refactor strategies to use new clean architecture

#### 2.1 Strategy Base Class Redesign
- [ ] **File**: `strategies/base_strategy.py`
  - [ ] New `BaseStrategy` abstract class
  - [ ] Separation of concerns:
    - [ ] `compute_indicators()` - pure indicator calculation
    - [ ] `generate_signals()` - signal logic only
    - [ ] `calculate_position_size()` - risk management
  - [ ] Clean state management (no more backtesting.py `self.data`)

#### 2.2 SRShort4HResistance Migration
- [ ] **File**: `strategies/sr_short_4h_resistance_v2.py`
  - [ ] Extract zone detection to separate module
  - [ ] Refactor signal generation to functional style
  - [ ] Remove backtesting.py dependencies
  - [ ] Implement new `BaseStrategy` interface
  - [ ] Split into logical components:
    - [ ] `sr_zones.py` - Zone detection logic
    - [ ] `sr_signals.py` - Signal generation
    - [ ] `sr_strategy.py` - Main strategy orchestration

#### 2.3 Position Sizing & Risk Management
- [ ] **File**: `risk_management/position_sizer.py`
  - [ ] Extract position sizing from strategy
  - [ ] Implement multiple sizing methods:
    - [ ] Fixed risk per trade
    - [ ] Kelly criterion
    - [ ] Volatility-based (ATR)
  - [ ] Portfolio-level risk constraints

---

### Phase 3: Entry Point Refactoring (Priority: HIGH)

**Objective**: Clean, production-grade backtesting runner

#### 3.1 New Backtest Runner
- [ ] **File**: `run/backtest_runner.py`
  - [ ] `BacktestRunner` class (engine-agnostic)
  - [ ] Configuration management (dataclass-based)
  - [ ] Result persistence (HDF5/Parquet)
  - [ ] Progress tracking and logging

#### 3.2 Run Script Redesign
- [ ] **File**: `run/run_backtest.py`
  - [ ] Clean configuration section
  - [ ] Minimal boilerplate
  - [ ] Clear separation: config → runner → results
  - [ ] Remove all engine-specific logic

#### 3.3 Results Export System
- [ ] **File**: `backtest/results_exporter.py`
  - [ ] Unified results format (engine-agnostic)
  - [ ] CSV/Parquet/JSON export
  - [ ] Interactive HTML reports (Bokeh/Plotly)
  - [ ] Metrics dashboard

---

### Phase 4: Testing & Validation (Priority: CRITICAL)

**Objective**: Ensure correctness and performance

#### 4.1 Unit Tests
- [ ] **File**: `tests/test_vectorbt_engine.py`
  - [ ] Signal generation tests
  - [ ] Position sizing tests
  - [ ] PnL calculation validation

#### 4.2 Integration Tests
- [ ] **File**: `tests/test_sr_strategy_migration.py`
  - [ ] Compare old vs new results
  - [ ] Verify trade consistency
  - [ ] Performance benchmarks

#### 4.3 Validation Suite
- [ ] **File**: `tests/validation/compare_engines.py`
  - [ ] Side-by-side comparison tool
  - [ ] Metrics comparison (Sharpe, Sortino, MaxDD)
  - [ ] Trade-by-trade diff analysis

---

### Phase 5: Documentation & Examples (Priority: MEDIUM)

#### 5.1 Architecture Documentation
- [ ] **File**: `docs/architecture/backtesting_system.md`
  - [ ] System overview diagram
  - [ ] Component interaction flows
  - [ ] Design decisions rationale

#### 5.2 Migration Guide
- [ ] **File**: `docs/guides/migration_from_backtestingpy.md`
  - [ ] Step-by-step migration guide
  - [ ] Common patterns and pitfalls
  - [ ] Code examples

#### 5.3 Strategy Development Guide
- [ ] **File**: `docs/guides/strategy_development.md`
  - [ ] How to write a new strategy
  - [ ] Signal generation patterns
  - [ ] Risk management integration

#### 5.4 Example Strategies
- [ ] **File**: `examples/simple_sma_cross.py`
  - [ ] Minimal working example
  - [ ] Well-commented code
  - [ ] Best practices demonstration

---

## 🏗️ Detailed Implementation Plan

### Phase 1.1: Engine Interface Design

```python
# backtest/engine_interface.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, Optional
import pandas as pd

@dataclass
class BacktestConfig:
    """Engine-agnostic backtest configuration."""
    initial_cash: float
    commission: float
    slippage: float
    # ... more config

@dataclass
class BacktestResult:
    """Standardized backtest results."""
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict
    positions: pd.DataFrame
    # ... more fields

class BacktestEngine(ABC):
    """Abstract base class for all backtest engines."""

    @abstractmethod
    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        config: BacktestConfig
    ) -> BacktestResult:
        """Run backtest with given signals."""
        pass
```

### Phase 2.2: Strategy Refactoring Pattern

**Before (backtesting.py style)**:
```python
class SRShort4HResistance(Strategy):
    def init(self):
        # Mix of indicator calculation and state management
        self.zones = []
        self.virtual_trades = []
        ...

    def next(self):
        # Mix of signal detection, position management, and execution
        signal = self._detect_signal()
        self._manage_exits()
        if signal:
            self.sell(size=...)
```

**After (VectorBT style - Clean Architecture)**:
```python
class SRShort4HResistance(BaseStrategy):
    """
    Clean separation of concerns:
    1. Indicators → compute_indicators()
    2. Signals → generate_signals()
    3. Sizing → calculate_position_size()
    """

    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Pure function: data → indicators."""
        zones = detect_sr_zones(data)
        return data.assign(
            zone_top=zones['top'],
            zone_bottom=zones['bottom']
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Pure function: data → signals."""
        entries = detect_zone_touch(data)
        exits = detect_exit_conditions(data)
        return pd.DataFrame({
            'entry': entries,
            'exit': exits,
            'direction': 'short'
        })

    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series
    ) -> pd.Series:
        """Pure function: data + equity → sizes."""
        return calculate_risk_based_size(
            data=data,
            equity=equity,
            risk_pct=0.005,
            atr=data['atr']
        )
```

---

## 📊 Success Metrics

### Code Quality
- [ ] Test coverage > 80%
- [ ] No backtesting.py dependencies in strategies
- [ ] All functions < 50 lines
- [ ] Type hints coverage 100%

### Performance
- [ ] Backtest speed > 10x improvement
- [ ] Memory usage < 50% of current

### Maintainability
- [ ] Clear module boundaries
- [ ] Documentation for all public APIs
- [ ] Examples for all core components

---

## 🚨 Critical Decisions

### Decision 1: VectorBT vs VectorBT Pro
- **Status**: TO DECIDE
- **Options**:
  - VectorBT (free, open-source)
  - VectorBT Pro (paid, more features)
- **Recommendation**: Start with free version, upgrade if needed

### Decision 2: Signal Storage Format
- **Status**: TO DECIDE
- **Options**:
  - DataFrame with boolean columns (simple)
  - Custom Signal dataclass list (flexible)
  - Structured array (performance)
- **Recommendation**: DataFrame for simplicity, optimize later if needed

### Decision 3: Multi-Position Tracking
- **Status**: TO DECIDE
- **Options**:
  - VectorBT native groups
  - Custom PositionTracker
- **Recommendation**: Start with custom tracker for full control

---

## 📅 Timeline Estimate

### Week 1: Foundation
- Day 1-2: Phase 1.1-1.2 (Engine interface + VectorBT implementation)
- Day 3-4: Phase 1.3-1.4 (Position manager + Signal framework)
- Day 5: Phase 2.1 (Strategy base class)

### Week 2: Strategy Migration
- Day 1-3: Phase 2.2 (SRShort4HResistance refactoring)
- Day 4-5: Phase 3.1-3.2 (Runner + Entry point)

### Week 3: Testing & Polish
- Day 1-2: Phase 4 (Testing & validation)
- Day 3-4: Phase 5 (Documentation)
- Day 5: Final review and polish

**Total Estimated Time**: 15 working days (3 weeks)

---

## 🔄 Rollback Plan

If VectorBT migration has critical issues:
1. Keep old backtesting.py code in `legacy/` folder
2. Feature flag to switch engines
3. Side-by-side comparison tool to validate

---

## 📚 References

- [VectorBT Documentation](https://vectorbt.dev/)
- [Clean Architecture Principles](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Quantitative Trading Architecture Patterns](https://www.quantstart.com/)

---

## 🎯 Next Steps

1. Review this TODO list with stakeholders
2. Approve architecture decisions
3. Start Phase 1.1 implementation
4. Set up CI/CD for automated testing

---

**Last Updated**: 2025-12-03
**Status**: DRAFT - Awaiting Approval
