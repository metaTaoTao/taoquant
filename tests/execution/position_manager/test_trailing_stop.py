"""
Unit tests for trailing stop logic in Position Manager.

Tests the critical bug fix: trailing stop should move DOWN for short positions.
"""

import pytest
from datetime import datetime
from execution.position_manager import (
    PositionManager,
    Position,
    PositionSide,
    ExitRules,
    TrailingStopRule,
    StopLossRule,
    ZeroCostRule,
)


class TestTrailingStopShort:
    """Test trailing stop logic for SHORT positions."""

    def test_trailing_stop_follows_price_down(self):
        """
        Test that trailing stop moves DOWN as price drops (for short).

        This is the bug we fixed: was using max() instead of min().
        """
        # Setup
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(
                distance_atr_mult=5.0,
                offset_atr_mult=2.0  # Net 3 ATR
            ),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        # Add position: SHORT at $120,000
        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=120000,
            entry_atr=2000,
            side=PositionSide.SHORT,
            entry_size=1.0,
            exit_rules=exit_rules
        )

        # Mark TP1 as hit so trailing stop is active
        pos.tp1_hit = True

        # Price drops to $115,000 (profit!)
        pm.check_exits(bar_idx=1, price=115000, atr=2000)

        # Trailing stop should be: $115,000 + (3 * 2000) = $121,000
        assert pos.trailing_stop_price == pytest.approx(121000, rel=1e-6)
        assert pos.best_price == 115000

        # Price drops further to $110,000 (more profit!)
        pm.check_exits(bar_idx=2, price=110000, atr=2000)

        # Trailing stop should move DOWN: $110,000 + $6,000 = $116,000
        assert pos.trailing_stop_price == pytest.approx(116000, rel=1e-6)
        assert pos.best_price == 110000

    def test_trailing_stop_does_not_move_up_for_short(self):
        """
        Test that trailing stop does NOT move UP when price rises (for short).

        Once set, it should only tighten, never loosen.
        """
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(distance_atr_mult=5.0, offset_atr_mult=2.0),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=120000,
            entry_atr=2000,
            side=PositionSide.SHORT,
            entry_size=1.0,
            exit_rules=exit_rules
        )
        pos.tp1_hit = True

        # Price drops to $110,000
        pm.check_exits(bar_idx=1, price=110000, atr=2000)
        stop_at_low = pos.trailing_stop_price  # $116,000

        # Price rises back to $115,000
        pm.check_exits(bar_idx=2, price=115000, atr=2000)

        # Trailing stop should NOT move up (should stay at $116,000)
        assert pos.trailing_stop_price == stop_at_low
        assert pos.best_price == 110000  # Best price doesn't change either

    def test_trailing_stop_triggers_exit(self):
        """Test that exit is triggered when price hits trailing stop."""
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(distance_atr_mult=5.0, offset_atr_mult=2.0),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=120000,
            entry_atr=2000,
            side=PositionSide.SHORT,
            entry_size=1.0,
            exit_rules=exit_rules
        )
        pos.tp1_hit = True

        # Price drops to $110,000
        pm.check_exits(bar_idx=1, price=110000, atr=2000)
        # Trailing stop = $116,000

        # Price rises to $116,000 (hits stop)
        exits = pm.check_exits(bar_idx=2, price=116000, atr=2000)

        # Should generate TP2 exit order
        assert len(exits) == 1
        assert exits[0].order_type.value == 'TP2'
        assert exits[0].exit_fraction == 1.0
        assert exits[0].price == 116000

        # Position should be closed
        assert pm.get_position_count() == 0

    def test_zero_cost_tp1_then_trailing_stop(self):
        """
        Test full lifecycle: TP1 (zero-cost) → Trailing stop → TP2.

        This simulates the real strategy flow.
        """
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(distance_atr_mult=5.0, offset_atr_mult=2.0),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=120000,
            entry_atr=2000,
            side=PositionSide.SHORT,
            entry_size=1.0,
            exit_rules=exit_rules
        )

        # Step 1: Price drops to $110,000
        # Risk = 2000 * 3 = $6,000
        # Profit = $120,000 - $110,000 = $10,000
        # Profit ratio = $10,000 / $6,000 = 1.67R (not yet 3.33R)
        exits = pm.check_exits(bar_idx=1, price=110000, atr=2000)
        assert len(exits) == 0  # No TP1 yet
        assert not pos.tp1_hit

        # Step 2: Price drops to $100,000
        # Profit = $120,000 - $100,000 = $20,000
        # Profit ratio = $20,000 / $6,000 = 3.33R (triggers TP1!)
        exits = pm.check_exits(bar_idx=2, price=100000, atr=2000)
        assert len(exits) == 1
        assert exits[0].order_type.value == 'TP1'
        assert exits[0].exit_fraction == 0.30  # Exit 30%
        assert pos.tp1_hit
        assert pos.remaining_size == pytest.approx(0.7, rel=1e-6)

        # Step 3: Price drops to $95,000 (more profit)
        exits = pm.check_exits(bar_idx=3, price=95000, atr=2000)
        # Trailing stop = $95,000 + $6,000 = $101,000
        assert pos.trailing_stop_price == pytest.approx(101000, rel=1e-6)
        assert len(exits) == 0  # No exit yet

        # Step 4: Price rises to $101,000 (hits trailing stop)
        exits = pm.check_exits(bar_idx=4, price=101000, atr=2000)
        assert len(exits) == 1
        assert exits[0].order_type.value == 'TP2'
        assert exits[0].exit_fraction == 1.0  # Close remaining 70%

        # Position closed
        assert pm.get_position_count() == 0


class TestTrailingStopLong:
    """Test trailing stop logic for LONG positions."""

    def test_trailing_stop_follows_price_up(self):
        """Test that trailing stop moves UP as price rises (for long)."""
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(distance_atr_mult=5.0, offset_atr_mult=2.0),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=100000,
            entry_atr=2000,
            side=PositionSide.LONG,
            entry_size=1.0,
            exit_rules=exit_rules
        )
        pos.tp1_hit = True

        # Price rises to $105,000 (profit!)
        pm.check_exits(bar_idx=1, price=105000, atr=2000)
        # Trailing stop = $105,000 - $6,000 = $99,000
        assert pos.trailing_stop_price == pytest.approx(99000, rel=1e-6)

        # Price rises to $110,000 (more profit!)
        pm.check_exits(bar_idx=2, price=110000, atr=2000)
        # Trailing stop moves UP: $110,000 - $6,000 = $104,000
        assert pos.trailing_stop_price == pytest.approx(104000, rel=1e-6)

    def test_trailing_stop_does_not_move_down_for_long(self):
        """Test that trailing stop does NOT move DOWN when price drops (for long)."""
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=TrailingStopRule(distance_atr_mult=5.0, offset_atr_mult=2.0),
            take_profit=[ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=100000,
            entry_atr=2000,
            side=PositionSide.LONG,
            entry_size=1.0,
            exit_rules=exit_rules
        )
        pos.tp1_hit = True

        # Price rises to $110,000
        pm.check_exits(bar_idx=1, price=110000, atr=2000)
        stop_at_high = pos.trailing_stop_price  # $104,000

        # Price drops to $105,000
        pm.check_exits(bar_idx=2, price=105000, atr=2000)

        # Trailing stop should NOT move down (should stay at $104,000)
        assert pos.trailing_stop_price == stop_at_high


class TestStopLoss:
    """Test stop loss logic."""

    def test_stop_loss_short(self):
        """Test stop loss for short position."""
        pm = PositionManager()
        exit_rules = ExitRules(
            stop_loss=StopLossRule(atr_mult=3.0),
            trailing_stop=None,
            take_profit=[]
        )

        pos = pm.add_position(
            entry_idx=0,
            entry_time=datetime(2025, 1, 1),
            entry_price=120000,
            entry_atr=2000,
            side=PositionSide.SHORT,
            entry_size=1.0,
            exit_rules=exit_rules
        )

        # SL = $120,000 + (3 * 2000) = $126,000

        # Price rises to $125,000 (approaching SL)
        exits = pm.check_exits(bar_idx=1, price=125000, atr=2000)
        assert len(exits) == 0  # No exit yet

        # Price rises to $126,000 (hits SL)
        exits = pm.check_exits(bar_idx=2, price=126000, atr=2000)
        assert len(exits) == 1
        assert exits[0].order_type.value == 'SL'
        assert exits[0].exit_fraction == 1.0

        # Position closed
        assert pm.get_position_count() == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
