from __future__ import annotations

from typing import Dict

TIMEFRAME_TO_MINUTES: Dict[str, int] = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "3d": 4320,
    "1w": 10080,
    "1mth": 43200,
    "1month": 43200,
}

ALIASES: Dict[str, str] = {
    "1M": "1mth",
    "3D": "3d",
}

_NORMALIZED_MAP: Dict[str, int] = {}
for key, value in TIMEFRAME_TO_MINUTES.items():
    _NORMALIZED_MAP[key.lower()] = value
for alias, target in ALIASES.items():
    _NORMALIZED_MAP[alias.lower()] = TIMEFRAME_TO_MINUTES[target]


def timeframe_to_minutes(timeframe: str) -> int:
    """Convert timeframe string to minutes."""
    key = timeframe.lower()
    if key not in _NORMALIZED_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _NORMALIZED_MAP[key]

