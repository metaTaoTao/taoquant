# 回测框架对比：部分平仓支持

## 支持部分平仓的框架

### 1. **backtesting.py** ⭐ 推荐
- **优点：**
  - ✅ 原生支持部分平仓（`strategy.order_target_percent()`）
  - ✅ 轻量级，API简洁
  - ✅ 支持trailing stop、移动止损
  - ✅ 你已经用过，代码库中有legacy代码
  - ✅ 性能不错（Cython优化）
  - ✅ 内置Bokeh可视化（你已经用Bokeh了）

- **缺点：**
  - ❌ 单线程（但通常够用）
  - ❌ 不支持多资产组合（但你的策略是单资产）

- **部分平仓示例：**
```python
# 平掉30%仓位
strategy.order_target_percent(0.7)  # 保留70%

# 或者直接指定数量
strategy.order.size = -strategy.position.size * 0.3
```

### 2. **Backtrader**
- **优点：**
  - ✅ 功能最强大，支持部分平仓
  - ✅ 支持多资产、多策略
  - ✅ 支持实时交易
  - ✅ 丰富的技术指标库

- **缺点：**
  - ❌ 学习曲线陡峭
  - ❌ API复杂
  - ❌ 文档不够友好
  - ❌ 性能一般（事件驱动）

### 3. **Zipline**
- **优点：**
  - ✅ 支持部分平仓
  - ✅ 适合多资产组合

- **缺点：**
  - ❌ 主要面向美股
  - ❌ 配置复杂
  - ❌ 性能一般

## 推荐方案

### 方案1：使用 backtesting.py（推荐）⭐

**理由：**
1. 你已经在用Bokeh，backtesting.py原生支持Bokeh
2. 代码库中有legacy代码，可以复用
3. API简洁，容易实现部分平仓
4. 性能足够好

**实现步骤：**
1. 创建 `BacktestingPyEngine` 实现 `BacktestEngine` 接口
2. 在策略中实现部分平仓逻辑
3. 保持现有架构（策略层、引擎层分离）

### 方案2：自定义事件驱动引擎

**理由：**
1. 完全控制仓位管理
2. 可以实现任何复杂逻辑
3. 不依赖外部框架

**实现步骤：**
1. 创建 `EventDrivenEngine` 实现 `BacktestEngine` 接口
2. 实现完整的仓位管理系统
3. 支持部分平仓、trailing stop等

## 性能对比

| 框架 | 速度 | 部分平仓 | 易用性 | 推荐度 |
|------|------|----------|--------|--------|
| VectorBT | ⚡⚡⚡⚡⚡ | ❌ | ⭐⭐⭐ | ⭐⭐ |
| backtesting.py | ⚡⚡⚡⚡ | ✅ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Backtrader | ⚡⚡⚡ | ✅ | ⭐⭐ | ⭐⭐⭐ |
| 自定义引擎 | ⚡⚡⚡⚡ | ✅ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

## 建议

**立即行动：**
1. 实现 `BacktestingPyEngine`（最快，复用现有代码）
2. 保持VectorBT作为快速原型工具
3. 需要部分平仓时切换到backtesting.py

**长期考虑：**
- 如果性能是瓶颈，考虑自定义引擎
- 如果需要多资产，考虑Backtrader

