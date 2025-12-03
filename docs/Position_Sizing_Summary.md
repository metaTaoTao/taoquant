# 仓位管理问题修复总结

## 问题根源

经过测试发现，backtesting.py对加密货币的小数仓位支持存在以下限制：

1. **不支持fractional units** (小数单位)
   - `sell(size=0.1667)` 会被警告或取整为 `sell(size=0)` 或 `sell(size=1)`
   - 官方建议：使用μBTC或satoshi作为整数单位

2. **百分比模式的陷阱**
   - `0 < size < 1` 应该表示权益百分比
   - 但当价格远大于cash时，可能触发内部转换错误
   - 测试显示在某些情况下仍会转为units模式

3. **多仓位累积风险**
   - 即使单个仓位 < 95%，多个虚拟交易累积可能超过100%
   - 一旦size >= 1.0，就会被误判为整数单位

## 已实施的修复

### 修复1: 增加Initial Capital

**文件**: `core/config.py`

```python
@dataclass
class BacktestConfig:
    initial_capital: float = 500000.0  # 从200,000增加到500,000
```

**效果**: 降低单个仓位占权益的百分比，减少超过95%的风险

---

### 修复2: _sync_position 安全检查

**文件**: `strategies/sr_short_4h_resistance.py`

添加了5重安全检查：

1. **Cap at 95%**: 任何仓位不得超过权益的95%
2. **Minimum threshold**: 低于0.1%的订单被忽略
3. **Range validation**: 确保size_pct在(0, 1)范围内
4. **Unit/percentage detection**: 检测并处理单位模式混淆
5. **Incremental safety**: 增加仓位时检查是否会超过上限

**示例代码**:
```python
MAX_POSITION_PCT = 0.95
MIN_POSITION_PCT = 0.001

if target_size_pct >= MAX_POSITION_PCT:
    print(f"[WARNING] Position size {target_size_pct:.2%} exceeds maximum...")
    target_size_pct = MAX_POSITION_PCT
```

---

## 当前状态

### ✅ 已解决的问题

1. **单个大仓位**: 会被cap在95%，不会超过1.0
2. **小仓位忽略**: 低于0.1%的订单被过滤，避免被backtesting.py忽略
3. **Equity波动**: 即使equity下降，百分比也不会超过95%
4. **日志告警**: 任何异常情况都会打印警告信息

### ⚠️ 仍存在的局限

1. **精度损失**: 由于cap在95%，极端情况下仓位可能小于预期
2. **Units模式风险**: 测试显示backtesting.py在某些情况下仍会转换为units模式
3. **实际交易差异**: 真实交易所支持8位小数BTC，回测可能不完全一致

---

## 推荐使用方式

### 日常回测（当前配置）

```python
# scripts/run_backtest.py 或自定义脚本

run_config = {
    "symbol": "BTCUSDT",
    "timeframe": "15m",
    "strategy": "sr_short_4h_resistance",
    "lookback_days": 30,
    "strategy_params": {
        "risk_per_trade_pct": 0.5,  # 每笔0.5%风险
        "max_positions": 5,          # 最多5个仓位
        # ...
    }
}
```

**预期表现**:
- 单笔仓位 ≈ 2-5% of equity (取决于止损距离)
- 5个仓位累积 ≈ 10-25% of equity
- 远低于95%上限，安全运行

---

### 生产环境使用

如果需要更高精度和真实模拟，建议：

1. **使用实盘模拟API**（如Binance Testnet）代替backtesting.py
2. **记录虚拟交易数据**，独立计算P&L，仅用backtesting.py绘图
3. **考虑实施长期方案**（mBTC单位转换，见下文）

---

## 长期优化方案

### 方案A: mBTC单位转换（推荐）

将所有数据转换为mBTC单位，使仓位成为整数：

**优点**:
- ✅ 彻底解决小数问题
- ✅ 0.1667 BTC → 167 mBTC (整数)
- ✅ 精度误差 < 0.2%

**缺点**:
- 需要修改数据处理流程
- 价格显示不直观（50 vs 50,000）

**实施**: 参见 `docs/Position_Sizing_Fix.md` 的详细步骤

---

### 方案B: 自定义回测引擎

完全绕过backtesting.py的限制：

```python
class CustomBacktestEngine:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.positions = []  # List of {entry, size_btc, ...}

    def sell(self, size_btc):
        """Accept fractional BTC directly"""
        self.positions.append({
            'size': size_btc,  # Exact decimal
            'entry_price': current_price,
            # ...
        })
```

**优点**:
- ✅ 完全控制，无限制
- ✅ 支持任意精度

**缺点**:
- 需要重新实现所有功能（equity曲线、统计、绘图）
- 开发工作量大

---

## 测试检查清单

在运行实际回测前，请确认：

- [ ] `core/config.py` 中 `initial_capital = 500000.0`
- [ ] 策略的`_sync_position`包含安全检查
- [ ] 运行测试脚本验证无size >= 1.0错误
- [ ] 检查回测输出中是否有WARNING日志
- [ ] 对比修改前后的回测结果，确保策略逻辑未改变

---

## 常见警告信息

运行回测时可能看到以下日志（均为正常）：

```
[WARNING] Position size 96.50% exceeds maximum 95.00%. Capping at 95.00%.
```
→ 触发了95%保护，仓位被限制

```
[WARNING] Position size 0.08% below minimum 0.10%. Skipping order.
```
→ 仓位太小，被过滤

```
[WARNING] Position size 1.23 is in units (>= 1.0). Converting to percentage.
```
→ 检测到units模式，正在尝试恢复（但这说明有bug）

---

## 获取帮助

如果遇到问题：

1. 查看回测日志中的WARNING信息
2. 检查 `backtest/results/trades.csv` 中的实际成交
3. 对比Position size是否符合预期
4. 参考 `docs/Position_Sizing_Fix.md` 获取详细方案

---

## 相关文件

- `core/config.py` - Initial capital配置
- `strategies/sr_short_4h_resistance.py` - 主策略文件（Line 755-848）
- `strategies/sr_short_4h_resistance_fixed.py` - Satoshi版本（备选）
- `docs/Position_Sizing_Fix.md` - 详细技术文档
- `tests/test_position_fix.py` - 测试脚本

---

## 更新日志

**2025-12-03**:
- 增加initial_capital到500,000
- 添加`_sync_position`安全检查
- 创建详细文档和测试脚本
