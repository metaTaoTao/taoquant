from __future__ import annotations

import math
from typing import Dict, List, Tuple

import backtrader as bt

from utils import risk, sizing


class StructureWeightedGrid(bt.Strategy):
    """Backtrader implementation of the structure-weighted grid skeleton.

    Milestone M3 extends the basic framework with geometric grids, edge-weighted
    sizing and hit-count decay, while keeping risk logic for later milestones.
    """

    params = dict(
        order_size=0.05,  # total quantity budget per side
        log_orders=True,
        price_rounding=2,
        grid_gap_pct=0.0018,
        alpha=2.0,
        max_levels_side=10,
        decay_k=2.0,
        # Risk control parameters
        exposure_thresh=0.7,  # midline rebalance threshold
        mid_band_pct=0.001,  # midline band percentage (0.1%)
        micro_atr_ratio=0.6,  # micro-oscillation cooldown threshold
        breakout_epsilon_mult=0.1,  # epsilon = atr * this multiplier
        breakout_atr_ratio=1.0,  # ATR expansion threshold for breakout
    )

    def __init__(self) -> None:
        self._long_hits: Dict[float, int] = {}
        self._short_hits: Dict[float, int] = {}
        self._tracked_orders: Dict[int, Tuple[str, float, bt.Order]] = {}
        # Breakout state tracking
        self._below_count = 0
        self._above_count = 0
        self._in_breakout = False
        # Trade logging
        self._trade_log: List[Dict] = []
        self._order_count = 0
        self._fill_count = 0

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def log(self, msg: str) -> None:
        if not self.p.log_orders:
            return
        dt = self.data.datetime.datetime(0)
        print(f"{dt:%Y-%m-%d %H:%M} | {msg}")

    def _cancel_all(self) -> None:
        for side, price, order in list(self._tracked_orders.values()):
            if order.alive():
                self.cancel(order)
        # keep entries; notify_order will remove them once cancellation is confirmed

    def _round_price(self, price: float) -> float:
        return round(price, int(self.p.price_rounding))

    def _round_levels(self, levels: List[float]) -> List[float]:
        unique: List[float] = []
        seen: set[float] = set()
        for level in levels:
            rounded = self._round_price(level)
            if not math.isfinite(rounded):
                continue
            if rounded in seen:
                continue
            unique.append(rounded)
            seen.add(rounded)
        return unique

    # ------------------------------------------------------------------
    # Core strategy logic
    # ------------------------------------------------------------------
    def next(self) -> None:  # type: ignore[override]
        support = float(self.data.support[0]) if math.isfinite(self.data.support[0]) else math.nan  # type: ignore[attr-defined]
        resistance = float(self.data.resistance[0]) if math.isfinite(self.data.resistance[0]) else math.nan  # type: ignore[attr-defined]
        range_valid = bool(self.data.range_valid[0]) if not math.isnan(float(self.data.range_valid[0])) else False  # type: ignore[attr-defined]
        midline = float(self.data.midline[0]) if math.isfinite(self.data.midline[0]) else math.nan  # type: ignore[attr-defined]
        atr = float(self.data.atr[0]) if math.isfinite(self.data.atr[0]) else math.nan  # type: ignore[attr-defined]
        atr_short = float(self.data.atr_short[0]) if math.isfinite(self.data.atr_short[0]) else math.nan  # type: ignore[attr-defined]
        close = float(self.data.close[0])

        # Debug logging for first few bars
        if len(self.data) <= 5:
            self.log(
                f"DEBUG: close={close:.2f}, support={support:.2f}, resistance={resistance:.2f}, "
                f"range_valid={range_valid}, in_range={support < close < resistance if (math.isfinite(support) and math.isfinite(resistance)) else False}"
            )

        # Check for breakout
        epsilon = atr * self.p.breakout_epsilon_mult if math.isfinite(atr) else 0.0
        self._below_count, self._above_count, breakout = risk.update_breakout_state(
            close=close,
            support=support,
            resistance=resistance,
            epsilon=epsilon,
            atr_short=atr_short,
            atr_long=atr,
            ratio_threshold=self.p.breakout_atr_ratio,
            below_count=self._below_count,
            above_count=self._above_count,
        )

        if breakout:
            self._in_breakout = True
            self._cancel_all()
            # Close all positions
            if self.position:
                self.log(f"BREAKOUT detected: closing position size={self.position.size}")
                self.close()
            return

        # Reset breakout state if back in range
        if range_valid and support < close < resistance:
            self._in_breakout = False

        if not range_valid or not (math.isfinite(support) and math.isfinite(resistance)):
            if len(self.data) <= 5:
                self.log(f"DEBUG: Skipping - range_valid={range_valid}, support={support:.2f}, resistance={resistance:.2f}")
            self._cancel_all()
            return
        if close <= support or close >= resistance:
            if len(self.data) <= 5:
                self.log(f"DEBUG: Skipping - price outside range: close={close:.2f}, support={support:.2f}, resistance={resistance:.2f}")
            self._cancel_all()
            return

        # Check micro-oscillation cooldown
        if risk.is_cooldown(atr_short, atr, self.p.micro_atr_ratio):
            self.log("Micro-oscillation cooldown: skipping grid placement")
            return

        # Midline inventory reset
        net_position = float(self.position.size) if self.position else 0.0
        max_position = self.p.order_size * self.p.max_levels_side * 2  # rough estimate
        rebalance_qty = risk.midline_rebalance(
            price=close,
            midline=midline,
            band_pct=self.p.mid_band_pct,
            net_position=net_position,
            exposure_thresh=self.p.exposure_thresh,
            max_position=max_position,
        )
        if abs(rebalance_qty) > 1e-6:
            self.log(f"Midline rebalance: reducing position by {rebalance_qty:.6f}")
            if rebalance_qty > 0:
                self.sell(size=abs(rebalance_qty), exectype=bt.Order.Market)
            else:
                self.buy(size=abs(rebalance_qty), exectype=bt.Order.Market)

        buy_raw, sell_raw = sizing.geometric_grid(
            base_price=close,
            gap_pct=self.p.grid_gap_pct,
            support=support,
            resistance=resistance,
            max_levels_side=self.p.max_levels_side,
        )

        buy_prices = self._round_levels(buy_raw)
        sell_prices = self._round_levels(sell_raw)

        if not buy_prices and not sell_prices:
            if len(self.data) <= 5:
                self.log(
                    f"DEBUG: No grid prices generated - buy_raw={len(buy_raw)}, sell_raw={len(sell_raw)}, "
                    f"close={close:.2f}, support={support:.2f}, resistance={resistance:.2f}, gap={self.p.grid_gap_pct}"
                )
            self._cancel_all()
            return

        self._long_hits = sizing.decay_hit_counts(self._long_hits, buy_prices)
        self._short_hits = sizing.decay_hit_counts(self._short_hits, sell_prices)

        long_weights = sizing.edge_weights(
            buy_prices,
            support,
            resistance,
            side="long",
            alpha=self.p.alpha,
            hit_counts=self._long_hits,
            decay_k=self.p.decay_k,
        )
        short_weights = sizing.edge_weights(
            sell_prices,
            support,
            resistance,
            side="short",
            alpha=self.p.alpha,
            hit_counts=self._short_hits,
            decay_k=self.p.decay_k,
        )

        long_qty = sizing.allocate_quantities(buy_prices, long_weights, self.p.order_size)
        short_qty = sizing.allocate_quantities(sell_prices, short_weights, self.p.order_size)

        self._cancel_all()

        for price, qty, weight in zip(buy_prices, long_qty, long_weights):
            if qty <= 0:
                continue
            order = self.buy(exectype=bt.Order.Limit, price=price, size=qty)
            self._tracked_orders[order.ref] = ("long", price, order)
            self.log(
                "BUY grid order @{price:.4f} qty={qty:.6f} w={weight:.4f}".format(
                    price=price,
                    qty=qty,
                    weight=weight,
                )
            )

        for price, qty, weight in zip(sell_prices, short_qty, short_weights):
            if qty <= 0:
                continue
            order = self.sell(exectype=bt.Order.Limit, price=price, size=qty)
            self._tracked_orders[order.ref] = ("short", price, order)
            self.log(
                "SELL grid order @{price:.4f} qty={qty:.6f} w={weight:.4f}".format(
                    price=price,
                    qty=qty,
                    weight=weight,
                )
            )

    def notify_order(self, order: bt.Order) -> None:  # type: ignore[override]
        info = self._tracked_orders.get(order.ref)
        if info is None:
            return
        side, price, _ = info

        if order.status in [bt.Order.Partial, bt.Order.Completed]:
            self._fill_count += 1
            self.log(
                "Filled {side} @ {price:.4f} (size={size:.6f}, fee={fee:.6f})".format(
                    side="BUY" if order.isbuy() else "SELL",
                    price=order.executed.price,
                    size=order.executed.size,
                    fee=order.executed.comm,
                )
            )
            # Log trade
            self._trade_log.append(
                {
                    "time": self.data.datetime.datetime(0),
                    "side": "BUY" if order.isbuy() else "SELL",
                    "price": order.executed.price,
                    "size": order.executed.size,
                    "fee": order.executed.comm,
                    "grid_price": price,
                }
            )
            if order.status == bt.Order.Completed:
                self._tracked_orders.pop(order.ref, None)
                if side == "long":
                    sizing.update_hit_counts(self._long_hits, price, order.executed.size)
                else:
                    sizing.update_hit_counts(self._short_hits, price, order.executed.size)
        elif order.status in [bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected, bt.Order.Expired]:
            self._tracked_orders.pop(order.ref, None)
            self.log(f"Order {side.upper()} @{price:.4f} {order.getstatusname()}")
        else:
            self._order_count += 1

    def notify_trade(self, trade: bt.Trade) -> None:  # type: ignore[override]
        if trade.isclosed:
            self.log(
                "Closed trade PnL: gross={gross:.2f}, net={net:.2f}".format(
                    gross=trade.pnl,
                    net=trade.pnlcomm,
                )
            )
