from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class DataSourceConfig:
    """Configuration for an individual data source."""

    name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    extra_params: Dict[str, str] = field(default_factory=dict)


@dataclass
class CacheConfig:
    """Configuration for parquet cache behavior."""

    enabled: bool = True
    cache_dir: Path = Path("data/cache")
    expire_minutes: Optional[int] = None


@dataclass
class BacktestConfig:
    """Configuration for backtesting defaults."""

    initial_capital: float = 200000.0
    commission: float = 0.004
    slippage: float = 0.0005


@dataclass
class ProjectConfig:
    """Top-level configuration container."""

    data_sources: Dict[str, DataSourceConfig] = field(default_factory=dict)
    cache: CacheConfig = CacheConfig()
    backtest: BacktestConfig = BacktestConfig()

    def ensure_directories(self) -> None:
        """Ensure that required directories exist."""
        if self.cache.enabled:
            self.cache.cache_dir.mkdir(parents=True, exist_ok=True)
        Path("data/raw").mkdir(parents=True, exist_ok=True)


default_config = ProjectConfig(
    data_sources={
        "okx": DataSourceConfig(
            name="okx",
            base_url="https://www.okx.com",
        ),
        "binance": DataSourceConfig(
            name="binance",
            base_url="https://api.binance.com",
        ),
        "csv": DataSourceConfig(name="csv"),
    }
)

default_config.ensure_directories()


