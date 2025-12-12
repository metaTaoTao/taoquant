"""
网格策略参数优化器

使用 scipy.optimize 优化仓位管理参数，目标：最大化 Sharpe Ratio
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, minimize

from strategies.grid.grid_backtester import GridBacktester
from strategies.grid.grid_strategy import GridStrategy, GridStrategyConfig


@dataclass
class OptimizationBounds:
    """参数优化边界"""
    grid_spacing_pct: Tuple[float, float] = (0.5, 3.0)  # 0.5% - 3%
    position_fraction: Tuple[float, float] = (0.03, 0.10)  # 3% - 10%
    max_exposure_pct: Tuple[float, float] = (0.20, 0.60)  # 20% - 60%
    weight_decay_param: Tuple[float, float] = (0.05, 0.50)  # 衰减参数范围


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict[str, float]
    best_sharpe: float
    optimization_history: List[Dict]
    final_result: Optional[any] = None  # BacktestResult


class GridOptimizer:
    """
    网格策略参数优化器
    
    优化目标：最大化 Sharpe Ratio
    优化参数：
    - grid_spacing_pct: 网格间距
    - position_fraction: 单格仓位比例
    - max_exposure_pct: 最大资金暴露
    - weight_decay_param: 仓位衰减参数
    """
    
    def __init__(
        self,
        execution_data: pd.DataFrame,
        upper_bound: float,
        lower_bound: float,
        start_date: Optional[pd.Timestamp] = None,
        initial_cash: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        weight_decay_type: str = 'exponential',
        bounds: Optional[OptimizationBounds] = None
    ):
        """
        初始化优化器
        
        Parameters
        ----------
        execution_data : pd.DataFrame
            执行数据（建议使用1分钟K线，更精确）
        upper_bound : float
            网格上界
        lower_bound : float
            网格下界
        start_date : pd.Timestamp, optional
            回测开始日期
        initial_cash : float
            初始资金
        commission : float
            手续费率
        slippage : float
            滑点率
        weight_decay_type : str
            仓位衰减类型（'linear', 'exponential', 'power'）
        bounds : OptimizationBounds, optional
            参数优化边界
        """
        self.execution_data = execution_data
        self.upper_bound = upper_bound
        self.lower_bound = lower_bound
        self.start_date = start_date
        self.initial_cash = initial_cash
        self.commission = commission
        self.slippage = slippage
        self.weight_decay_type = weight_decay_type
        self.bounds = bounds or OptimizationBounds()
        
        # 优化历史记录
        self.optimization_history: List[Dict] = []
    
    def optimize(
        self,
        method: str = 'differential_evolution',
        max_iterations: int = 50,
        population_size: int = 15,
        seed: Optional[int] = None
    ) -> OptimizationResult:
        """
        优化参数以最大化 Sharpe Ratio
        
        Parameters
        ----------
        method : str
            优化方法：'differential_evolution' 或 'minimize'
        max_iterations : int
            最大迭代次数
        population_size : int
            差分进化算法的种群大小
        seed : int, optional
            随机种子
        
        Returns
        -------
        OptimizationResult
            优化结果
        """
        # 定义参数向量：[grid_spacing_pct, position_fraction, max_exposure_pct, weight_decay_param]
        bounds_list = [
            self.bounds.grid_spacing_pct,
            self.bounds.position_fraction,
            self.bounds.max_exposure_pct,
            self.bounds.weight_decay_param,
        ]
        
        # 目标函数（负 Sharpe，因为优化器是最小化）
        def objective(params: np.ndarray) -> float:
            return -self._evaluate_params(params)
        
        # 运行优化
        if method == 'differential_evolution':
            result = differential_evolution(
                objective,
                bounds=bounds_list,
                maxiter=max_iterations,
                popsize=population_size,
                seed=seed,
                callback=self._optimization_callback,
                polish=True,  # 最后用局部优化精炼
            )
        else:  # minimize
            # 初始猜测（边界中点）
            x0 = [
                (b[0] + b[1]) / 2 for b in bounds_list
            ]
            
            result = minimize(
                objective,
                x0=x0,
                bounds=bounds_list,
                method='L-BFGS-B',
                options={'maxiter': max_iterations},
                callback=self._optimization_callback,
            )
        
        # 提取最优参数
        best_params = {
            'grid_spacing_pct': result.x[0],
            'position_fraction': result.x[1],
            'max_exposure_pct': result.x[2],
            'weight_decay_param': result.x[3],
        }
        
        # 运行最终回测
        final_result = self._run_backtest(best_params)
        best_sharpe = final_result.metrics['sharpe_ratio']
        
        return OptimizationResult(
            best_params=best_params,
            best_sharpe=best_sharpe,
            optimization_history=self.optimization_history.copy(),
            final_result=final_result
        )
    
    def _evaluate_params(self, params: np.ndarray) -> float:
        """
        评估参数组合的 Sharpe Ratio
        
        Parameters
        ----------
        params : np.ndarray
            参数向量 [grid_spacing_pct, position_fraction, max_exposure_pct, weight_decay_param]
        
        Returns
        -------
        float
            Sharpe Ratio（如果回测失败返回 -inf）
        """
        try:
            # 创建策略配置
            config = GridStrategyConfig(
                name="Grid Strategy",
                description="Optimized grid strategy",
                upper_bound=self.upper_bound,
                lower_bound=self.lower_bound,
                grid_spacing_pct=params[0],
                position_fraction=params[1],
                max_exposure_pct=params[2],
                weight_decay_type=self.weight_decay_type,
                weight_decay_param=params[3],
                commission=self.commission,
                slippage=self.slippage,
            )
            
            # 运行回测
            result = self._run_backtest({
                'grid_spacing_pct': params[0],
                'position_fraction': params[1],
                'max_exposure_pct': params[2],
                'weight_decay_param': params[3],
            })
            
            sharpe = result.metrics['sharpe_ratio']
            
            # 记录到历史
            self.optimization_history.append({
                'grid_spacing_pct': params[0],
                'position_fraction': params[1],
                'max_exposure_pct': params[2],
                'weight_decay_param': params[3],
                'sharpe_ratio': sharpe,
                'total_return': result.metrics['total_return'],
                'max_drawdown': result.metrics['max_drawdown'],
            })
            
            return sharpe if not np.isnan(sharpe) else -np.inf
            
        except Exception as e:
            # 回测失败，返回负无穷
            print(f"Error evaluating params {params}: {e}")
            return -np.inf
    
    def _run_backtest(self, params: Dict[str, float]) -> any:
        """运行回测并返回结果"""
        config = GridStrategyConfig(
            name="Grid Strategy",
            description="Optimized grid strategy",
            upper_bound=self.upper_bound,
            lower_bound=self.lower_bound,
            grid_spacing_pct=params['grid_spacing_pct'],
            position_fraction=params['position_fraction'],
            max_exposure_pct=params['max_exposure_pct'],
            weight_decay_type=self.weight_decay_type,
            weight_decay_param=params['weight_decay_param'],
            commission=self.commission,
            slippage=self.slippage,
        )
        
        strategy = GridStrategy(config)
        backtester = GridBacktester(strategy)
        
        return backtester.run(
            self.execution_data,
            start_date=self.start_date,
            initial_cash=self.initial_cash,
            commission=self.commission,
            slippage=self.slippage,
        )
    
    def _optimization_callback(self, xk: np.ndarray, convergence: float = 0.0):
        """优化回调函数（可选，用于显示进度）"""
        pass  # 可以在这里添加进度显示

