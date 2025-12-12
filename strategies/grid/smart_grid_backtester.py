"""
智能网格策略回测引擎

支持做空、多笔交易的回测
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT is required. Install with: pip install vectorbt")

from execution.engines.base import BacktestResult
from strategies.grid.smart_grid_strategy import SmartGridStrategy, SmartGridConfig


class SmartGridBacktester:
    """
    智能网格策略回测器
    
    支持：
    - 做空交易
    - 多笔同时持仓
    - 动态仓位管理
    """
    
    def __init__(self, strategy: SmartGridStrategy):
        self.strategy = strategy
    
    def run(
        self,
        execution_data: pd.DataFrame,
        start_date: Optional[pd.Timestamp] = None,
        end_date: Optional[pd.Timestamp] = None,
        initial_cash: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ) -> BacktestResult:
        """
        运行智能网格策略回测
        
        Parameters
        ----------
        execution_data : pd.DataFrame
            执行数据（1分钟K线）
        start_date : pd.Timestamp, optional
            回测开始日期
        end_date : pd.Timestamp, optional
            回测结束日期
        initial_cash : float
            初始资金
        commission : float
            手续费率
        slippage : float
            滑点率
        
        Returns
        -------
        BacktestResult
            回测结果
        """
        # 过滤数据
        if start_date is not None:
            execution_data = execution_data[execution_data.index >= start_date]
        if end_date is not None:
            execution_data = execution_data[execution_data.index <= end_date]
        
        if len(execution_data) == 0:
            raise ValueError("No data in specified date range")
        
        # 生成订单
        orders_df = self.strategy.generate_orders(execution_data, initial_cash)
        
        if len(orders_df) == 0:
            return self._create_empty_result(execution_data, initial_cash)
        
        # 准备 VectorBT 输入
        close_prices = execution_data['close']
        
        # 将订单转换为 VectorBT 格式
        order_sizes = pd.Series(0.0, index=close_prices.index)
        
        for order_time, order in orders_df.iterrows():
            if order_time in order_sizes.index:
                order_sizes.loc[order_time] = order['size']
            else:
                next_bars = order_sizes.index[order_sizes.index >= order_time]
                if len(next_bars) > 0:
                    order_sizes.loc[next_bars[0]] = order['size']
        
        # 检测频率
        freq = self._detect_frequency(close_prices.index)
        
        # 使用 VectorBT 回测（支持做空）
        portfolio = vbt.Portfolio.from_orders(
            close=close_prices,
            size=order_sizes,
            size_type='amount',
            init_cash=initial_cash,
            fees=commission,
            slippage=slippage,
            freq=freq,
            # VectorBT 默认支持做空（负数size表示做空）
        )
        
        # 提取结果
        return self._extract_results(portfolio, execution_data, orders_df, initial_cash)
    
    def _extract_results(
        self,
        portfolio: vbt.Portfolio,
        data: pd.DataFrame,
        orders_df: pd.DataFrame,
        initial_cash: float
    ) -> BacktestResult:
        """从 VectorBT Portfolio 提取结果"""
        
        trades = portfolio.trades.records_readable
        
        equity = portfolio.value()
        cash = portfolio.cash()
        position_value = equity - cash
        
        equity_curve = pd.DataFrame({
            'equity': equity,
            'cash': cash,
            'position_value': position_value
        }, index=data.index)
        
        returns = portfolio.returns()
        
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        
        equity_series = equity_curve['equity']
        cumulative_max = equity_series.expanding().max()
        drawdown = (equity_series - cumulative_max) / cumulative_max
        max_drawdown = drawdown.min() * 100
        
        total_return = (equity_series.iloc[-1] / initial_cash - 1) * 100
        
        if len(trades) > 0 and 'PnL' in trades.columns:
            winning_trades = trades[trades['PnL'] > 0]
            win_rate = len(winning_trades) / len(trades) * 100
            
            gross_profit = trades[trades['PnL'] > 0]['PnL'].sum()
            gross_loss = abs(trades[trades['PnL'] < 0]['PnL'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        else:
            win_rate = 0.0
            profit_factor = 0.0
        
        positions = portfolio.positions.records_readable
        
        metrics = {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(trades),
            'final_equity': equity_series.iloc[-1],
        }
        
        metadata = {
            'engine': 'SmartGridBacktester',
            'start_time': data.index[0],
            'end_time': data.index[-1],
            'duration': data.index[-1] - data.index[0],
            'initial_cash': initial_cash,
            'execution_timeframe': self._detect_timeframe(data),
            'allow_shorting': self.strategy.config.allow_shorting,
            'allow_multiple_positions': self.strategy.config.allow_multiple_positions,
        }
        
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            positions=positions,
            metrics=metrics,
            metadata=metadata
        )
    
    def _calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """计算年化 Sharpe Ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        periods_per_year = 252 * 24 * 60  # 1分钟数据
        excess_returns = returns - risk_free_rate / periods_per_year
        
        sharpe = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()
        return sharpe if not np.isnan(sharpe) else 0.0
    
    def _calculate_sortino_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """计算年化 Sortino Ratio"""
        if len(returns) == 0:
            return 0.0
        
        periods_per_year = 252 * 24 * 60
        excess_returns = returns - risk_free_rate / periods_per_year
        
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        downside_std = downside_returns.std()
        sortino = np.sqrt(periods_per_year) * excess_returns.mean() / downside_std
        return sortino if not np.isnan(sortino) else 0.0
    
    def _detect_frequency(self, index: pd.DatetimeIndex) -> str:
        """自动检测数据频率"""
        if len(index) < 2:
            return '1min'
        
        time_diffs = index.to_series().diff().dropna()
        avg_diff = time_diffs.median()
        
        if avg_diff <= pd.Timedelta(minutes=1):
            return '1min'
        elif avg_diff <= pd.Timedelta(minutes=5):
            return '5min'
        elif avg_diff <= pd.Timedelta(minutes=15):
            return '15min'
        elif avg_diff <= pd.Timedelta(hours=1):
            return '1H'
        else:
            return '1D'
    
    def _detect_timeframe(self, data: pd.DataFrame) -> str:
        """检测数据时间框架"""
        if len(data) < 2:
            return 'unknown'
        
        time_diffs = data.index.to_series().diff().dropna()
        avg_diff = time_diffs.median()
        
        if avg_diff <= pd.Timedelta(minutes=1):
            return '1m'
        elif avg_diff <= pd.Timedelta(minutes=15):
            return '15m'
        else:
            return '1d'
    
    def _create_empty_result(self, data: pd.DataFrame, initial_cash: float) -> BacktestResult:
        """创建空结果"""
        equity_curve = pd.DataFrame({
            'equity': [initial_cash] * len(data),
            'cash': [initial_cash] * len(data),
            'position_value': [0.0] * len(data)
        }, index=data.index)
        
        return BacktestResult(
            trades=pd.DataFrame(),
            equity_curve=equity_curve,
            positions=pd.DataFrame(),
            metrics={
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'total_trades': 0,
                'final_equity': initial_cash,
            },
            metadata={
                'engine': 'SmartGridBacktester',
                'start_time': data.index[0],
                'end_time': data.index[-1],
                'duration': data.index[-1] - data.index[0],
                'initial_cash': initial_cash,
            }
        )

