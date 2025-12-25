# Winrate 100% Bug 分析报告

> **日期**: 2025-12-03  
> **严重程度**: Critical  
> **状态**: 已确认问题

---

## 🔍 问题描述

回测结果显示 `win_rate: 1.0` (100%)，但实际存在一个止损（SL）交易，应该是亏损的。

---

## 📊 数据分析

### 1. 订单数据（orders.csv）

**SL 订单详情**：
- Entry: 2025-11-27 12:00:00, Price = 91,354.20 (SHORT)
- SL Exit: 2025-11-28 14:15:00, Price = 93,004.48 (LONG)
- Size: 2.5495 BTC

**正确的 Return 计算**（对于做空）：
```
Return = (Entry Price - Exit Price) / Entry Price
       = (91,354.20 - 93,004.48) / 91,354.20
       = -1,650.28 / 91,354.20
       = -0.018065 (-1.81%)
```

**结论**: SL 交易应该是 **-1.81%** 的亏损。

---

### 2. 交易数据（trades.csv）

**SL 交易在 trades.csv 中的记录**：
- Entry time: **2025-10-06 20:00:00** ❌ (错误！应该是 2025-11-27 12:00:00)
- Exit time: 2025-11-28 14:15:00 ✅ (正确)
- Return: **0.058286 (5.83%)** ❌ (应该是 -1.81%)

**问题**：
1. Entry time 被错误地设置为第一个 entry 的时间（2025-10-06）
2. Return 被错误地计算为正数（5.83%），而不是负数（-1.81%）

---

## 🐛 根本原因

### VectorBT 的部分平仓处理问题

当使用 `from_orders()` 进行部分平仓时，VectorBT 的行为：

1. **多个部分平仓被合并**：
   - 同一个 entry 的多个 exits（TP1, TP2, SL）可能被合并到一个 trade 记录
   - Entry time 可能被错误地设置为第一个 entry 的时间

2. **Entry price 计算错误**：
   - VectorBT 可能使用了错误的 entry_price（来自第一个 entry）
   - 导致 return 计算错误

3. **Trade 匹配问题**：
   - 部分平仓导致 entry-exit 匹配混乱
   - 最后一个 exit（SL）被错误地匹配到了第一个 entry

---

## 📈 影响分析

### 当前状态

| 指标 | 实际值 | 应该的值 |
|------|--------|----------|
| Total Trades | 8 | 8 |
| Winning Trades | 8 | 7 |
| Losing Trades | 0 | 1 |
| Win Rate | 100% | 87.5% |
| SL Trade Return | +5.83% | -1.81% |

### 性能指标影响

- **Win Rate**: 被高估（100% vs 87.5%）
- **Profit Factor**: 无法计算（avg_loss = 0）
- **Sharpe Ratio**: 可能被高估（没有亏损交易）

---

## 🔧 解决方案

### 方案 1: 从 orders.csv 重新计算 trades（推荐）

**优点**：
- 使用准确的订单数据
- 可以正确匹配 entry-exit
- 可以正确计算 return

**实现**：
```python
def recalculate_trades_from_orders(orders_df: pd.DataFrame) -> pd.DataFrame:
    """
    从 orders.csv 重新计算 trades，确保 entry-exit 正确匹配。
    """
    trades_list = []
    current_entry = None
    
    for _, order in orders_df.iterrows():
        if order['order_type'] == 'ENTRY':
            current_entry = {
                'entry_time': order['timestamp'],
                'entry_price': order['price'],
                'entry_size': order['size'],
                'exits': []
            }
        elif order['order_type'] in ['TP1', 'TP2', 'SL'] and current_entry:
            # 对于部分平仓，每个 exit 都是一个独立的 trade
            exit_price = order['price']
            exit_size = order['size']
            entry_price = current_entry['entry_price']
            
            # 计算 return（对于做空）
            return_pct = (entry_price - exit_price) / entry_price
            
            trades_list.append({
                'entry_time': current_entry['entry_time'],
                'exit_time': order['timestamp'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'size': exit_size,
                'return_pct': return_pct,
                'order_type': order['order_type']
            })
            
            # 更新剩余仓位
            current_entry['entry_size'] -= exit_size
            if current_entry['entry_size'] < 0.001:
                current_entry = None  # 仓位已全部平仓
    
    return pd.DataFrame(trades_list)
```

### 方案 2: 修复 VectorBT 的 trades 提取逻辑

**问题**：当前代码直接使用 `portfolio.trades.records_readable`，没有验证 entry-exit 匹配。

**修复**：
1. 验证每个 trade 的 entry_time 是否与 orders 中的 entry 匹配
2. 如果不匹配，从 orders 中查找正确的 entry
3. 重新计算 return

### 方案 3: 使用 orders.csv 计算 win rate

**临时方案**：
- 直接从 `orders.csv` 计算 win rate
- 忽略 `trades.csv` 中的错误数据

---

## 🎯 建议

1. **立即修复**：实现方案 1，从 orders.csv 重新计算 trades
2. **验证**：确保所有 trades 的 entry-exit 匹配正确
3. **测试**：重新运行回测，验证 win rate 是否正确

---

## 📝 相关文件

- `execution/engines/vectorbt_engine.py` - `_extract_trades()` 方法
- `run/results/SR Short 4H_BTCUSDT_15m_orders.csv` - 准确的订单数据
- `run/results/SR Short 4H_BTCUSDT_15m_trades.csv` - 错误的交易数据

---

**状态**: 待修复  
**优先级**: High  
**分配给**: 需要修复 `_extract_trades()` 方法

