"""
Bitget Trading Execution Engine.

This module provides order execution functionality for Bitget exchange via CCXT.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any
import time


class BitgetExecutionEngine:
    """Bitget trading execution engine (CCXT)."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        subaccount_uid: Optional[str] = None,
        debug: bool = False,
        market_type: str = "spot",
    ):
        """
        Initialize Bitget execution engine.

        Parameters
        ----------
        api_key : str
            Bitget API key
        api_secret : str
            Bitget API secret
        passphrase : str
            Bitget API passphrase
        subaccount_uid : str, optional
            Subaccount UID if trading on subaccount
        debug : bool
            Enable debug logging
        """
        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ccxt package is required for Bitget execution. Install via pip install ccxt."
            ) from exc

        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.subaccount_uid = subaccount_uid
        self.debug = debug
        self.market_type = str(market_type or "spot").lower()

        # Initialize CCXT exchange
        self.exchange = ccxt.bitget(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,  # Bitget passphrase in CCXT
                "enableRateLimit": True,
                "options": {"defaultType": self.market_type},
            }
        )
        try:
            self.exchange.load_markets()
        except Exception:
            # Non-fatal: some environments may fail to load markets intermittently
            pass

        # Track pending orders
        self.pending_orders: Dict[str, Dict[str, Any]] = {}

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "limit",
        client_order_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order (limit/market) with optional client_order_id for idempotency.

        Notes
        -----
        - For Bitget (via CCXT), client order id is usually passed as params["clientOid"].
        - For market orders, price is ignored.
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            ccxt_side = "buy" if side.lower() == "buy" else "sell"
            ccxt_type = str(order_type or "limit").lower()

            extra: Dict[str, Any] = {}
            if params:
                extra.update(params)
            if client_order_id:
                extra.setdefault("clientOid", str(client_order_id))

            # Get market precision info
            market = self.exchange.market(ccxt_symbol)
            
            # Round quantity to exchange precision (typically 0.0001 for BTC)
            # Use explicit rounding instead of truncation for better accuracy
            amount_precision = market.get("precision", {}).get("amount", 4)
            if isinstance(amount_precision, int):
                # Precision is number of decimal places
                amount = round(float(quantity), amount_precision)
            else:
                # Precision might be step size (e.g., 0.0001)
                step = float(amount_precision) if amount_precision else 0.0001
                amount = round(float(quantity) / step) * step
                amount = round(amount, 8)  # Clean up floating point errors
            
            # Check if amount meets minimum requirements
            min_amount = market.get("limits", {}).get("amount", {}).get("min", 0)
            if self.debug:
                print(f"[Bitget CCXT Engine] quantity rounded: {quantity} -> {amount} (precision={amount_precision}, min={min_amount})")
            if min_amount and amount < min_amount:
                import sys
                print(f"[Bitget place_order REJECTED] amount={amount} < min_amount={min_amount} for {ccxt_symbol}", file=sys.stderr)
                return None

            if ccxt_type == "market":
                if self.debug:
                    print(
                        f"[Bitget CCXT Engine] create_order(symbol={ccxt_symbol}, type=market, side={ccxt_side}, amount={amount}, clientOid={client_order_id})"
                    )
                order = self.exchange.create_order(ccxt_symbol, "market", ccxt_side, amount, None, extra or None)
            else:
                if price is None:
                    raise ValueError("price is required for limit orders")
                px = float(self.exchange.price_to_precision(ccxt_symbol, float(price)))
                # Always log order placement attempt for debugging (swap orders need specific params)
                import sys
                print(
                    f"[Bitget CCXT Engine] create_order(symbol={ccxt_symbol}, type=limit, side={ccxt_side}, "
                    f"amount={amount}, price={px}, params={extra})",
                    file=sys.stderr
                )
                order = self.exchange.create_order(ccxt_symbol, "limit", ccxt_side, amount, px, extra or None)

            order_id = str(order.get("id", "")) if isinstance(order, dict) else ""
            if not order_id:
                return None

            info = {
                "order_id": order_id,
                "client_order_id": (order.get("clientOrderId") if isinstance(order, dict) else None) or client_order_id,
                "symbol": symbol,
                "side": side.lower(),
                "price": float(price) if price is not None else None,
                "quantity": float(quantity),
                "status": str(order.get("status", "open")) if isinstance(order, dict) else "open",
                "timestamp": datetime.now(),
            }
            self.pending_orders[order_id] = info
            return info
        except Exception as e:
            # Always log order errors to stderr (critical for debugging live trading issues)
            # This ensures it shows up in journalctl and console output
            import sys
            error_msg = (
                f"[Bitget place_order FAILED] symbol={symbol} side={side} qty={quantity} price={price} "
                f"client_oid={client_order_id} error={type(e).__name__}: {e}"
            )
            print(error_msg, file=sys.stderr)
            if self.debug:
                import traceback
                traceback.print_exc()
            return None

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        order_type: str = "limit",
    ) -> Optional[Dict[str, Any]]:
        """
        Place a limit order.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        side : str
            "buy" or "sell"
        price : float
            Order price
        quantity : float
            Order quantity
        order_type : str
            Order type (default: "limit")

        Returns
        -------
        dict or None
            Order response with order_id, status, etc.
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel an order.

        Parameters
        ----------
        symbol : str
            Trading symbol
        order_id : str
            Order ID to cancel

        Returns
        -------
        bool
            True if cancellation successful
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            if self.debug:
                print(f"[Bitget CCXT Engine] cancel_order(order_id={order_id}, symbol={ccxt_symbol})")
            self.exchange.cancel_order(order_id, ccxt_symbol)
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
            return True

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error cancelling order: {e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get open orders.

        Parameters
        ----------
        symbol : str, optional
            Filter by symbol

        Returns
        -------
        list
            List of open orders
        """
        try:
            orders = []
            if symbol:
                ccxt_symbol = self._convert_symbol(symbol)
                raw = self.exchange.fetch_open_orders(ccxt_symbol)
            else:
                raw = self.exchange.fetch_open_orders()

            for o in raw:
                orders.append(
                    {
                        "order_id": str(o.get("id", "")),
                        "client_order_id": str(o.get("clientOrderId", "") or o.get("clientOid", "") or ""),
                        "symbol": str(o.get("symbol", "")),
                        "side": str(o.get("side", "")),
                        "price": float(o.get("price") or 0.0),
                        "quantity": float(o.get("amount") or 0.0),
                        "filled_quantity": float(o.get("filled") or 0.0),
                        "remaining_quantity": float(o.get("remaining") or 0.0),
                        "average_price": float(o.get("average") or 0.0),
                        "status": str(o.get("status", "open")),
                    }
                )
            return orders

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error getting open orders: {e}")
            return []

    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status.

        Parameters
        ----------
        symbol : str
            Trading symbol
        order_id : str
            Order ID

        Returns
        -------
        dict or None
            Order status information
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            o = self.exchange.fetch_order(order_id, ccxt_symbol)
            return {
                "order_id": str(o.get("id", "")),
                "symbol": str(o.get("symbol", "")),
                "side": str(o.get("side", "")),
                "price": float(o.get("price") or 0.0),
                "average_price": float(o.get("average") or 0.0),
                "cost": float(o.get("cost") or 0.0),
                "quantity": float(o.get("amount") or 0.0),
                "filled_quantity": float(o.get("filled") or 0.0),
                "remaining_quantity": float(o.get("remaining") or 0.0),
                "status": str(o.get("status", "unknown")),
                "client_order_id": str(o.get("clientOrderId", "") or o.get("clientOid", "") or ""),
            }

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error getting order status: {e}")
            return None

    def cancel_all_orders(self, symbol: str, client_oid_prefix: Optional[str] = None) -> int:
        """
        Cancel all open orders for a symbol.

        If client_oid_prefix is provided, only cancel orders whose client_order_id starts with the prefix.
        Returns number of cancelled orders (best-effort).
        """
        cancelled = 0
        open_orders = self.get_open_orders(symbol)
        for o in open_orders:
            coid = str(o.get("client_order_id") or "")
            if client_oid_prefix and not coid.startswith(client_oid_prefix):
                continue
            oid = str(o.get("order_id") or "")
            if not oid:
                continue
            if self.cancel_order(symbol, oid):
                cancelled += 1
        return cancelled

    def get_my_trades(
        self,
        symbol: str,
        since_ms: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Fetch user trades (fills) via CCXT.

        This is used for downtime replay / accounting. Best-effort.
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            raw = self.exchange.fetch_my_trades(ccxt_symbol, since=since_ms, limit=int(limit))
            out: List[Dict[str, Any]] = []
            for t in raw or []:
                fee = t.get("fee") or {}
                out.append(
                    {
                        "trade_id": str(t.get("id") or ""),
                        "order_id": str(t.get("order") or ""),
                        "client_order_id": str(
                            (t.get("clientOrderId") or "")
                            or (t.get("clientOid") or "")
                            or (t.get("info", {}) or {}).get("clientOid")
                            or ""
                        ),
                        "symbol": str(t.get("symbol") or ""),
                        "side": str(t.get("side") or ""),
                        "price": float(t.get("price") or 0.0),
                        "qty": float(t.get("amount") or 0.0),
                        "cost": float(t.get("cost") or 0.0),
                        "fee": float(fee.get("cost") or 0.0) if isinstance(fee, dict) else 0.0,
                        "fee_currency": str(fee.get("currency") or "") if isinstance(fee, dict) else "",
                        "timestamp_ms": int(t.get("timestamp") or 0),
                        "raw": t,
                    }
                )
            return out
        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error fetching my trades: {e}")
            return []

    def get_account_balance(self) -> Dict[str, Any]:
        """
        Get account balance.

        Returns
        -------
        dict
            Account balance information with keys:
            - total_equity: Total account equity
            - available_balance: Available balance
            - frozen_balance: Frozen balance
            - assets: List of asset balances
        """
        try:
            # CCXT unified balance; some exchanges honor type/defaultType.
            # We still pass explicit type to be safe.
            try:
                bal = self.exchange.fetch_balance({"type": self.market_type})
            except Exception:
                bal = self.exchange.fetch_balance()

            assets = []
            total_equity = 0.0
            available_balance = 0.0
            frozen_balance = 0.0

            # Prefer valuing equity in USDT if possible (USDT cash + major holdings * last price).
            free = bal.get("free", {}) or {}
            used = bal.get("used", {}) or {}
            total = bal.get("total", {}) or {}

            # Build assets list
            for ccy, tot in total.items():
                try:
                    tot_f = float(tot or 0.0)
                except Exception:
                    continue
                if tot_f <= 0:
                    continue
                assets.append(
                    {
                        "currency": str(ccy),
                        "available": float(free.get(ccy) or 0.0),
                        "frozen": float(used.get(ccy) or 0.0),
                        "total": tot_f,
                    }
                )

            usdt_free = float(free.get("USDT") or 0.0)
            usdt_used = float(used.get("USDT") or 0.0)
            available_balance = usdt_free
            frozen_balance = usdt_used

            total_equity = usdt_free + usdt_used
            # Note: add other holdings valuation lazily in live runner when symbol is known
            return {
                "total_equity": total_equity,
                "available_balance": available_balance,
                "frozen_balance": frozen_balance,
                "assets": assets,
            }

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error getting account balance: {e}")
            return {
                "total_equity": 0.0,
                "available_balance": 0.0,
                "frozen_balance": 0.0,
                "assets": [],
            }

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Parameters
        ----------
        symbol : str, optional
            Filter by symbol

        Returns
        -------
        list
            List of positions
        """
        try:
            positions: List[Dict[str, Any]] = []

            if self.market_type == "spot":
                balance = self.get_account_balance()
                base_currency = None
                if symbol:
                    base_currency = self._base_currency(symbol)
                for asset in balance.get("assets", []):
                    currency = asset.get("currency", "")
                    total = asset.get("total", 0)
                    if total > 0:
                        if base_currency is None or currency == base_currency:
                            positions.append(
                                {
                                    "symbol": symbol or f"{currency}USDT",
                                    "currency": currency,
                                    "quantity": total,
                                    "available": asset.get("available", 0),
                                    "frozen": asset.get("frozen", 0),
                                    "unrealized_pnl": 0.0,
                                    "side": "spot",
                                    "entry_price": None,
                                }
                            )
                return positions

            # swap / futures: use fetch_positions if supported
            try:
                if symbol:
                    ccxt_symbol = self._convert_symbol(symbol)
                    raw = self.exchange.fetch_positions([ccxt_symbol], {"type": self.market_type})
                else:
                    raw = self.exchange.fetch_positions(None, {"type": self.market_type})
            except Exception:
                raw = []

            for p in raw or []:
                qty = float(p.get("contracts") or p.get("contractSize") or p.get("positionAmt") or p.get("size") or 0.0)
                if qty == 0.0:
                    continue
                side = str(p.get("side") or "").lower()
                entry = p.get("entryPrice") or p.get("entry_price") or p.get("avgCostPrice") or p.get("average")
                upnl = p.get("unrealizedPnl") or p.get("unrealisedPnl") or p.get("info", {}).get("unrealizedPnl")
                positions.append(
                    {
                        "symbol": str(p.get("symbol") or symbol or ""),
                        "currency": self._base_currency(symbol) if symbol else "",
                        "quantity": abs(qty),
                        "side": side or ("long" if qty > 0 else "short"),
                        "entry_price": float(entry) if entry is not None else None,
                        "unrealized_pnl": float(upnl) if upnl is not None else 0.0,
                    }
                )
            return positions

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error getting positions: {e}")
            return []

    def _convert_symbol(self, symbol: str) -> str:
        """
        Convert symbol format to CCXT format.

        Parameters
        ----------
        symbol : str
            Symbol like "BTCUSDT"

        Returns
        -------
        str
            CCXT symbol format
        """
        upper = symbol.upper()
        if "/" in upper:
            norm = upper.replace("-", "/")
        elif upper.endswith("USDT") and len(upper) > 4:
            norm = f"{upper[:-4]}/USDT"
        else:
            norm = upper

        # Bitget USDT perpetual in CCXT is typically formatted as "BTC/USDT:USDT"
        if self.market_type in ("swap", "future", "futures"):
            if ":" not in norm and norm.endswith("/USDT"):
                return f"{norm}:USDT"
        return norm

    def set_leverage(self, symbol: str, leverage: float) -> bool:
        """
        Set leverage for swap/futures (best-effort).
        """
        if self.market_type not in ("swap", "future", "futures"):
            return False
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            lev = int(max(1, float(leverage)))
            if hasattr(self.exchange, "set_leverage"):
                self.exchange.set_leverage(lev, ccxt_symbol)
                return True
        except Exception:
            return False
        return False

    def close_position(self, symbol: str, side: str) -> Optional[Dict[str, Any]]:
        """
        Close position using Bitget's Flash Close Position API.

        This uses the dedicated close position endpoint which works reliably
        for USDT perpetual swaps in unilateral (one-way) mode.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        side : str
            Position side to close: "long" or "short"

        Returns
        -------
        dict or None
            Close position response, or None if failed

        Notes
        -----
        - This method uses Bitget's Flash Close Position API (/api/v2/mix/order/close-positions)
        - The position will be closed at market price
        - Only works for swap/futures markets, not spot
        - Rate limit: 1 request/second/UID

        References
        ----------
        https://www.bitget.com/api-doc/contract/trade/Flash-Close-Position
        """
        if self.market_type not in ("swap", "future", "futures"):
            if self.debug:
                print(f"[Bitget] close_position only works for swap/futures, not {self.market_type}")
            return None

        try:
            # Convert symbol to Bitget format (e.g., "BTCUSDT" without slashes)
            base_symbol = symbol.upper().replace("/", "").replace(":USDT", "")

            # Determine product type
            product_type = "USDT-FUTURES"  # For USDT perpetual swaps

            # Validate side
            hold_side = str(side).lower()
            if hold_side not in ("long", "short"):
                if self.debug:
                    print(f"[Bitget] Invalid side '{side}', must be 'long' or 'short'")
                return None

            # Always log Flash Close API calls (critical operation)
            print(f"[Bitget CCXT Engine] close_position(symbol={base_symbol}, productType={product_type}, holdSide={hold_side})")

            # Call Bitget's Flash Close Position API via CCXT private endpoint
            # API: POST /api/v2/mix/order/close-positions
            response = self.exchange.private_mix_post_v2_mix_order_close_positions({
                'symbol': base_symbol,
                'productType': product_type,
                'holdSide': hold_side,
            })

            # Always log response (critical operation)
            print(f"[Bitget] close_position response: {response}")

            # Parse response
            # Response format: {"code":"00000","data":{"successList":[{"orderId":"...","clientOid":"...","symbol":"..."}],"failureList":[]},"msg":"success"}
            if response and response.get('code') == '00000':
                data = response.get('data', {})
                success_list = data.get('successList', [])
                failure_list = data.get('failureList', [])

                # Check if position was successfully closed
                if success_list:
                    order_info = success_list[0]
                    return {
                        'success': True,
                        'order_id': order_info.get('orderId'),
                        'client_oid': order_info.get('clientOid'),
                        'symbol': order_info.get('symbol', symbol),
                        'side': hold_side,
                        'message': response.get('msg', 'Position closed successfully'),
                    }
                elif failure_list:
                    # Position close failed
                    error_info = failure_list[0]
                    error_msg = error_info.get('errorMsg', 'Unknown error')
                    error_code = error_info.get('errorCode', 'Unknown')
                    print(f"[Bitget] close_position failed: {error_code} - {error_msg}")
                    return None
                else:
                    # No success or failure - unexpected response
                    print(f"[Bitget] close_position returned empty successList and failureList")
                    return None
            else:
                # Always log failures (critical operation)
                print(f"[Bitget] close_position failed: {response}")
                return None

        except Exception as e:
            # Always log exceptions (critical operation)
            print(f"[Bitget] Error closing position: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _base_currency(symbol: str) -> str:
        upper = symbol.upper()
        if "/" in upper:
            return upper.split("/")[0]
        if upper.endswith("USDT") and len(upper) > 4:
            return upper[:-4]
        return upper
