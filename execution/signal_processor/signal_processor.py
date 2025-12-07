"""
Signal Processor.

Converts strategy signals + exit rules into executable orders.
Uses Position Manager for position tracking and exit execution.
"""

from __future__ import annotations
from typing import Dict, Optional
import pandas as pd
import numpy as np

from execution.position_manager import PositionManager, PositionSide
from execution.position_manager.exit_rules import ExitRules
from execution.signal_processor.models import EntrySignal, SignalType


class SignalProcessor:
    """
    Signal Processor - converts signals to orders.

    Architecture:
    Strategy (WHAT) → Signal Processor (HOW) → Engine (SIMULATE)

    Responsibilities:
    - Convert entry signals to entry orders
    - Track open positions using Position Manager
    - Generate exit orders based on exit rules
    - Handle 2B reversals and special signal types

    Does NOT:
    - Generate signals (that's Strategy's job)
    - Define exit rules (that's Strategy's job)
    - Execute orders (that's Engine's job)
    """

    def __init__(self, max_concurrent_positions: int = 1):
        """
        Initialize Signal Processor.

        Parameters
        ----------
        max_concurrent_positions : int
            Maximum number of concurrent positions
        """
        self.max_concurrent_positions = max_concurrent_positions

    def process(
        self,
        entry_signals: EntrySignal,
        exit_rules: ExitRules,
        exit_rules_2b: Optional[ExitRules],
        data: pd.DataFrame,
        b2_config: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Process signals into orders.

        Parameters
        ----------
        entry_signals : EntrySignal
            Entry signal specification (where to enter)
        exit_rules : ExitRules
            Exit rules for normal entries
        exit_rules_2b : ExitRules, optional
            Exit rules for 2B reversal entries
        data : pd.DataFrame
            OHLCV data with indicators (must have 'close', 'atr' columns)
        b2_config : dict, optional
            2B reversal configuration:
            - time_window_hours: float (default: 48.0)
            - breakout_threshold_pct: float (default: 0.0)
            - risk_multiplier: float (default: 4.0)

        Returns
        -------
        pd.DataFrame
            Orders with columns:
            - orders: float (negative for entry, positive for exit, 0 for no order)
            - direction: str ('long' or 'short')
            - order_types: str (ENTRY, TP1, TP2, SL, FORCE_CLOSE, 2B_ENTRY)
        """
        # Initialize position manager
        pm = PositionManager(max_positions=self.max_concurrent_positions)

        # Initialize order arrays
        orders = pd.Series(0.0, index=data.index, dtype=float)
        direction = pd.Series(entry_signals.side, index=data.index, dtype=str)
        order_types = pd.Series('', index=data.index, dtype=object)

        # Track which zones have been used for entries
        used_zones = set()

        # Track broken zones for 2B reversal (if applicable)
        broken_zones = {}

        # 2B configuration defaults
        if b2_config is None:
            b2_config = {}
        b2_time_window = b2_config.get('time_window_hours', 48.0)
        b2_threshold_pct = b2_config.get('breakout_threshold_pct', 0.0)
        b2_risk_mult = b2_config.get('risk_multiplier', 4.0)
        b2_enabled = exit_rules_2b is not None

        # Process bar by bar
        for i in range(len(data)):
            bar_idx = i
            current_price = data['close'].iloc[i]
            # Use HTF ATR for trailing stop if available, otherwise fallback to regular ATR
            # HTF ATR is used for exit management (trailing stop), regular ATR for position sizing
            if 'atr_htf' in data.columns and pd.notna(data['atr_htf'].iloc[i]):
                current_atr = data['atr_htf'].iloc[i]  # Use 4H ATR for trailing stop
            else:
                current_atr = data['atr'].iloc[i] if pd.notna(data['atr'].iloc[i]) else 0.0
            current_time = data.index[i]

            # Track if we had an exit this bar (prevent same-bar re-entry)
            had_exit_this_bar = False

            # Step 1: Check exits for existing positions
            exit_orders = pm.check_exits(
                bar_idx=bar_idx,
                price=current_price,
                atr=current_atr
            )

            for exit_order in exit_orders:
                # Record exit order
                orders.iloc[i] = exit_order.exit_fraction
                order_types.iloc[i] = exit_order.order_type.value
                had_exit_this_bar = True

                # If this was a stop loss on a normal entry, track for 2B reversal
                if exit_order.order_type.value == 'SL' and b2_enabled:
                    if not exit_order.is_2b_trade and exit_order.zone_key:
                        # Record broken zone (using entry info from OrderAction)
                        broken_zones[exit_order.zone_key] = {
                            'stop_time': current_time,
                            'stop_price': current_price,
                            'entry_price': exit_order.entry_price,
                            'entry_atr': exit_order.entry_atr,
                            'zone_bottom': exit_order.zone_key[0],
                            'zone_top': exit_order.zone_key[1],
                        }
                        print(f"[2B Tracker] Zone {exit_order.zone_key} broken at {current_time}, SL @ ${current_price:,.2f}")

                # Clear zone from used_zones when position fully closed
                if exit_order.exit_fraction == 1.0 and exit_order.zone_key:
                    used_zones.discard(exit_order.zone_key)

            # Step 2: Check for new entry signals (if no positions and no exit this bar)
            if pm.get_position_count() < self.max_concurrent_positions and not had_exit_this_bar:
                # Priority 1: Check 2B reversal opportunities (INDEPENDENT of normal signals)
                b2_entry_triggered = False
                b2_zone_key = None

                if b2_enabled and broken_zones:
                    # Check all broken zones for 2B reversal
                    zones_to_remove = []
                    for zone_key, zone_info in list(broken_zones.items()):
                        # Time window check
                        time_diff = (current_time - zone_info['stop_time']).total_seconds() / 3600
                        if time_diff > b2_time_window:
                            zones_to_remove.append(zone_key)
                            continue

                        # Price check: closed below zone_bottom (for short)
                        zone_bottom = zone_info['zone_bottom']
                        breakout_threshold = zone_bottom * (1 - b2_threshold_pct / 100)

                        if entry_signals.side == 'short' and current_price <= breakout_threshold:
                            # 2B Reversal triggered!
                            b2_entry_triggered = True
                            b2_zone_key = zone_key
                            zones_to_remove.append(zone_key)
                            print(f"[2B Reversal] Triggered at {current_time}!")
                            print(f"  Zone: ${zone_info['zone_bottom']:,.2f} - ${zone_info['zone_top']:,.2f}")
                            print(f"  Stop time: {zone_info['stop_time']}, Window: {time_diff:.1f}h")
                            print(f"  Current price: ${current_price:,.2f} (below ${zone_bottom:,.2f})")
                            break

                    # Clean up expired/used zones
                    for zk in zones_to_remove:
                        del broken_zones[zk]

                # Execute entry (2B takes priority over normal)
                if b2_entry_triggered:
                    # 2B Reversal Entry
                    # Use HTF ATR for entry_atr (for trailing stop calculation)
                    entry_atr = data['atr_htf'].iloc[i] if 'atr_htf' in data.columns and pd.notna(data['atr_htf'].iloc[i]) else current_atr
                    pm.add_position(
                        entry_idx=bar_idx,
                        entry_time=current_time,
                        entry_price=current_price,
                        entry_atr=entry_atr,  # Use HTF ATR for trailing stop
                        side=PositionSide.SHORT if entry_signals.side == 'short' else PositionSide.LONG,
                        entry_size=b2_risk_mult,
                        exit_rules=exit_rules_2b,
                        zone_key=b2_zone_key,
                        is_2b_trade=True,
                    )

                    # Create 2B entry order
                    entry_order_size = -b2_risk_mult if entry_signals.side == 'short' else b2_risk_mult
                    orders.iloc[i] = entry_order_size
                    order_types.iloc[i] = '2B_ENTRY'

                    # Mark zone as used
                    if b2_zone_key is not None:
                        used_zones.add(b2_zone_key)

                # Priority 2: Check normal entry signals
                elif entry_signals.signals.iloc[i]:
                    signal_type = entry_signals.signal_type.iloc[i]
                    risk_multiplier = entry_signals.risk_multipliers.iloc[i]
                    zone_key = entry_signals.zone_keys.iloc[i] if entry_signals.zone_keys is not None else None

                    # Check zone constraints
                    can_enter = True
                    if zone_key is not None:
                        # Convert to tuple if needed
                        if isinstance(zone_key, (list, np.ndarray)):
                            zone_key = tuple(zone_key)
                        elif pd.isna(zone_key):
                            zone_key = None

                        # Check if zone already used
                        if zone_key is not None and zone_key in used_zones:
                            can_enter = False

                    if can_enter:
                        # Use normal exit rules
                        current_exit_rules = exit_rules
                        is_2b_trade = False
                        order_type_label = 'ENTRY'

                        # Use HTF ATR for entry_atr (for trailing stop calculation)
                        entry_atr = data['atr_htf'].iloc[i] if 'atr_htf' in data.columns and pd.notna(data['atr_htf'].iloc[i]) else current_atr
                        # Add position to manager
                        pm.add_position(
                            entry_idx=bar_idx,
                            entry_time=current_time,
                            entry_price=current_price,
                            entry_atr=entry_atr,  # Use HTF ATR for trailing stop
                            side=PositionSide.SHORT if entry_signals.side == 'short' else PositionSide.LONG,
                            entry_size=risk_multiplier,
                            exit_rules=current_exit_rules,
                            zone_key=zone_key,
                            is_2b_trade=is_2b_trade,
                        )

                        # Create entry order
                        entry_order_size = -risk_multiplier if entry_signals.side == 'short' else risk_multiplier
                        orders.iloc[i] = entry_order_size
                        order_types.iloc[i] = order_type_label

                        # Mark zone as used
                        if zone_key is not None:
                            used_zones.add(zone_key)

        # Step 3: Force close any remaining positions at end
        if pm.get_position_count() > 0:
            last_bar_idx = len(data) - 1
            final_price = data['close'].iloc[last_bar_idx]
            force_close_orders = pm.force_close_all(
                bar_idx=last_bar_idx,
                price=final_price
            )
            for fc_order in force_close_orders:
                orders.iloc[last_bar_idx] = fc_order.exit_fraction
                order_types.iloc[last_bar_idx] = fc_order.order_type.value

        # Return orders DataFrame
        return pd.DataFrame({
            'orders': orders,
            'direction': direction,
            'order_types': order_types,
        }, index=data.index)
