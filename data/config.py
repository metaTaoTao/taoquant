"""
Data layer configuration.

Simple configuration for data caching and sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class CacheConfig:
    """Configuration for data caching."""

    enabled: bool = True
    cache_dir: Path = Path("data/cache")
    expire_minutes: Optional[int] = None  # None = never expire


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""

    base_url: str


@dataclass
class DataConfig:
    """Configuration for data management."""

    cache: CacheConfig = field(default_factory=CacheConfig)
    data_sources: Dict[str, DataSourceConfig] = field(default_factory=lambda: {
        "okx": DataSourceConfig(base_url="https://www.okx.com"),
        "binance": DataSourceConfig(base_url="https://api.binance.com"),
    })


# Default configuration instance
default_config = DataConfig()
