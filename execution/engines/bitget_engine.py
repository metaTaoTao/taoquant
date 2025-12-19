"""
Bitget Trading Execution Engine.

This module provides order execution functionality for Bitget exchange.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any
import time


class BitgetExecutionEngine:
    """Bitget trading execution engine."""

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
            from bitget import Client  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "bitget-python package is required. Install via pip install bitget-python."
            ) from exc

        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.subaccount_uid = subaccount_uid
        self.debug = debug

        # Initialize client
        self.client = Client(api_key, api_secret, passphrase=passphrase)

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
            # Convert symbol format
            bitget_symbol = self._convert_symbol(symbol)
            bitget_side = "buy" if side.lower() == "buy" else "sell"

            # Prepare order parameters
            params = {
                "symbol": bitget_symbol,
                "side": bitget_side,
                "orderType": order_type,
                "price": str(price),
                "size": str(quantity),
            }

            if self.subaccount_uid:
                params["subUid"] = self.subaccount_uid

            if self.debug:
                print(f"[Bitget Engine] Placing order: {params}")

            # Place spot order
            response = self.client.spot.place_order(**params)

            if self.debug:
                print(f"[Bitget Engine] Order response: {response}")

            # Parse response
            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":  # Success
                    data = response.get("data", {})
                    order_id = data.get("orderId") or data.get("order_id")
                    if order_id:
                        order_info = {
                            "order_id": str(order_id),
                            "symbol": symbol,
                            "side": side,
                            "price": price,
                            "quantity": quantity,
                            "status": "pending",
                            "timestamp": datetime.now(),
                        }
                        self.pending_orders[str(order_id)] = order_info
                        return order_info
                else:
                    msg = response.get("msg", "Unknown error")
                    if self.debug:
                        print(f"[Bitget Engine] Order failed: {msg}")
                    return None

            return None

        except Exception as e:
            if self.debug:
                print(f"[Bitget Engine] Error placing order: {e}")
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
            bitget_symbol = self._convert_symbol(symbol)

            params = {
                "symbol": bitget_symbol,
                "orderId": order_id,
            }

            if self.subaccount_uid:
                params["subUid"] = self.subaccount_uid

            if self.debug:
                print(f"[Bitget Engine] Cancelling order: {params}")

            response = self.client.spot.cancel_order(**params)

            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    # Remove from pending orders
                    if order_id in self.pending_orders:
                        del self.pending_orders[order_id]
                    return True

            return False

        except Exception as e:
            if self.debug:
                print(f"[Bitget Engine] Error cancelling order: {e}")
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
            params = {}
            if symbol:
                params["symbol"] = self._convert_symbol(symbol)

            if self.subaccount_uid:
                params["subUid"] = self.subaccount_uid

            response = self.client.spot.open_orders(**params)

            orders = []
            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", [])
                    for item in data:
                        orders.append({
                            "order_id": str(item.get("orderId") or item.get("order_id", "")),
                            "symbol": item.get("symbol", ""),
                            "side": item.get("side", ""),
                            "price": float(item.get("price", 0)),
                            "quantity": float(item.get("size") or item.get("quantity", 0)),
                            "filled_quantity": float(item.get("filledSize") or item.get("filled_quantity", 0)),
                            "status": item.get("status", "pending"),
                        })

            return orders

        except Exception as e:
            if self.debug:
                print(f"[Bitget Engine] Error getting open orders: {e}")
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
            bitget_symbol = self._convert_symbol(symbol)

            params = {
                "symbol": bitget_symbol,
                "orderId": order_id,
            }

            if self.subaccount_uid:
                params["subUid"] = self.subaccount_uid

            response = self.client.spot.order_info(**params)

            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", {})
                    return {
                        "order_id": str(data.get("orderId") or data.get("order_id", "")),
                        "symbol": data.get("symbol", ""),
                        "side": data.get("side", ""),
                        "price": float(data.get("price", 0)),
                        "quantity": float(data.get("size") or data.get("quantity", 0)),
                        "filled_quantity": float(data.get("filledSize") or data.get("filled_quantity", 0)),
                        "status": data.get("status", "unknown"),
                    }

            return None

        except Exception as e:
            if self.debug:
                print(f"[Bitget Engine] Error getting order status: {e}")
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
            params = {}
            if self.subaccount_uid:
                params["subUid"] = self.subaccount_uid

            response = self.client.account.assets(**params)

            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", {})
                    # Parse Bitget balance format
                    # Adjust based on actual Bitget response structure
                    total_equity = 0.0
                    available_balance = 0.0
                    frozen_balance = 0.0
                    assets = []

                    if isinstance(data, list):
                        for asset in data:
                            available = float(asset.get("available", 0))
                            frozen = float(asset.get("frozen", 0))
                            total = available + frozen
                            total_equity += total
                            available_balance += available
                            frozen_balance += frozen
                            assets.append({
                                "currency": asset.get("coinName", ""),
                                "available": available,
                                "frozen": frozen,
                                "total": total,
                            })
                    elif isinstance(data, dict):
                        # If Bitget returns different format
                        available_balance = float(data.get("available", 0))
                        frozen_balance = float(data.get("frozen", 0))
                        total_equity = available_balance + frozen_balance

                    return {
                        "total_equity": total_equity,
                        "available_balance": available_balance,
                        "frozen_balance": frozen_balance,
                        "assets": assets,
                    }

            return {
                "total_equity": 0.0,
                "available_balance": 0.0,
                "frozen_balance": 0.0,
                "assets": [],
            }

        except Exception as e:
            if self.debug:
                print(f"[Bitget Engine] Error getting account balance: {e}")
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
            # For spot trading, positions are just holdings
            balance = self.get_account_balance()
            positions = []

            # Filter by symbol if provided
            base_currency = None
            if symbol:
                # Extract base currency from symbol (e.g., BTCUSDT -> BTC)
                if symbol.endswith("USDT"):
                    base_currency = symbol[:-4]

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
                print(f"[Bitget Engine] Error getting positions: {e}")
            return []

    def _convert_symbol(self, symbol: str) -> str:
        """
        Convert symbol format to Bitget format.

        Parameters
        ----------
        symbol : str
            Symbol like "BTCUSDT"

        Returns
        -------
        str
            Bitget symbol format
        """
        # Bitget spot format: BTCUSDT_SPBL
        upper = symbol.upper()
        if upper.endswith("USDT"):
            return f"{upper}_SPBL"
        return symbol
