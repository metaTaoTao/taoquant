"""
Live Trading Logger.

This module provides logging functionality for live trading.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class LiveLogger:
    """Live trading logger."""

    def __init__(self, log_dir: str = "logs/bitget_live", name: str = "bitget_live"):
        """
        Initialize live logger.

        Parameters
        ----------
        log_dir : str
            Log directory path
        name : str
            Logger name
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers.clear()

        # File handler
        log_file = self.log_dir / f"live_{datetime.now():%Y%m%d_%H%M%S}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        self.logger.info("=" * 80)
        self.logger.info("Live Trading Logger Initialized")
        self.logger.info(f"Log file: {log_file}")
        self.logger.info("=" * 80)

    def log_signal(
        self,
        signal_type: str,
        price: float,
        quantity: float,
        level: Optional[int] = None,
        reason: Optional[str] = None,
    ):
        """
        Log trading signal.

        Parameters
        ----------
        signal_type : str
            Signal type (buy/sell)
        price : float
            Order price
        quantity : float
            Order quantity
        level : int, optional
            Grid level
        reason : str, optional
            Signal reason
        """
        msg = f"[SIGNAL] {signal_type.upper()} | Price: {price:.2f} | Qty: {quantity:.6f}"
        if level is not None:
            msg += f" | Level: {level}"
        if reason:
            msg += f" | Reason: {reason}"
        self.logger.info(msg)

    def log_order(
        self,
        order_id: str,
        status: str,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        filled_quantity: Optional[float] = None,
    ):
        """
        Log order status.

        Parameters
        ----------
        order_id : str
            Order ID
        status : str
            Order status
        price : float, optional
            Order price
        quantity : float, optional
            Order quantity
        filled_quantity : float, optional
            Filled quantity
        """
        msg = f"[ORDER] {order_id} | Status: {status}"
        if price is not None:
            msg += f" | Price: {price:.2f}"
        if quantity is not None:
            msg += f" | Qty: {quantity:.6f}"
        if filled_quantity is not None:
            msg += f" | Filled: {filled_quantity:.6f}"
        self.logger.info(msg)

    def log_portfolio(
        self,
        equity: float,
        cash: Optional[float] = None,
        holdings: Optional[float] = None,
        unrealized_pnl: Optional[float] = None,
    ):
        """
        Log portfolio status.

        Parameters
        ----------
        equity : float
            Total equity
        cash : float, optional
            Available cash
        holdings : float, optional
            Holdings quantity
        unrealized_pnl : float, optional
            Unrealized PnL
        """
        msg = f"[PORTFOLIO] Equity: {equity:.2f}"
        if cash is not None:
            msg += f" | Cash: {cash:.2f}"
        if holdings is not None:
            msg += f" | Holdings: {holdings:.6f}"
        if unrealized_pnl is not None:
            pnl_sign = "+" if unrealized_pnl >= 0 else ""
            msg += f" | Unrealized PnL: {pnl_sign}{unrealized_pnl:.2f}"
        self.logger.info(msg)

    def log_info(self, message: str):
        """Log info message."""
        self.logger.info(message)

    def log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)

    def log_error(self, message: str, exc_info: bool = False):
        """
        Log error message.

        Parameters
        ----------
        message : str
            Error message
        exc_info : bool
            Include exception info
        """
        self.logger.error(message, exc_info=exc_info)

    def log_exception(self, message: str):
        """Log exception with traceback."""
        self.logger.exception(message)
