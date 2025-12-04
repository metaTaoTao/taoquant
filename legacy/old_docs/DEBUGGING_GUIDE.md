# 调试指南：验证策略与 TradingView 一致性

## 快速开始

### 1. 运行验证脚本

```bash
# 验证 7 天的 BTC 数据
python run/verify_sr_levels.py BTCUSDT 7

# 验证其他交易对
python run/verify_sr_levels.py ETHUSDT 7
```

这个脚本会：
- 加载数据并计算支撑/阻力
- 显示所有 pivot 点
- 显示确认后的支撑/阻力
- 导出 CSV 文件供对比

### 2. 在 PyCharm 中设置断点

#### 方法 1：点击行号左侧
1. 打开文件 `preprocess/build_sr_range.py`
2. 找到标记了 `🔴 BREAKPOINT` 的行
3. 点击行号左侧，会出现红色圆点
4. 运行调试模式（Shift+F9 或点击调试按钮）

#### 方法 2：使用条件断点
1. 右键点击断点
2. 选择 "More" 或 "Edit Breakpoint"
3. 设置条件，例如：
   - `len(out) > 100` - 只在数据量大于 100 时暂停
   - `out['pivot_high'].notna().any()` - 只在有 pivot high 时暂停
   - `timestamp == '2025-11-14 16:30:00'` - 只在特定时间点暂停

## 关键断点位置

### 断点 1：原始数据检查
**文件**: `preprocess/build_sr_range.py`  
**位置**: 第 64 行（`out = indicator.calculate(data)` 之前）

**检查内容**:
```python
# 在调试控制台输入：
data.head(20)  # 查看前 20 根 K 线
data.tail(20)  # 查看后 20 根 K 线
data.shape     # 查看数据维度
data['close'].describe()  # 查看价格统计
```

**验证**:
- 数据时间范围是否正确
- OHLCV 数据是否完整
- 价格是否与 TradingView 一致

### 断点 2：Pivot 点检查
**文件**: `preprocess/build_sr_range.py`  
**位置**: 第 66 行（`out = indicator.calculate(data)` 之后）

**检查内容**:
```python
# 查看所有 pivot 点
pivot_highs = out[out['pivot_high'].notna()][['pivot_high', 'close', 'high']]
pivot_lows = out[out['pivot_low'].notna()][['pivot_low', 'close', 'low']]

print("Pivot Highs:")
print(pivot_highs)

print("Pivot Lows:")
print(pivot_lows)
```

**验证**:
- 在 TradingView 中打开相同时间范围
- 使用 `ta.pivothigh(close, 20, 20)` 和 `ta.pivotlow(close, 20, 20)`
- 对比 pivot 点的位置和价格是否一致

### 断点 3：确认后的 Pivot（+20 bar）
**文件**: `preprocess/build_sr_range.py`  
**位置**: 第 70 行（`out["confirmed_low"] = ...` 之后）

**检查内容**:
```python
# 查看确认逻辑
comparison = out[['pivot_low', 'confirmed_low', 'pivot_high', 'confirmed_high']].head(50)
print(comparison)

# 验证 shift(20) 是否正确
# confirmed_low 在第 i 行应该等于 pivot_low 在第 (i-20) 行
```

**验证**:
- 确认 `shift(20)` 是否正确应用
- 检查确认时间点是否与 TradingView 一致

### 断点 4：最终支撑/阻力
**文件**: `preprocess/build_sr_range.py`  
**位置**: 第 72 行（`out["support"] = ...` 之后）

**检查内容**:
```python
# 查看最终 S/R
sr_data = out[['support', 'resistance', 'range_valid', 'close']].dropna()
print(sr_data.head(20))

# 检查特定时间点
target_time = pd.Timestamp('2025-11-14 16:30:00')
if target_time in out.index:
    print(out.loc[target_time, ['support', 'resistance', 'close']])
```

**验证**:
- 在 TradingView 中，找到相同时间点
- 检查支撑/阻力值是否一致
- 注意：TradingView 显示的是 pivot 点，我们的 support/resistance 是确认后的值

## 策略执行断点

### 断点 5：策略决策点
**文件**: `strategies/structure_weighted_grid.py`  
**位置**: 第 77 行（`def next(self):` 函数内）

**检查内容**:
```python
# 在 next() 函数开始处添加断点
# 检查每个 bar 的 S/R 值
support = float(self.data.support[0])
resistance = float(self.data.resistance[0])
close = float(self.data.close[0])

print(f"Bar {len(self.data)}: close={close}, support={support}, resistance={resistance}")
```

**验证**:
- 策略在每个时间点看到的支撑/阻力是否正确
- 价格是否在区间内
- 网格订单价格是否合理

## 对比 TradingView 的步骤

### 步骤 1：准备数据
1. 运行 `python run/verify_sr_levels.py BTCUSDT 7`
2. 打开生成的 CSV：`scripts/backtest/results/sr_verification_BTCUSDT_7d.csv`

### 步骤 2：在 TradingView 中设置
1. 打开 TradingView，选择 BTCUSDT，15m 时间框架
2. 添加 Pine Script 代码：
```pinescript
//@version=5
indicator("Pivot Check", overlay=true)
lookback = 20
pivot_high = ta.pivothigh(close, lookback, lookback)
pivot_low = ta.pivotlow(close, lookback, lookback)
plot(pivot_high, "Pivot High", color=color.red, linewidth=2)
plot(pivot_low, "Pivot Low", color=color.green, linewidth=2)
```

### 步骤 3：对比时间点
1. 在 CSV 中找到有 pivot 的时间点
2. 在 TradingView 中找到相同时间点
3. 对比 pivot 价格是否一致
4. 注意：我们的 `support`/`resistance` 是 pivot 确认后（+20 bar）的值

### 步骤 4：验证确认逻辑
1. 在 CSV 中，找到 `pivot_low` 的时间点（例如：bar 100）
2. 检查 `confirmed_low` 是否在 bar 120（100+20）出现
3. 检查 `support` 是否从 bar 120 开始有值

## 常见问题排查

### Q: Pivot 点数量不一致
**可能原因**:
- TradingView 和我们的 pivot 计算逻辑不同
- 数据时间范围不一致

**解决方法**:
- 检查 `indicators/sr_volume_boxes.py` 中的 `_pivot()` 函数
- 确保使用相同的 lookback 参数

### Q: 支撑/阻力值不匹配
**可能原因**:
- TradingView 显示的是 pivot 点，我们显示的是确认后的值
- 时间点不对齐（时区问题）

**解决方法**:
- 对比 `pivot_high`/`pivot_low` 而不是 `support`/`resistance`
- 检查时区设置（我们使用 UTC）

### Q: 策略没有交易
**检查**:
1. 在断点 4 检查 `range_valid` 是否为 True
2. 在断点 5 检查 `close` 是否在 `[support, resistance]` 区间内
3. 检查是否有微震荡冷却触发

## 调试技巧

### 1. 使用条件断点
只在特定条件下暂停：
```python
# 只在有 pivot 时暂停
out['pivot_high'].notna().any()

# 只在特定时间暂停
str(out.index[-1]) == '2025-11-14 16:30:00+00:00'
```

### 2. 使用日志断点
不暂停执行，只打印信息：
1. 右键断点 → "More"
2. 取消勾选 "Suspend"
3. 在 "Log evaluated expression" 中输入：`f"Pivot found at {out.index[-1]}"`

### 3. 导出中间结果
在断点处导出数据：
```python
# 在调试控制台执行
out.to_csv('debug_output.csv')
```

## 下一步

验证通过后，可以：
1. 运行完整回测：`python run/run_backtest_m2.py`
2. 查看性能指标和交易日志
3. 进行参数优化

