# Backtesting.py 仓位管理修复方案

## 问题诊断

### backtesting.py对size参数的处理

经过测试，发现backtesting.py对`buy()`和`sell()`的`size`参数有以下限制：

1. **0 < size < 1**: 视为权益百分比
   - 例如：`sell(size=0.10)` = 卖出权益的10%
   - ✅ 支持小数

2. **size >= 1**: 视为整数单位数
   - 例如：`sell(size=2.5)` → 取整为 `sell(2)` 或者报错
   - ❌ **不支持小数单位**
   - 警告："fractional trading is not supported"

3. **size < 某个最小阈值**: 订单被忽略
   - 测试显示 `size=0.0001667` 时订单未执行
   - 可能需要 size > 0.001 (0.1%)

### 当前代码的问题

您当前的策略使用百分比模式（Line 778-779）：

```python
target_size_pct = (target_size * current_price) / equity
```

**问题场景**：
1. **多仓位累积时超过100%**
   ```
   Trade 1: 0.1667 BTC × 50,000 / 200,000 = 0.4168 (41.68%) ✅
   Trade 2: 0.1667 BTC × 50,000 / 200,000 = 0.4168 (41.68%) ✅
   Total: 0.8336 (83.36%) ✅

   Trade 3: 0.1667 BTC × 50,000 / 200,000 = 0.4168 (41.68%)
   Total: 1.25 (125%) ❌ >= 1.0, 会被视为整数单位！
   ```

2. **Equity下降时超过100%**
   ```
   初始: 0.2 BTC × 50,000 / 200,000 = 0.50 (50%) ✅
   亏损后equity = 150,000
   现在: 0.2 BTC × 50,000 / 150,000 = 0.667 (66.7%) ✅

   继续亏损equity = 90,000
   现在: 0.2 BTC × 50,000 / 90,000 = 1.11 ❌
   ```

3. **精度损失**
   - BTC ↔ % 转换可能产生舍入误差
   - 多次调整仓位时误差累积

---

## 解决方案对比

### 方案A: 使用Satoshi单位（已实现）

**原理**: 1 BTC = 100,000,000 satoshi（整数）

**修改**:
```python
# 将所有BTC数量转换为satoshi
position_satoshi = int(position_btc * 100_000_000)

# 直接使用satoshi作为整数单位
self.sell(size=position_satoshi)  # e.g., 16,670,000
```

**优点**:
- ✅ 完全避免小数问题
- ✅ 精度高（1 satoshi = 0.00000001 BTC）
- ✅ 符合区块链实际精度

**缺点**:
- ⚠️ **数字巨大**（0.1667 BTC = 16,670,000 satoshi）
- ⚠️ backtesting.py可能对大数值有性能问题
- ⚠️ 价格仍然是 USDT/BTC，单位不统一

**适用场景**: 需要极高精度的场景

---

### 方案B: 调整数据单位（推荐）

**原理**: 将数据转换为 **μBTC** (microbitcoin) 或 **mBTC** (millibitcoin)

#### B1: 使用mBTC (1 BTC = 1000 mBTC)

```python
# 1. 修改价格数据
df['Close_mBTC'] = df['Close'] / 1000  # 50,000 → 50 USDT/mBTC
df['High_mBTC'] = df['High'] / 1000
df['Low_mBTC'] = df['Low'] / 1000
df['Open_mBTC'] = df['Open'] / 1000

# 2. 调整initial_cash（保持不变或按比例）
cash = 200,000  # USDT不变

# 3. 仓位计算
position_mbtc = position_btc * 1000  # 0.1667 BTC → 166.7 mBTC
self.sell(size=int(position_mbtc))  # 167 mBTC (整数)
```

**示例**:
```
原始:
  Price = 50,000 USDT/BTC
  Position = 0.1667 BTC
  Value = 8,335 USDT

转换后:
  Price = 50 USDT/mBTC
  Position = 167 mBTC (整数)
  Value = 167 × 50 = 8,350 USDT (误差 15 USDT ≈ 0.18%)
```

**优点**:
- ✅ 数字合理（100-1000 mBTC）
- ✅ 整数单位，无小数问题
- ✅ 误差可控（取整误差 < 1 mBTC）
- ✅ 代码修改少

**缺点**:
- ⚠️ 需要转换所有OHLC数据
- ⚠️ 价格显示不直观（50 vs 50,000）

---

#### B2: 使用μBTC (1 BTC = 1,000,000 μBTC)

```python
# 价格
df['Close_uBTC'] = df['Close'] / 1_000_000  # 50,000 → 0.05 USDT/μBTC

# 仓位
position_ubtc = position_btc * 1_000_000  # 0.1667 → 166,700 μBTC
self.sell(size=position_ubtc)
```

**优点**:
- ✅ 更高精度
- ✅ 整数单位

**缺点**:
- ⚠️ 价格太小（0.05 USDT/μBTC）
- ⚠️ 可能触发backtesting.py的最小价格限制

---

### 方案C: 确保百分比模式安全（最简单）

**原理**: 继续使用百分比，但添加安全检查

**修改 `_sync_position` 方法**:

```python
def _sync_position(self, target_size: float):
    """Sync position with safety checks."""
    if target_size <= 0:
        if self.position and self.position.size != 0:
            self.position.close()
        return

    current_idx = len(self.data) - 1
    current_price = self.data.Close[current_idx]
    equity = self.equity

    # Convert BTC to percentage
    target_size_pct = (target_size * current_price) / equity

    # 🔥 KEY FIX: Cap at safe maximum (95%)
    MAX_POSITION_PCT = 0.95
    if target_size_pct >= MAX_POSITION_PCT:
        print(f"[WARNING] Position size {target_size_pct:.2%} exceeds max {MAX_POSITION_PCT:.0%}. "
              f"Reducing to {MAX_POSITION_PCT:.0%}")
        target_size_pct = MAX_POSITION_PCT

    # 🔥 KEY FIX: Minimum position threshold (0.1%)
    MIN_POSITION_PCT = 0.001
    if target_size_pct < MIN_POSITION_PCT:
        print(f"[WARNING] Position size {target_size_pct:.4%} below minimum {MIN_POSITION_PCT:.1%}. Skipping.")
        return

    # Open/adjust position
    if not self.position or self.position.size == 0:
        self.sell(size=target_size_pct)
    else:
        current_size_pct = abs(self.position.size)

        # Handle unit/percentage混淆
        if current_size_pct >= 1.0:
            # Position is in units, convert to %
            current_size_pct = (current_size_pct * current_price) / equity
            if current_size_pct >= MAX_POSITION_PCT:
                current_size_pct = MAX_POSITION_PCT

        diff_pct = target_size_pct - current_size_pct

        # Adjust with tolerance
        if abs(diff_pct) > 0.0001:
            if diff_pct > 0:
                # Increase position
                add_pct = min(diff_pct, MAX_POSITION_PCT - current_size_pct)
                self.sell(size=add_pct)
            else:
                # Decrease position
                self.buy(size=min(abs(diff_pct), current_size_pct))
```

**优点**:
- ✅ **最少修改**，只改 `_sync_position`
- ✅ 保持原有BTC单位和价格
- ✅ 添加防护机制防止错误

**缺点**:
- ⚠️ 在极端情况（equity暴跌）下可能仍有问题
- ⚠️ 仓位可能被强制限制在95%

---

### 方案D: 增加Initial Capital

**原理**: 将`initial_capital`设置得足够大，确保任何仓位都 < 100%

```python
# core/config.py
@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0  # 100万USDT
    commission: float = 0.004
    slippage: float = 0.0005
```

**计算**:
```
如果最大仓位 = 5个 × 0.2 BTC = 1.0 BTC
价格 = 50,000 USDT
最大价值 = 50,000 USDT

需要cash > 50,000 / 0.95 ≈ 53,000 USDT
建议cash ≥ 100,000 USDT（2倍安全边际）
```

**优点**:
- ✅ **最简单**，只改一个参数
- ✅ 不影响策略逻辑
- ✅ 百分比模式仍然有效

**缺点**:
- ⚠️ 回测资金不真实（实际账户可能只有10万）
- ⚠️ 收益率计算会失真

---

## 推荐方案

### 短期方案（立即修复）: **方案C + 方案D组合**

1. **增加initial_capital到500,000或1,000,000**
   ```python
   # core/config.py
   initial_capital: float = 500_000.0
   ```

2. **修改`_sync_position`添加安全检查**（见方案C代码）

**原因**:
- 修改最少，风险最低
- 立即解决size >= 1.0的问题
- 保持所有现有逻辑不变

---

### 长期方案（最优）: **方案B1 (mBTC单位)**

**实施步骤**:

1. **创建数据转换函数**:
```python
# utils/data_conversion.py
def convert_to_mbtc(df: pd.DataFrame) -> pd.DataFrame:
    """Convert BTC-priced data to mBTC units."""
    df_mbtc = df.copy()

    # Convert prices (USDT/BTC → USDT/mBTC)
    price_cols = ['Open', 'High', 'Low', 'Close']
    for col in price_cols:
        if col in df_mbtc.columns:
            df_mbtc[col] = df_mbtc[col] / 1000

    # Volume stays in BTC (or convert to mBTC if needed)
    if 'Volume' in df_mbtc.columns:
        df_mbtc['Volume'] = df_mbtc['Volume'] * 1000  # BTC → mBTC

    return df_mbtc
```

2. **在回测引擎中转换数据**:
```python
# backtest/engine.py
from utils.data_conversion import convert_to_mbtc

def run_backtest(...):
    # ...
    dataset = _prepare_dataset(data)

    # Convert to mBTC if trading crypto
    if symbol.endswith('USDT') or symbol.endswith('USD'):
        dataset = convert_to_mbtc(dataset)
        # Adjust cash accordingly (optional)
        cash_mbtc = cash  # Keep USDT amount same
    # ...
```

3. **修改仓位计算**:
```python
def _calculate_position_size(self, entry_price, stop_distance, equity):
    # Calculate in BTC first
    risk_amount = equity * (self.risk_per_trade_pct / 100)
    position_btc = risk_amount / stop_distance

    # Convert to mBTC (integer)
    position_mbtc = int(position_btc * 1000)

    return position_mbtc

def _sync_position(self, target_mbtc: int):
    if target_mbtc <= 0:
        if self.position:
            self.position.close()
        return

    # Use integer mBTC directly
    if not self.position or self.position.size == 0:
        self.sell(size=target_mbtc)
    else:
        current = abs(self.position.size)
        diff = target_mbtc - current
        if abs(diff) >= 1:  # At least 1 mBTC difference
            if diff > 0:
                self.sell(size=diff)
            else:
                self.buy(size=abs(diff))
```

---

## 实施建议

### 第一步: 立即修复（今天）
使用**方案C + D**:
1. 修改`core/config.py`中的`initial_capital`为500,000
2. 在`_sync_position`中添加安全检查（MAX_POSITION_PCT = 0.95）

### 第二步: 验证（明天）
1. 运行现有回测
2. 检查是否还有size相关警告
3. 验证仓位管理正确性

### 第三步: 长期优化（下周）
1. 实施**方案B1 (mBTC)**
2. 创建单元测试验证转换正确性
3. 对比新旧方案的回测结果

---

## 测试清单

完成修复后，请验证以下场景：

- [ ] 单笔交易：0.1667 BTC开仓
- [ ] 多笔交易：3个虚拟交易同时活跃
- [ ] 最大仓位：5个交易累计1.0 BTC
- [ ] Equity下降：从200k跌到100k时仓位调整
- [ ] 部分平仓：30%仓位止盈后剩余70%
- [ ] 移动止盈：70%仓位的SL动态调整
- [ ] 价格变化：BTC从40k涨到60k时的仓位%变化

---

## 常见问题

**Q: 为什么不直接使用backtesting.py的hedging=True?**
A: Hedging模式允许多头和空头同时存在，但不支持同方向多个独立仓位。

**Q: 能否自己实现Order管理而不用backtesting.py的Position?**
A: 可以，但会失去backtesting.py的很多功能（如equity曲线、trade统计等）。

**Q: mBTC方案是否影响回测结果?**
A: 由于整数取整，会有微小误差（< 0.2%），但对策略表现影响可忽略。

**Q: 其他交易所是否有类似问题?**
A: 真实交易所都支持小数BTC（通常8位精度），这是backtesting.py特有的限制。
