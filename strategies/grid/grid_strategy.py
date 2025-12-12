"""
网格策略实现 - 基于文档 Part 4: 网格区间内的仓位管理

核心功能：
1. 在指定区间内设置网格
2. 衰减式仓位分配（底部重，顶部轻）
3. 价格触及网格线时自动买卖
4. 支持参数优化以最大化 Sharpe Ratio
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

from strategies.base_strategy import BaseStrategy, StrategyConfig


@dataclass
class GridStrategyConfig(StrategyConfig):
    """
    网格策略配置参数
    
    根据文档 Part 4，需要优化的参数：
    - grid_spacing_pct: 网格间距（价格百分比）
    - position_fraction: 单格仓位比例（资金的百分比）
    - max_exposure_pct: 最大资金暴露
    - weight_decay_type: 仓位衰减类型（linear/exponential/power）
    - weight_decay_param: 衰减参数
    """
    
    # 网格区间（由交易员手动设置）
    upper_bound: float  # 上界（阻力）
    lower_bound: float  # 下界（支撑）
    
    # 网格参数（需要优化）
    grid_spacing_pct: float = 1.5  # 网格间距（%），默认 1-2%
    position_fraction: float = 0.05  # 单格仓位比例（资金的%），默认 3-10%
    max_exposure_pct: float = 0.40  # 最大资金暴露，默认 30-50%
    
    # 仓位衰减参数（需要优化）
    weight_decay_type: Literal['linear', 'exponential', 'power'] = 'exponential'
    weight_decay_param: float = 0.15  # 衰减强度参数
    
    # 交易成本
    commission: float = 0.001  # 手续费 0.1%
    slippage: float = 0.0005  # 滑点 0.05%
    
    # 风险控制
    stop_loss_pct: Optional[float] = None  # 区间失效止损（下破支撑多少%）
    time_stop_days: Optional[int] = None  # 时间止损（天数）


class GridStrategy:
    """
    网格策略实现
    
    根据文档 Part 4，实现：
    1. 衰减式仓位分配（Martingale 反向）
    2. 网格订单生成
    3. 区间失效检测
    """
    
    def __init__(self, config: GridStrategyConfig):
        self.config = config
        self._validate_config()
    
    def _validate_config(self):
        """验证配置参数"""
        if self.config.upper_bound <= self.config.lower_bound:
            raise ValueError("upper_bound must be greater than lower_bound")
        
        if not (0 < self.config.grid_spacing_pct < 10):
            raise ValueError("grid_spacing_pct should be between 0 and 10%")
        
        if not (0 < self.config.position_fraction <= 1):
            raise ValueError("position_fraction should be between 0 and 1")
        
        if not (0 < self.config.max_exposure_pct <= 1):
            raise ValueError("max_exposure_pct should be between 0 and 1")
    
    def generate_grid_levels(self) -> pd.DataFrame:
        """
        生成网格价格水平
        
        Returns
        -------
        pd.DataFrame
            Columns: ['price', 'level', 'weight', 'direction']
            - price: 网格价格
            - level: 网格层级（0 为中间，负数向下，正数向上）
            - weight: 仓位权重（衰减式）
            - direction: 'buy' 或 'sell'
        """
        spacing = self.config.grid_spacing_pct / 100.0
        mid_price = (self.config.upper_bound + self.config.lower_bound) / 2.0
        
        # 计算网格层级
        levels = []
        
        # 向下网格（买入）
        level = 0
        price = mid_price
        while price >= self.config.lower_bound:
            levels.append({
                'price': price,
                'level': level,
                'direction': 'buy'
            })
            level -= 1
            price = mid_price * (1 - abs(level) * spacing)
        
        # 向上网格（卖出）
        level = 0
        price = mid_price
        while price <= self.config.upper_bound:
            if level != 0:  # 跳过中间层
                levels.append({
                    'price': price,
                    'level': level,
                    'direction': 'sell'
                })
            level += 1
            price = mid_price * (1 + level * spacing)
        
        df = pd.DataFrame(levels)
        
        # 计算仓位权重（衰减式）
        df['weight'] = self._calculate_weights(df['level'].values)
        
        return df.sort_values('price')
    
    def _calculate_weights(self, levels: np.ndarray) -> np.ndarray:
        """
        计算衰减式仓位权重
        
        根据文档：底部区域仓位更重，越往上越轻
        
        Parameters
        ----------
        levels : np.ndarray
            网格层级数组（负数=底部，正数=顶部）
        
        Returns
        -------
        np.ndarray
            仓位权重数组
        """
        # 归一化层级到 [0, 1]，底部=0，顶部=1
        min_level = levels.min()
        max_level = levels.max()
        if max_level == min_level:
            return np.ones_like(levels)
        
        normalized = (levels - min_level) / (max_level - min_level)
        
        # 根据衰减类型计算权重
        if self.config.weight_decay_type == 'linear':
            # 线性衰减：w = 1 - alpha * normalized
            weights = 1.0 - self.config.weight_decay_param * normalized
        
        elif self.config.weight_decay_type == 'exponential':
            # 指数衰减：w = exp(-alpha * normalized)
            weights = np.exp(-self.config.weight_decay_param * normalized)
        
        elif self.config.weight_decay_type == 'power':
            # 幂衰减：w = (1 - normalized)^alpha
            weights = np.power(1.0 - normalized, self.config.weight_decay_param)
        
        else:
            raise ValueError(f"Unknown weight_decay_type: {self.config.weight_decay_type}")
        
        # 归一化权重，使总和等于 position_fraction
        weights = weights / weights.sum() * self.config.position_fraction
        
        return weights
    
    def generate_orders(
        self,
        data: pd.DataFrame,
        initial_cash: float = 100000.0
    ) -> pd.DataFrame:
        """
        根据价格数据生成网格订单
        
        当价格触及网格线时，生成买卖订单
        
        Parameters
        ----------
        data : pd.DataFrame
            OHLCV 数据，必须包含 'close' 列
        initial_cash : float
            初始资金
        
        Returns
        -------
        pd.DataFrame
            Orders DataFrame with columns:
            - time: datetime
            - price: float (成交价格)
            - size: float (订单大小，正数=买入，负数=卖出)
            - grid_level: int (网格层级)
            - direction: str ('buy' or 'sell')
        """
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # 生成网格水平
        grid_levels = self.generate_grid_levels()
        
        # 初始化订单列表
        orders = []
        
        # 跟踪已触发的网格（避免重复触发）
        triggered_grids = set()
        
        # 当前持仓（用于计算可用资金）
        current_position = 0.0
        current_cash = initial_cash
        
        # 遍历每个 bar
        for i, (timestamp, row) in enumerate(data.iterrows()):
            close_price = row['close']
            high_price = row['high']
            low_price = row['low']
            
            # 检查是否在区间内（允许价格暂时超出，但只在区间内交易）
            # 如果价格完全超出区间，停止交易
            if close_price < self.config.lower_bound * 0.99 or close_price > self.config.upper_bound * 1.01:
                # 区间失效，停止交易
                continue
            
            # 检查每个网格水平是否被触发
            for _, grid in grid_levels.iterrows():
                grid_price = grid['price']
                grid_level = int(grid['level'])
                grid_key = (grid_level, grid['direction'])
                
                # 跳过已触发的网格
                if grid_key in triggered_grids:
                    continue
                
                # 检查是否触及网格线
                triggered = False
                if grid['direction'] == 'buy':
                    # 买单：价格跌到或低于网格价格（在区间内）
                    if (low_price <= grid_price <= high_price and 
                        self.config.lower_bound <= grid_price <= self.config.upper_bound):
                        triggered = True
                else:  # sell
                    # 卖单：价格涨到或高于网格价格（在区间内）
                    if (low_price <= grid_price <= high_price and 
                        self.config.lower_bound <= grid_price <= self.config.upper_bound):
                        triggered = True
                
                if triggered:
                    # 计算订单大小
                    weight = grid['weight']
                    
                    if grid['direction'] == 'buy':
                        # 买入：使用可用资金
                        order_size = (current_cash * weight) / grid_price
                        if order_size > 0:
                            orders.append({
                                'time': timestamp,
                                'price': grid_price,
                                'size': order_size,
                                'grid_level': grid_level,
                                'direction': 'buy'
                            })
                            current_cash -= order_size * grid_price
                            current_position += order_size
                    
                    else:  # sell
                        # 卖出：使用持仓
                        if current_position > 0:
                            order_size = current_position * weight
                            if order_size > 0:
                                orders.append({
                                    'time': timestamp,
                                    'price': grid_price,
                                    'size': -order_size,  # 负数表示卖出
                                    'grid_level': grid_level,
                                    'direction': 'sell'
                                })
                                current_position -= order_size
                                current_cash += order_size * grid_price
                    
                    # 标记为已触发
                    triggered_grids.add(grid_key)
        
        if not orders:
            return pd.DataFrame(columns=['time', 'price', 'size', 'grid_level', 'direction'])
        
        return pd.DataFrame(orders).set_index('time')
    
    def get_grid_info(self) -> dict:
        """
        获取网格信息（用于显示和验证）
        
        Returns
        -------
        dict
            网格信息字典
        """
        grid_levels = self.generate_grid_levels()
        
        return {
            'num_levels': len(grid_levels),
            'buy_levels': len(grid_levels[grid_levels['direction'] == 'buy']),
            'sell_levels': len(grid_levels[grid_levels['direction'] == 'sell']),
            'price_range': {
                'upper': self.config.upper_bound,
                'lower': self.config.lower_bound,
                'mid': (self.config.upper_bound + self.config.lower_bound) / 2.0,
                'width_pct': (self.config.upper_bound - self.config.lower_bound) / 
                            ((self.config.upper_bound + self.config.lower_bound) / 2.0) * 100
            },
            'grid_spacing_pct': self.config.grid_spacing_pct,
            'total_weight': grid_levels['weight'].sum(),
            'max_exposure_pct': self.config.max_exposure_pct
        }

