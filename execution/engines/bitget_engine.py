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

        # Initialize CCXT exchange
        self.exchange = ccxt.bitget(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,  # Bitget passphrase in CCXT
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )

        # Track pending orders
        self.pending_orders: Dict[str, Dict[str, Any]] = {}

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
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            ccxt_side = "buy" if side.lower() == "buy" else "sell"
            ccxt_type = "limit" if order_type == "limit" else order_type

            # CCXT: amount/price precision
            amount = float(self.exchange.amount_to_precision(ccxt_symbol, quantity))
            px = float(self.exchange.price_to_precision(ccxt_symbol, price))

            if self.debug:
                print(f"[Bitget CCXT Engine] create_order(symbol={ccxt_symbol}, side={ccxt_side}, amount={amount}, price={px})")

            order = self.exchange.create_order(ccxt_symbol, ccxt_type, ccxt_side, amount, px)
            order_id = str(order.get("id", ""))
            if not order_id:
                return None

            order_info = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity,
                "status": str(order.get("status", "open")),
                "timestamp": datetime.now(),
            }
            self.pending_orders[order_id] = order_info
            return order_info

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error placing order: {e}")
                import traceback
                traceback.print_exc()
            return None

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
                        "symbol": str(o.get("symbol", "")),
                        "side": str(o.get("side", "")),
                        "price": float(o.get("price") or 0.0),
                        "quantity": float(o.get("amount") or 0.0),
                        "filled_quantity": float(o.get("filled") or 0.0),
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
                "quantity": float(o.get("amount") or 0.0),
                "filled_quantity": float(o.get("filled") or 0.0),
                "status": str(o.get("status", "unknown")),
            }

        except Exception as e:
            if self.debug:
                print(f"[Bitget CCXT Engine] Error getting order status: {e}")
            return None

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
            balance = self.get_account_balance()
            positions = []

            # Filter by symbol if provided
            base_currency = None
            if symbol:
                # Extract base currency from symbol (e.g., BTCUSDT -> BTC)
                base_currency = self._base_currency(symbol)

            for asset in balance.get("assets", []):
                currency = asset.get("currency", "")
                total = asset.get("total", 0)

                if total > 0:
                    if base_currency is None or currency == base_currency:
                        positions.append({
                            "symbol": symbol or f"{currency}USDT",
                            "currency": currency,
                            "quantity": total,
                            "available": asset.get("available", 0),
                            "frozen": asset.get("frozen", 0),
                            "unrealized_pnl": 0.0,  # Spot doesn't have unrealized PnL
                        })

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
            return upper.replace("-", "/")
        if upper.endswith("USDT") and len(upper) > 4:
            return f"{upper[:-4]}/USDT"
        return upper

    @staticmethod
    def _base_currency(symbol: str) -> str:
        upper = symbol.upper()
        if "/" in upper:
            return upper.split("/")[0]
        if upper.endswith("USDT") and len(upper) > 4:
            return upper[:-4]
        return upper
