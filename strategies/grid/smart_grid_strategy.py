"""
智能动态网格策略 - 基于《智能动态网格系统.pdf》

核心特性：
1. 支持做空（卖单可以直接做空）
2. 配对网格（每次买入后在上一个格子挂卖单，形成配对）
3. 动态仓位控制（衰减机制、边缘加权）
4. 几何网格（价格越远间距越大）
5. 结构驱动的仓位分配

网格模式：
- Neutral: 中性配对网格（优先兑现上一格利润）
- Long: 震荡做多（偏向做多，但仍保持配对）
- Short: 震荡做空（偏向做空，但仍保持配对）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Dict, Tuple, List

import numpy as np
import pandas as pd

from strategies.base_strategy import BaseStrategy, StrategyConfig


@dataclass
class SmartGridConfig(StrategyConfig):
    """
    智能动态网格策略配置
    
    基于文档的核心参数：
    - 几何网格间距
    - 边缘加权仓位
    - 命中衰减机制
    - 做空支持
    - 配对网格逻辑
    """
    
    # 网格区间（由交易员手动设置）
    upper_bound: float  # 上界（阻力）
    lower_bound: float  # 下界（支撑）
    
    # 几何网格参数
    grid_gap_pct: float = 0.0018  # 基础网格间距（%），文档建议 0.0018
    alpha: float = 2.0  # 几何序列系数，价格越远间距越大
    max_layers_per_side: int = 10  # 单边最多层数
    
    # 仓位管理参数
    position_fraction: float = 0.05  # 单格基础仓位比例
    max_exposure_pct: float = 0.50  # 最大资金暴露（文档建议 0.5）
    edge_weight_multiplier: float = 2.0  # 边缘权重倍数（靠近支撑/阻力权重更大）
    
    # 衰减机制参数
    enable_hit_decay: bool = True  # 启用命中衰减
    decay_k: float = 2.0  # 衰减系数（文档建议 2.0）
    
    # 做空支持
    allow_shorting: bool = True  # 允许做空
    short_leverage: float = 1.0  # 做空杠杆（1.0 = 无杠杆做空）
    
    # 多笔交易支持
    allow_multiple_positions: bool = True  # 允许多个网格同时持仓
    max_concurrent_positions: int = 20  # 最大同时持仓数
    
    # 网格模式（根据市场状态选择）
    grid_mode: Literal['Neutral', 'Long', 'Short'] = 'Neutral'
    # 'Neutral': 中性配对网格（优先兑现上一格利润）
    # 'Long': 震荡做多（偏向做多，但仍保持配对）
    # 'Short': 震荡做空（偏向做空，但仍保持配对）
    
    # 交易成本
    commission: float = 0.001  # 手续费 0.1%
    slippage: float = 0.0005  # 滑点 0.05%


class GridPosition:
    """网格持仓记录（用于配对网格）"""
    def __init__(self, entry_price: float, entry_level: int, size: float, pair_exit_price: float, is_long: bool = True):
        self.entry_price = entry_price  # 开仓价格
        self.entry_level = entry_level  # 开仓网格层级
        self.size = size  # 持仓数量
        self.pair_exit_price = pair_exit_price  # 配对平仓价位
        self.is_long = is_long  # True=多头，False=空头
        self.sold = False  # 是否已平仓


class GridLock:
    """网格锁状态（防止重复触发）"""
    IDLE = "IDLE"      # 空闲：允许开仓一次
    OPENED = "OPENED"  # 已开仓：已在该格子开过仓，等待配对卖出完成
    CLOSED = "CLOSED"  # 已配对：配对完成，格子解锁，回到IDLE
    
    def __init__(self, grid_price: float, grid_level: int, direction: str):
        self.grid_price = grid_price
        self.grid_level = grid_level
        self.direction = direction
        self.state = self.IDLE
        self.last_price = None  # 上次价格（用于穿越检测，可选）


class SmartGridStrategy:
    """
    智能动态网格策略（配对网格实现）
    
    核心改进：
    1. 配对网格：每次买入后在上一个格子挂卖单，形成配对
    2. 优先兑现：价格回到上一格时，优先卖出配对的那份
    3. 支持做空：卖单可以直接做空（Short模式）
    4. 几何网格：价格越远间距越大
    5. 边缘加权：靠近支撑/阻力权重更大
    6. 命中衰减：频繁触发的网格权重自动衰减
    """
    
    def __init__(self, config: SmartGridConfig):
        self.config = config
        self._validate_config()
        
        # 跟踪每个网格的命中次数（用于衰减）
        self.grid_hit_counts: Dict[Tuple[int, str], int] = {}
        
        # 配对网格：跟踪每笔买入的配对卖出价位
        self.long_positions: List[GridPosition] = []  # 多头持仓列表（配对网格）
        self.short_positions: List[GridPosition] = []  # 空头持仓列表（配对网格）
        
        # 网格锁：防止重复触发
        self.grid_locks: Dict[Tuple[int, str], GridLock] = {}  # {(level, direction): GridLock}
        
        # 注意：不使用冷却时间，因为：
        # 1. 网格锁的OPENED状态已经阻止重复触发
        # 2. 穿越触发（crossing）已经过滤了大部分震荡
        # 3. 配对完成后立即解锁，允许再次触发（如果价格真的穿越了）
    
    def _validate_config(self):
        """验证配置参数"""
        if self.config.upper_bound <= self.config.lower_bound:
            raise ValueError("upper_bound must be greater than lower_bound")
        
        if not (0 < self.config.grid_gap_pct < 0.1):
            raise ValueError("grid_gap_pct should be between 0 and 10%")
        
        if self.config.alpha <= 0:
            raise ValueError("alpha must be positive")
    
    def generate_geometric_grid_levels(self, current_price: float) -> pd.DataFrame:
        """
        生成几何网格水平
        
        几何网格：价格越远间距越大
        price_n = price_0 * (1 ± gap * alpha^n)
        
        Parameters
        ----------
        current_price : float
            当前价格（作为网格中心）
        
        Returns
        -------
        pd.DataFrame
            Columns: ['price', 'level', 'weight', 'direction', 'distance_from_edge']
        """
        levels = []
        gap = self.config.grid_gap_pct
        
        # 向下网格（买入/做多）
        for n in range(self.config.max_layers_per_side + 1):
            if n == 0:
                price = current_price
            else:
                # 几何序列：间距 = gap * alpha^n
                spacing = gap * (self.config.alpha ** n)
                price = current_price * (1 - spacing)
            
            # 只保留在区间内的网格
            if price >= self.config.lower_bound:
                levels.append({
                    'price': price,
                    'level': -n,
                    'direction': 'buy',
                    'distance_from_edge': (price - self.config.lower_bound) / 
                                         (self.config.upper_bound - self.config.lower_bound)
                })
            else:
                break
        
        # 向上网格（卖出/做空）
        for n in range(1, self.config.max_layers_per_side + 1):
            # 几何序列：间距 = gap * alpha^n
            spacing = gap * (self.config.alpha ** n)
            price = current_price * (1 + spacing)
            
            # 只保留在区间内的网格
            if price <= self.config.upper_bound:
                levels.append({
                    'price': price,
                    'level': n,
                    'direction': 'sell',
                    'distance_from_edge': (self.config.upper_bound - price) / 
                                         (self.config.upper_bound - self.config.lower_bound)
                })
            else:
                break
        
        df = pd.DataFrame(levels)
        
        if len(df) == 0:
            return df
        
        # 计算边缘加权仓位
        df['weight'] = self._calculate_edge_weighted_weights(df)
        
        return df.sort_values('price')
    
    def _calculate_edge_weighted_weights(self, grid_df: pd.DataFrame) -> np.ndarray:
        """
        计算边缘加权仓位（根据网格模式调整）
        
        根据文档和网格模式：
        - Neutral: 双向网格，靠近支撑/阻力权重都大
        - Long: 震荡做多，买入权重更大，卖出权重减小
        - Short: 震荡做空，卖出权重更大，买入权重减小
        
        Parameters
        ----------
        grid_df : pd.DataFrame
            网格DataFrame，必须包含 'distance_from_edge' 和 'direction'
        
        Returns
        -------
        np.ndarray
            仓位权重数组
        """
        weights = np.zeros(len(grid_df))
        
        for i, row in grid_df.iterrows():
            distance = row['distance_from_edge']
            direction = row['direction']
            
            # 基础边缘加权
            if direction == 'buy':
                # 买入：靠近支撑（distance ≈ 0）权重最大
                edge_factor = 1.0 + self.config.edge_weight_multiplier * (1.0 - distance)
            else:  # sell
                # 卖出：靠近阻力（distance ≈ 0）权重最大
                edge_factor = 1.0 + self.config.edge_weight_multiplier * (1.0 - distance)
            
            # 根据网格模式调整权重
            if self.config.grid_mode == 'Neutral':
                # 中性模式：双向，不调整
                mode_factor = 1.0
            elif self.config.grid_mode == 'Long':
                # 震荡做多：买入权重增加，卖出权重减少
                if direction == 'buy':
                    mode_factor = 2.0  # 做多方向权重加倍
                else:  # sell
                    mode_factor = 0.3  # 做空方向权重减少（但不禁用，用于平仓）
            else:  # Short
                # 震荡做空：卖出权重增加，买入权重减少
                if direction == 'sell':
                    mode_factor = 2.0  # 做空方向权重加倍
                else:  # buy
                    mode_factor = 0.3  # 做多方向权重减少（但不禁用，用于平仓）
            
            weights[i] = self.config.position_fraction * edge_factor * mode_factor
        
        # 归一化权重
        if weights.sum() > 0:
            weights = weights / weights.sum() * self.config.position_fraction * len(grid_df)
        
        return weights
    
    def _apply_hit_decay(self, grid_key: Tuple[int, str], base_weight: float) -> float:
        """
        应用命中衰减机制
        
        根据文档：w_decayed = w_raw × exp(-hits / decay_k)
        频繁触发的网格权重自动衰减
        
        Parameters
        ----------
        grid_key : Tuple[int, str]
            网格键 (level, direction)
        base_weight : float
            基础权重
        
        Returns
        -------
        float
            衰减后的权重
        """
        if not self.config.enable_hit_decay:
            return base_weight
        
        hits = self.grid_hit_counts.get(grid_key, 0)
        decay_factor = np.exp(-hits / self.config.decay_k)
        
        return base_weight * decay_factor
    
    def _find_pair_sell_price(self, buy_price: float, grid_levels: pd.DataFrame) -> Optional[float]:
        """
        找到买入价对应的配对卖出价（上一格）
        
        配对规则：在价位X买入 → 在X+step卖出
        
        Parameters
        ----------
        buy_price : float
            买入价格
        grid_levels : pd.DataFrame
            网格水平DataFrame
        
        Returns
        -------
        Optional[float]
            配对卖出价格，如果找不到返回None
        """
        # 找到买入价对应的网格
        buy_grids = grid_levels[grid_levels['direction'] == 'buy'].sort_values('price')
        sell_grids = grid_levels[grid_levels['direction'] == 'sell'].sort_values('price')
        
        # 找到买入价在网格中的位置
        for i, (_, buy_grid) in enumerate(buy_grids.iterrows()):
            if abs(buy_grid['price'] - buy_price) < buy_price * 0.001:  # 允许0.1%误差
                # 找到下一个更高的卖出网格（配对卖出价）
                for _, sell_grid in sell_grids.iterrows():
                    if sell_grid['price'] > buy_price:
                        return sell_grid['price']
                break
        
        return None
    
    def _find_pair_buy_price(self, sell_price: float, grid_levels: pd.DataFrame) -> Optional[float]:
        """
        找到卖出价对应的配对买入价（下一格）
        
        配对规则：在价位X卖出（做空）→ 在X-step买入（平空）
        
        Parameters
        ----------
        sell_price : float
            卖出价格
        grid_levels : pd.DataFrame
            网格水平DataFrame
        
        Returns
        -------
        Optional[float]
            配对买入价格，如果找不到返回None
        """
        buy_grids = grid_levels[grid_levels['direction'] == 'buy'].sort_values('price', ascending=False)
        
        # 找到下一个更低的买入网格（配对买入价）
        for _, buy_grid in buy_grids.iterrows():
            if buy_grid['price'] < sell_price:
                return buy_grid['price']
        
        return None
    
    def generate_orders(
        self,
        data: pd.DataFrame,
        initial_cash: float = 100000.0
    ) -> pd.DataFrame:
        """
        生成网格订单（配对网格实现）
        
        配对网格核心规则：
        1. 在价位X买入1份 → 立即在X+step挂卖单1份（配对）
        2. 价格回到X+step时 → 优先卖出X买入的那份（兑现）
        3. 如果没有配对持仓，才考虑其他逻辑
        
        Parameters
        ----------
        data : pd.DataFrame
            OHLCV 数据（1分钟K线）
        initial_cash : float
            初始资金
        
        Returns
        -------
        pd.DataFrame
            Orders DataFrame
        """
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # 重置状态（每次生成订单时重置）
        self.grid_hit_counts.clear()
        self.long_positions.clear()
        self.short_positions.clear()
        self.grid_locks.clear()
        
        # 初始化网格锁
        mid_price = (self.config.upper_bound + self.config.lower_bound) / 2.0
        grid_levels = self.generate_geometric_grid_levels(mid_price)
        for _, grid in grid_levels.iterrows():
            grid_key = (int(grid['level']), grid['direction'])
            if grid_key not in self.grid_locks:
                self.grid_locks[grid_key] = GridLock(
                    grid_price=grid['price'],
                    grid_level=int(grid['level']),
                    direction=grid['direction']
                )
        
        orders = []
        
        # 当前资金和持仓状态
        current_cash = initial_cash
        
        # 上一个bar的价格（用于穿越检测）
        prev_close = None
        
        # 遍历每个 bar
        for i, (timestamp, row) in enumerate(data.iterrows()):
            close_price = row['close']
            high_price = row['high']
            low_price = row['low']
            
            # 检查是否在区间内
            if close_price < self.config.lower_bound * 0.99 or close_price > self.config.upper_bound * 1.01:
                prev_close = close_price
                continue
            
            # 检查每个网格水平是否被触发
            for _, grid in grid_levels.iterrows():
                grid_price = grid['price']
                grid_level = int(grid['level'])
                grid_direction = grid['direction']
                grid_key = (grid_level, grid_direction)
                grid_lock = self.grid_locks.get(grid_key)
                
                if grid_lock is None:
                    continue
                
                # ============================================================
                # 三道保险：防止重复触发
                # ============================================================
                
                # 1. 网格锁检查：状态必须是IDLE才允许触发
                if grid_lock.state != GridLock.IDLE:
                    # OPENED状态：已在该网格开仓，等待配对完成，不允许再次触发
                    # （不需要冷却时间检查，状态本身已经阻止）
                    if grid_lock.state == GridLock.OPENED:
                        continue  # 直接跳过，等待配对完成
                    
                    # CLOSED状态：配对完成，检查是否可以解锁
                    elif grid_lock.state == GridLock.CLOSED:
                        # 检查是否有该网格的持仓已全部平仓
                        all_closed = True
                        if grid_direction == 'buy':
                            for pos in self.long_positions:
                                if (not pos.sold and 
                                    abs(pos.entry_price - grid_price) < grid_price * 0.001):
                                    all_closed = False
                                    break
                        else:  # sell
                            for pos in self.short_positions:
                                if (not pos.sold and 
                                    abs(pos.entry_price - grid_price) < grid_price * 0.001):
                                    all_closed = False
                                    break
                        
                        if all_closed:
                            # 配对完成，立即解锁回到IDLE（允许再次触发）
                            # 不需要冷却时间，因为：
                            # 1. 网格锁的OPENED状态已经阻止重复触发
                            # 2. 穿越触发机制已经过滤了震荡
                            # 3. 如果价格真的穿越了网格线，应该允许再次触发
                            grid_lock.state = GridLock.IDLE
                        else:
                            # 仍有持仓，保持CLOSED状态
                            continue
                
                # 2. 穿越触发（crossing）而不是触碰触发（touch）
                # 买单：价格从上到下穿越网格线
                # 卖单：价格从下到上穿越网格线
                triggered = False
                if grid_direction == 'buy':
                    # 买单：需要从上到下穿越（prev_close > grid_price >= close_price）
                    if prev_close is not None:
                        if prev_close > grid_price and close_price <= grid_price:
                            # 从上到下穿越
                            triggered = True
                    else:
                        # 第一个bar：使用low_price判断（简化处理）
                        if low_price <= grid_price <= high_price:
                            triggered = True
                else:  # sell
                    # 卖单：需要从下到上穿越（prev_close < grid_price <= close_price）
                    if prev_close is not None:
                        if prev_close < grid_price and close_price >= grid_price:
                            # 从下到上穿越
                            triggered = True
                    else:
                        # 第一个bar：使用high_price判断（简化处理）
                        if low_price <= grid_price <= high_price:
                            triggered = True
                
                if triggered:
                    # 3. 更新网格锁状态
                    grid_lock.state = GridLock.OPENED
                    grid_lock.last_price = close_price
                    
                    # 应用命中衰减
                    base_weight = grid['weight']
                    decayed_weight = self._apply_hit_decay(grid_key, base_weight)
                    
                    # 更新命中计数
                    if self.config.enable_hit_decay:
                        self.grid_hit_counts[grid_key] = self.grid_hit_counts.get(grid_key, 0) + 1
                    
                    # ============================================================
                    # 配对网格核心逻辑
                    # ============================================================
                    
                    if grid_direction == 'buy':
                        # ========== 买入逻辑 ==========
                        
                        # 1. 优先检查是否有配对卖出（平空）
                        if self.config.grid_mode == 'Short' and len(self.short_positions) > 0:
                            # Short模式：优先平空
                            for pos in self.short_positions:
                                if not pos.sold and abs(pos.pair_exit_price - grid_price) < grid_price * 0.001:
                                    # 找到配对平空价位
                                    order_size = min(pos.size, pos.size * decayed_weight)
                                    if order_size > 0:
                                        orders.append({
                                            'time': timestamp,
                                            'price': grid_price,
                                            'size': order_size,
                                            'grid_level': grid_level,
                                            'direction': 'buy'
                                        })
                                        pos.size -= order_size
                                        if pos.size <= 0:
                                            pos.sold = True
                                            # 配对完成：解锁网格
                                            sell_grid_key = (pos.entry_level, 'sell')
                                            sell_grid_lock = self.grid_locks.get(sell_grid_key)
                                            if sell_grid_lock:
                                                sell_grid_lock.state = GridLock.CLOSED
                                        current_cash -= order_size * grid_price
                                    break
                            else:
                                # 没有配对平空，继续买入逻辑
                                pass
                        
                        # 2. 买入新仓位（配对网格）
                        # 关键：检查该网格是否已经有未平仓的持仓
                        # 配对网格规则：每个网格只触发一次，直到配对完成
                        has_open_position_at_grid = False
                        for pos in self.long_positions:
                            if not pos.sold and abs(pos.entry_price - grid_price) < grid_price * 0.001:
                                # 该网格已经有未平仓的持仓，跳过（配对网格：一个网格一次）
                                has_open_position_at_grid = True
                                break
                        
                        if not has_open_position_at_grid and (self.config.grid_mode != 'Short' or len(self.short_positions) == 0):
                            # 找到配对卖出价（上一格）
                            pair_sell_price = self._find_pair_sell_price(grid_price, grid_levels)
                            
                            if pair_sell_price is not None:
                                # 计算买入数量
                                available_cash = current_cash
                                order_size = (available_cash * decayed_weight) / grid_price
                                
                                # 检查最大暴露限制
                                total_long_size = sum(p.size for p in self.long_positions if not p.sold)
                                total_exposure = (total_long_size + order_size) * grid_price
                                max_exposure = initial_cash * self.config.max_exposure_pct
                                
                                if total_exposure > max_exposure:
                                    scale = max_exposure / total_exposure
                                    order_size = order_size * scale
                                
                                if order_size > 0:
                                    orders.append({
                                        'time': timestamp,
                                        'price': grid_price,
                                        'size': order_size,
                                        'grid_level': grid_level,
                                        'direction': 'buy'
                                    })
                                    
                                    # 创建配对持仓记录（多头）
                                    position = GridPosition(
                                        entry_price=grid_price,
                                        entry_level=grid_level,
                                        size=order_size,
                                        pair_exit_price=pair_sell_price,
                                        is_long=True
                                    )
                                    self.long_positions.append(position)
                                    
                                    # 更新资金
                                    current_cash -= order_size * grid_price
                                    
                                    # 网格锁：标记为OPENED（已开仓，等待配对）
                                    grid_lock.state = GridLock.OPENED
                    
                    else:  # sell
                        # ========== 卖出逻辑 ==========
                        
                        # 1. 优先检查是否有配对买入（平多）- 配对网格核心
                        matched = False
                        for pos in self.long_positions:
                            if not pos.sold and abs(pos.pair_exit_price - grid_price) < grid_price * 0.001:
                                # 找到配对卖出价位，优先兑现
                                order_size = min(pos.size, pos.size * decayed_weight)
                                if order_size > 0:
                                    orders.append({
                                        'time': timestamp,
                                        'price': grid_price,
                                        'size': -order_size,
                                        'grid_level': grid_level,
                                        'direction': 'sell'
                                    })
                                    pos.size -= order_size
                                    if pos.size <= 0:
                                        pos.sold = True
                                        # 配对完成：解锁网格
                                        # 找到对应的买入网格锁
                                        buy_grid_key = (pos.entry_level, 'buy')
                                        buy_grid_lock = self.grid_locks.get(buy_grid_key)
                                        if buy_grid_lock:
                                            buy_grid_lock.state = GridLock.CLOSED
                                    
                                    current_cash += order_size * grid_price
                                    matched = True
                                    break
                        
                        # 2. 如果没有配对平多，根据模式决定
                        if not matched:
                            if self.config.grid_mode == 'Long':
                                # Long模式：如果没有配对，不卖出（保持多头）
                                continue
                            elif self.config.grid_mode == 'Short' and self.config.allow_shorting:
                                # Short模式：做空（配对网格）
                                pair_buy_price = self._find_pair_buy_price(grid_price, grid_levels)
                                
                                if pair_buy_price is not None:
                                    # 计算做空数量
                                    available_cash = current_cash
                                    order_size = (available_cash * decayed_weight) / grid_price
                                    
                                    # 检查最大暴露限制
                                    total_short_size = sum(p.size for p in self.short_positions if not p.sold)
                                    total_exposure = (total_short_size + order_size) * grid_price
                                    max_exposure = initial_cash * self.config.max_exposure_pct
                                    
                                    if total_exposure > max_exposure:
                                        scale = max_exposure / total_exposure
                                        order_size = order_size * scale
                                    
                                    if order_size > 0:
                                        orders.append({
                                            'time': timestamp,
                                            'price': grid_price,
                                            'size': -order_size,  # 负数表示做空
                                            'grid_level': grid_level,
                                            'direction': 'sell'
                                        })
                                        
                                        # 创建配对持仓记录（空头）
                                        position = GridPosition(
                                            entry_price=grid_price,  # 做空的卖出价
                                            entry_level=grid_level,
                                            size=order_size,
                                            pair_exit_price=pair_buy_price,  # 配对平空价
                                            is_long=False
                                        )
                                        self.short_positions.append(position)
                                        
                                        # 更新资金（做空获得资金）
                                        current_cash += order_size * grid_price
                                        
                                        # 网格锁：标记为OPENED
                                        grid_lock.state = GridLock.OPENED
                            elif self.config.grid_mode == 'Neutral' and self.config.allow_shorting:
                                # Neutral模式：允许做空（配对网格）
                                # 检查该网格是否已经有未平仓的空头持仓
                                has_open_short_at_grid = False
                                for pos in self.short_positions:
                                    if not pos.sold and abs(pos.entry_price - grid_price) < grid_price * 0.001:
                                        has_open_short_at_grid = True
                                        break
                                
                                if not has_open_short_at_grid:
                                    pair_buy_price = self._find_pair_buy_price(grid_price, grid_levels)
                                    
                                    if pair_buy_price is not None:
                                        available_cash = current_cash
                                        order_size = (available_cash * decayed_weight) / grid_price
                                        
                                        total_short_size = sum(p.size for p in self.short_positions if not p.sold)
                                        total_exposure = (total_short_size + order_size) * grid_price
                                        max_exposure = initial_cash * self.config.max_exposure_pct
                                        
                                        if total_exposure > max_exposure:
                                            scale = max_exposure / total_exposure
                                            order_size = order_size * scale
                                        
                                        if order_size > 0:
                                            orders.append({
                                                'time': timestamp,
                                                'price': grid_price,
                                                'size': -order_size,
                                                'grid_level': grid_level,
                                                'direction': 'sell'
                                            })
                                            
                                            position = GridPosition(
                                                entry_price=grid_price,
                                                entry_level=grid_level,
                                                size=order_size,
                                                pair_exit_price=pair_buy_price,
                                                is_long=False
                                            )
                                            self.short_positions.append(position)
                                            current_cash += order_size * grid_price
                                            
                                            # 网格锁：标记为OPENED
                                            grid_lock.state = GridLock.OPENED
            
            # 更新上一个bar的价格（用于穿越检测）
            prev_close = close_price
        
        if not orders:
            return pd.DataFrame(columns=['time', 'price', 'size', 'grid_level', 'direction'])
        
        return pd.DataFrame(orders).set_index('time')
    
    def get_grid_info(self) -> dict:
        """获取网格信息"""
        mid_price = (self.config.upper_bound + self.config.lower_bound) / 2.0
        grid_levels = self.generate_geometric_grid_levels(mid_price)
        
        return {
            'num_levels': len(grid_levels),
            'buy_levels': len(grid_levels[grid_levels['direction'] == 'buy']),
            'sell_levels': len(grid_levels[grid_levels['direction'] == 'sell']),
            'price_range': {
                'upper': self.config.upper_bound,
                'lower': self.config.lower_bound,
                'mid': mid_price,
                'width_pct': (self.config.upper_bound - self.config.lower_bound) / mid_price * 100
            },
            'grid_gap_pct': self.config.grid_gap_pct,
            'alpha': self.config.alpha,
            'allow_shorting': self.config.allow_shorting,
            'allow_multiple_positions': self.config.allow_multiple_positions,
            'grid_mode': self.config.grid_mode,
        }
