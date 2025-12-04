"""
Utility functions for path management.
Ensures consistent paths regardless of where the script is run from.
"""

from pathlib import Path


def get_project_root() -> Path:
    """
    Get the project root directory.
    
    Assumes the project root contains:
    - run/ directory
    - data/ directory
    - strategies/ directory
    
    Returns
    -------
    Path
        Absolute path to project root
    """
    # Start from this file's location
    current = Path(__file__).resolve()
    
    # Walk up until we find the project root (has run/, data/, strategies/)
    for parent in [current] + list(current.parents):
        if all((parent / d).exists() for d in ['run', 'data', 'strategies']):
            return parent
    
    # Fallback: assume we're in utils/ subdirectory
    return current.parent


def get_results_dir() -> Path:
    """
    Get the results directory path.
    
    Returns
    -------
    Path
        Absolute path to run/results directory
    """
    project_root = get_project_root()
    results_dir = project_root / 'run' / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir

