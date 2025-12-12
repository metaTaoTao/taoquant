"""
网格策略回测引擎

使用 VectorBT 进行高性能回测，支持1分钟K线精确执行
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT is required. Install with: pip install vectorbt")

from execution.engines.base import BacktestConfig, BacktestResult
from strategies.grid.grid_strategy import GridStrategy, GridStrategyConfig


@dataclass
class GridBacktestConfig(BacktestConfig):
    """网格策略回测配置"""
    pass  # 继承 BacktestConfig 的所有字段


class GridBacktester:
    """
    网格策略回测器
    
    使用 VectorBT 进行向量化回测
    支持1分钟K线精确执行订单
    """
    
    def __init__(self, strategy: GridStrategy):
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
        运行网格策略回测（使用1分钟K线执行）
        
        网格设置基于策略配置的区间，订单执行基于1分钟K线数据
        
        Parameters
        ----------
        execution_data : pd.DataFrame
            执行数据（建议使用1分钟K线，更精确）
            必须包含 ['open', 'high', 'low', 'close', 'volume']
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
        # 过滤数据到指定日期范围
        if start_date is not None:
            execution_data = execution_data[execution_data.index >= start_date]
        if end_date is not None:
            execution_data = execution_data[execution_data.index <= end_date]
        
        if len(execution_data) == 0:
            raise ValueError("No data in specified date range")
        
        # 在1分钟数据上生成订单（更精确的成交判断）
        orders_df = self.strategy.generate_orders(execution_data, initial_cash)
        
        if len(orders_df) == 0:
            # 没有订单，返回空结果
            return self._create_empty_result(execution_data, initial_cash)
        
        # 准备 VectorBT 输入
        close_prices = execution_data['close']
        
        # 将订单转换为 VectorBT 格式
        # VectorBT 需要订单大小序列（与 close_prices 对齐）
        order_sizes = pd.Series(0.0, index=close_prices.index)
        
        for order_time, order in orders_df.iterrows():
            # 找到最接近的 bar（1分钟精度）
            if order_time in order_sizes.index:
                order_sizes.loc[order_time] = order['size']
            else:
                # 找到下一个 bar
                next_bars = order_sizes.index[order_sizes.index >= order_time]
                if len(next_bars) > 0:
                    order_sizes.loc[next_bars[0]] = order['size']
        
        # 自动检测时间框架频率
        freq = self._detect_frequency(close_prices.index)
        
        # 使用 VectorBT 回测
        portfolio = vbt.Portfolio.from_orders(
            close=close_prices,
            size=order_sizes,
            size_type='amount',  # 使用绝对数量
            init_cash=initial_cash,
            fees=commission,
            slippage=slippage,
            freq=freq,
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
        """从 VectorBT Portfolio 提取标准化结果"""
        
        # 提取交易记录
        trades = portfolio.trades.records_readable
        
        # 提取权益曲线
        equity = portfolio.value()
        cash = portfolio.cash()
        position_value = equity - cash
        
        equity_curve = pd.DataFrame({
            'equity': equity,
            'cash': cash,
            'position_value': position_value
        }, index=data.index)
        
        # 计算性能指标
        returns = portfolio.returns()
        
        # Sharpe Ratio（年化）
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        
        # Sortino Ratio
        sortino_ratio = self._calculate_sortino_ratio(returns)
        
        # 最大回撤
        equity_series = equity_curve['equity']
        cumulative_max = equity_series.expanding().max()
        drawdown = (equity_series - cumulative_max) / cumulative_max
        max_drawdown = drawdown.min() * 100  # 转换为百分比
        
        # 总收益率
        total_return = (equity_series.iloc[-1] / initial_cash - 1) * 100
        
        # 胜率
        if len(trades) > 0 and 'PnL' in trades.columns:
            winning_trades = trades[trades['PnL'] > 0]
            win_rate = len(winning_trades) / len(trades) * 100
        else:
            win_rate = 0.0
        
        # Profit Factor
        if len(trades) > 0 and 'PnL' in trades.columns:
            gross_profit = trades[trades['PnL'] > 0]['PnL'].sum()
            gross_loss = abs(trades[trades['PnL'] < 0]['PnL'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        else:
            profit_factor = 0.0
        
        # 持仓记录
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
            'engine': 'GridBacktester',
            'start_time': data.index[0],
            'end_time': data.index[-1],
            'duration': data.index[-1] - data.index[0],
            'initial_cash': initial_cash,
            'execution_timeframe': self._detect_timeframe(data),
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
        
        # 根据数据频率计算年化因子
        # 假设是1分钟数据，一年约 365 * 24 * 60 = 525600 分钟
        # 但更准确的方式是根据实际时间跨度计算
        periods_per_year = 252 * 24 * 60  # 1分钟数据，假设一年252个交易日
        excess_returns = returns - risk_free_rate / periods_per_year
        
        sharpe = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()
        return sharpe if not np.isnan(sharpe) else 0.0
    
    def _calculate_sortino_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """计算年化 Sortino Ratio（只考虑下行波动）"""
        if len(returns) == 0:
            return 0.0
        
        # 根据数据频率计算年化因子
        periods_per_year = 252 * 24 * 60  # 1分钟数据
        excess_returns = returns - risk_free_rate / periods_per_year
        
        # 只考虑负收益
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
        
        # 计算平均时间间隔
        time_diffs = index.to_series().diff().dropna()
        avg_diff = time_diffs.median()
        
        # 转换为 pandas 频率字符串
        if avg_diff <= pd.Timedelta(minutes=1):
            return '1min'
        elif avg_diff <= pd.Timedelta(minutes=5):
            return '5min'
        elif avg_diff <= pd.Timedelta(minutes=15):
            return '15min'
        elif avg_diff <= pd.Timedelta(hours=1):
            return '1H'
        elif avg_diff <= pd.Timedelta(hours=4):
            return '4H'
        elif avg_diff <= pd.Timedelta(days=1):
            return '1D'
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
        elif avg_diff <= pd.Timedelta(minutes=5):
            return '5m'
        elif avg_diff <= pd.Timedelta(minutes=15):
            return '15m'
        elif avg_diff <= pd.Timedelta(hours=1):
            return '1h'
        elif avg_diff <= pd.Timedelta(hours=4):
            return '4h'
        else:
            return '1d'
    
    def _create_empty_result(self, data: pd.DataFrame, initial_cash: float) -> BacktestResult:
        """创建空结果（没有交易时）"""
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
                'engine': 'GridBacktester',
                'start_time': data.index[0],
                'end_time': data.index[-1],
                'duration': data.index[-1] - data.index[0],
                'initial_cash': initial_cash,
                'execution_timeframe': self._detect_timeframe(data),
            }
        )
