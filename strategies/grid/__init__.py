"""
网格策略模块

包含：
- GridStrategy: 基础网格策略实现
- GridBacktester: 基础网格策略回测引擎
- GridOptimizer: 参数优化器（最大化 Sharpe Ratio）
- SmartGridStrategy: 智能动态网格策略（支持做空、多笔交易、衰减机制）
- SmartGridBacktester: 智能网格回测引擎
"""

from .grid_backtester import GridBacktester
from .grid_optimizer import GridOptimizer, OptimizationBounds, OptimizationResult
from .grid_strategy import GridStrategy, GridStrategyConfig
from .smart_grid_strategy import SmartGridStrategy, SmartGridConfig
from .smart_grid_backtester import SmartGridBacktester

__all__ = [
    'GridStrategy',
    'GridStrategyConfig',
    'GridBacktester',
    'GridOptimizer',
    'OptimizationBounds',
    'OptimizationResult',
    'SmartGridStrategy',
    'SmartGridConfig',
    'SmartGridBacktester',
]

