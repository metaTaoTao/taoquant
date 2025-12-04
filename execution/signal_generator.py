"""
Signal generation framework for TaoQuant.

This module provides utilities for generating and validating trading signals.
Signals are the output of strategy logic and input to the backtest engine.

Design Principles:
- Signals are pure data (no execution logic)
- Signals are validated before execution
- Signals are DataFrame-based (aligned with OHLCV data)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class SignalMetadata:
    """
    Metadata for a signal generation event.

    Attributes
    ----------
    strategy_name : str
        Name of the strategy that generated the signal
    signal_type : str
        Type of signal (entry, exit, sl_update, tp_update)
    reason : str
        Human-readable reason for the signal
    confidence : Optional[float]
        Signal confidence score (0-1)
    """

    strategy_name: str
    signal_type: str
    reason: str
    confidence: Optional[float] = None


def create_signal_dataframe(
    index: pd.DatetimeIndex,
    entry: Optional[pd.Series] = None,
    exit: Optional[pd.Series] = None,
    direction: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Create a standardized signal DataFrame.

    This is a convenience function to create properly formatted signals
    that can be passed to BacktestEngine.run().

    Parameters
    ----------
    index : pd.DatetimeIndex
        Time index (must match OHLCV data index)
    entry : Optional[pd.Series]
        Entry signals (bool Series, True = enter position)
    exit : Optional[pd.Series]
        Exit signals (bool Series, True = exit position)
    direction : Optional[pd.Series]
        Position direction (str Series, 'long' or 'short')

    Returns
    -------
    pd.DataFrame
        Signal DataFrame with columns: [entry, exit, direction]

    Examples
    --------
    >>> index = pd.date_range('2025-01-01', periods=5, freq='1h')
    >>> signals = create_signal_dataframe(
    ...     index=index,
    ...     entry=pd.Series([False, True, False, False, False], index=index),
    ...     exit=pd.Series([False, False, False, True, False], index=index),
    ...     direction=pd.Series(['long'] * 5, index=index)
    ... )
    """
    if entry is None:
        entry = pd.Series(False, index=index)

    if exit is None:
        exit = pd.Series(False, index=index)

    if direction is None:
        direction = pd.Series('long', index=index)

    # Validate indices match
    if not entry.index.equals(index):
        raise ValueError("Entry index must match provided index")

    if not exit.index.equals(index):
        raise ValueError("Exit index must match provided index")

    if not direction.index.equals(index):
        raise ValueError("Direction index must match provided index")

    return pd.DataFrame({
        'entry': entry.astype(bool),
        'exit': exit.astype(bool),
        'direction': direction.astype(str),
    }, index=index)


def validate_signals(signals: pd.DataFrame) -> None:
    """
    Validate signal DataFrame format.

    Parameters
    ----------
    signals : pd.DataFrame
        Signal DataFrame to validate

    Raises
    ------
    ValueError
        If signals are invalid
    """
    # Check required columns
    required_cols = ['entry', 'exit', 'direction']
    missing_cols = [col for col in required_cols if col not in signals.columns]
    if missing_cols:
        raise ValueError(f"Signals missing required columns: {missing_cols}")

    # Check index is DatetimeIndex
    if not isinstance(signals.index, pd.DatetimeIndex):
        raise ValueError("Signals index must be DatetimeIndex")

    # Check data types
    if signals['entry'].dtype != bool:
        raise ValueError("Entry signals must be boolean")

    if signals['exit'].dtype != bool:
        raise ValueError("Exit signals must be boolean")

    # Check direction values
    valid_directions = {'long', 'short'}
    invalid_directions = set(signals['direction'].unique()) - valid_directions
    if invalid_directions:
        raise ValueError(
            f"Invalid direction values: {invalid_directions}. "
            f"Must be 'long' or 'short'"
        )

    # Check for simultaneous entry and exit
    simultaneous = signals['entry'] & signals['exit']
    if simultaneous.any():
        raise ValueError(
            f"Found {simultaneous.sum()} bars with simultaneous entry and exit signals. "
            "This is not allowed."
        )


def merge_signals(
    *signal_dfs: pd.DataFrame,
    method: str = 'any'
) -> pd.DataFrame:
    """
    Merge multiple signal DataFrames.

    Useful for combining signals from multiple strategies or conditions.

    Parameters
    ----------
    *signal_dfs : pd.DataFrame
        Signal DataFrames to merge
    method : str
        Merge method:
        - 'any': Signal is True if ANY DataFrame has True
        - 'all': Signal is True only if ALL DataFrames have True
        - 'majority': Signal is True if > 50% of DataFrames have True

    Returns
    -------
    pd.DataFrame
        Merged signal DataFrame

    Examples
    --------
    >>> signals1 = create_signal_dataframe(...)
    >>> signals2 = create_signal_dataframe(...)
    >>> merged = merge_signals(signals1, signals2, method='any')
    """
    if len(signal_dfs) == 0:
        raise ValueError("Must provide at least one signal DataFrame")

    if len(signal_dfs) == 1:
        return signal_dfs[0].copy()

    # Validate all signals
    for df in signal_dfs:
        validate_signals(df)

    # Check all have same index
    first_index = signal_dfs[0].index
    for df in signal_dfs[1:]:
        if not df.index.equals(first_index):
            raise ValueError("All signal DataFrames must have the same index")

    # Merge entry signals
    if method == 'any':
        entry_merged = pd.concat([df['entry'] for df in signal_dfs], axis=1).any(axis=1)
        exit_merged = pd.concat([df['exit'] for df in signal_dfs], axis=1).any(axis=1)
    elif method == 'all':
        entry_merged = pd.concat([df['entry'] for df in signal_dfs], axis=1).all(axis=1)
        exit_merged = pd.concat([df['exit'] for df in signal_dfs], axis=1).all(axis=1)
    elif method == 'majority':
        entry_sum = pd.concat([df['entry'] for df in signal_dfs], axis=1).sum(axis=1)
        entry_merged = entry_sum > (len(signal_dfs) / 2)
        exit_sum = pd.concat([df['exit'] for df in signal_dfs], axis=1).sum(axis=1)
        exit_merged = exit_sum > (len(signal_dfs) / 2)
    else:
        raise ValueError(f"Unknown merge method: {method}")

    # For direction, use first non-NaN direction
    direction_merged = signal_dfs[0]['direction'].copy()

    return pd.DataFrame({
        'entry': entry_merged,
        'exit': exit_merged,
        'direction': direction_merged,
    }, index=first_index)


def apply_signal_filters(
    signals: pd.DataFrame,
    cooldown_bars: Optional[int] = None,
    max_signals: Optional[int] = None,
) -> pd.DataFrame:
    """
    Apply filters to signals.

    Parameters
    ----------
    signals : pd.DataFrame
        Input signals
    cooldown_bars : Optional[int]
        Minimum bars between signals (None = no cooldown)
    max_signals : Optional[int]
        Maximum number of signals to allow (None = unlimited)

    Returns
    -------
    pd.DataFrame
        Filtered signals

    Examples
    --------
    >>> filtered = apply_signal_filters(
    ...     signals,
    ...     cooldown_bars=10,  # At least 10 bars between signals
    ...     max_signals=5       # Maximum 5 signals total
    ... )
    """
    validate_signals(signals)

    filtered = signals.copy()

    # Apply cooldown filter
    if cooldown_bars is not None and cooldown_bars > 0:
        filtered = _apply_cooldown(filtered, cooldown_bars)

    # Apply max signals filter
    if max_signals is not None and max_signals > 0:
        filtered = _apply_max_signals(filtered, max_signals)

    return filtered


def _apply_cooldown(signals: pd.DataFrame, cooldown_bars: int) -> pd.DataFrame:
    """
    Apply cooldown filter to signals.

    After each entry signal, suppress subsequent entry signals
    for cooldown_bars.

    Parameters
    ----------
    signals : pd.DataFrame
        Input signals
    cooldown_bars : int
        Cooldown period in bars

    Returns
    -------
    pd.DataFrame
        Filtered signals
    """
    filtered = signals.copy()

    # Track last signal bar
    last_signal_idx = -cooldown_bars - 1

    # Iterate through entry signals
    for i in range(len(filtered)):
        if filtered['entry'].iloc[i]:
            # Check if within cooldown period
            if i - last_signal_idx <= cooldown_bars:
                # Suppress this signal
                filtered['entry'].iloc[i] = False
            else:
                # Allow this signal, update last signal index
                last_signal_idx = i

    return filtered


def _apply_max_signals(signals: pd.DataFrame, max_signals: int) -> pd.DataFrame:
    """
    Limit total number of signals.

    Parameters
    ----------
    signals : pd.DataFrame
        Input signals
    max_signals : int
        Maximum number of signals

    Returns
    -------
    pd.DataFrame
        Filtered signals
    """
    filtered = signals.copy()

    # Find all entry signal indices
    entry_indices = filtered[filtered['entry']].index

    # If more than max_signals, keep only first max_signals
    if len(entry_indices) > max_signals:
        # Suppress signals beyond max_signals
        excess_indices = entry_indices[max_signals:]
        filtered.loc[excess_indices, 'entry'] = False

    return filtered


def get_signal_summary(signals: pd.DataFrame) -> dict:
    """
    Get summary statistics for signals.

    Parameters
    ----------
    signals : pd.DataFrame
        Signal DataFrame

    Returns
    -------
    dict
        Summary statistics

    Examples
    --------
    >>> summary = get_signal_summary(signals)
    >>> print(f"Total entry signals: {summary['num_entries']}")
    >>> print(f"Long signals: {summary['num_long']}")
    >>> print(f"Short signals: {summary['num_short']}")
    """
    validate_signals(signals)

    num_entries = signals['entry'].sum()
    num_exits = signals['exit'].sum()

    # Count by direction
    entry_signals = signals[signals['entry']]
    num_long = (entry_signals['direction'] == 'long').sum()
    num_short = (entry_signals['direction'] == 'short').sum()

    # Calculate signal frequency
    if len(signals) > 0:
        entry_frequency = num_entries / len(signals)
    else:
        entry_frequency = 0

    return {
        'num_entries': int(num_entries),
        'num_exits': int(num_exits),
        'num_long': int(num_long),
        'num_short': int(num_short),
        'entry_frequency': float(entry_frequency),
        'total_bars': len(signals),
    }
