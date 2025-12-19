"""
Market data source implementations.
"""

from __future__ import annotations

from .base import MarketDataSource

# Import implementations
try:
    from .bitget_sdk import BitgetSDKDataSource
    __all__ = ["MarketDataSource", "BitgetSDKDataSource"]
except ImportError:
    __all__ = ["MarketDataSource"]

