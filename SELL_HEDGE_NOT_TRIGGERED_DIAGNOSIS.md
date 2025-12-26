# SELL Hedge未触发诊断分析

**日期**: 2025-12-26
**问题**: BUY limit被fill，但对应的SELL hedge订单没有触发

---

## 正常流程

当BUY订单成交时，应该触发以下流程：

```
1. BUY order filled on exchange
   ↓
2. bitget_live_runner.py 检测到fill
   ↓
3. 调用 algorithm.on_order_filled(order)
   ↓
4. algorithm.py:600-619 处理BUY fill:
   - add_buy_position(level, size, price)
   - remove_pending_order('buy', level)
   - place_pending_order('sell', target_sell_level, target_sell_price)
   ↓
5. grid_manager.py:533-584 添加SELL hedge到pending_limit_orders
   ↓
6. bitget_live_runner.py:2092-2250 order sync:
   - 检查SELL Protection (exchange_long >= sell_qty)
   - 如果通过，调用exchange.create_order()
   ↓
7. SELL hedge订单在exchange上挂单成功
```

---

## 可能导致SELL hedge不触发的原因

### 原因1: SELL Level超出范围 ❌

**代码位置**: `algorithm.py:609-619`

```python
target_sell_level = level  # buy[i] -> sell[i]
if self.grid_manager.sell_levels is not None and target_sell_level < len(self.grid_manager.sell_levels):
    # 生成SELL hedge
    ...
```

**问题**: 如果 `target_sell_level >= len(sell_levels)`，则不会生成SELL hedge

**示例**:
```
grid_layers_buy = 40  (BUY levels: 0-39)
grid_layers_sell = 40 (SELL levels: 0-39)

如果 BUY level 39 成交:
  target_sell_level = 39
  len(sell_levels) = 40
  39 < 40 → ✅ 正常生成

如果 BUY level 40 成交 (因为某种原因超出范围):
  target_sell_level = 40
  len(sell_levels) = 40
  40 < 40 → ❌ 不生成SELL hedge
```

**诊断方法**:
```bash
# 检查日志，查找BUY fill事件
grep "on_order_filled.*BUY" live_*.log

# 查看BUY fill的level和grid配置
grep "grid_layers" live_*.log
```

**解决方案**:
- 如果确实是最高level的BUY成交，这是正常的（边界情况）
- 如果不是边界情况，需要检查为什么BUY level超出范围

---

### 原因2: SELL Protection阻止了订单 🛡️

**代码位置**: `bitget_live_runner.py:2105-2150`

```python
if direction == "sell" and leg == "long":
    portfolio_state = self._get_portfolio_state(current_price=price)
    exchange_long = float(portfolio_state.get("long_holdings", 0.0))

    # SELL order cannot exceed actual holdings
    if exchange_long < qty * 0.95:
        self.logger.log_error(
            f"[SELL_PROTECTION] ❌ CRITICAL: Blocked SELL order! "
            f"SELL qty={qty:.6f} > exchange_long={exchange_long:.6f}"
        )
        continue  # ← 订单被阻止
```

**问题**: 如果exchange_long < SELL qty，订单会被阻止（避免开空仓）

**可能原因**:
1. **Fill Recovery bug遗留问题**: 之前的bug导致ledger和exchange不同步
2. **部分成交**: BUY订单只部分成交，但ledger认为全部成交
3. **Exchange延迟**: 查询position时，BUY成交还未反映在exchange_long中

**诊断方法**:
```bash
# 查找SELL Protection日志
grep "SELL_PROTECTION.*Blocked" live_*.log

# 查找LEDGER_DRIFT警告
grep "LEDGER_DRIFT" live_*.log
```

**典型日志**:
```
[SELL_PROTECTION] ❌ CRITICAL: Blocked SELL order due to insufficient holdings!
SELL qty=0.000795 > exchange_long=0.000000.
This would open SHORT position in LONG-ONLY mode!
level=8, leg=long, price=87800.00
```

**解决方案**:
- 如果看到SELL_PROTECTION日志，说明保护逻辑正常工作
- 检查为什么exchange_long为0（BUY是否真的成交了？）
- 检查FILL_RECOVERY日志，看position verification是否正确

---

### 原因3: SELL订单已存在（重复生成被跳过）

**代码位置**: `grid_manager.py:556-565`

```python
# Check if order already exists
for order in self.pending_limit_orders:
    if (
        order.get("direction") == direction
        and int(order.get("level_index", -999999)) == int(level_index)
        and order.get("leg") == leg
    ):
        if getattr(self.config, "enable_console_log", False):
            print(f"[PENDING_ORDER] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} already exists, skipping")
        return  # Already exists
```

**问题**: 如果SELL hedge订单已经在pending_limit_orders中，不会重复添加

**可能原因**:
1. 之前已经生成过SELL hedge，但还未被sync到exchange
2. 重复的on_order_filled调用

**诊断方法**:
```bash
# 查找"already exists"日志
grep "already exists" live_*.log

# 查找重复的on_order_filled调用
grep "on_order_filled.*BUY.*L[0-9]" live_*.log | sort
```

**解决方案**:
- 这是正常保护逻辑，避免重复订单
- 检查为什么会重复调用on_order_filled

---

### 原因4: Exchange API拒绝订单

**代码位置**: `bitget_live_runner.py:2200-2230`

```python
try:
    result = self.execution_engine.create_order(
        symbol=self.symbol,
        side=side,
        order_type="limit",
        quantity=qty,
        price=price,
        client_order_id=coid,
    )
except Exception as e:
    self.logger.log_error(f"[ORDER_SYNC] Failed to create order: {e}")
    continue
```

**问题**: Exchange可能因为各种原因拒绝订单

**可能原因**:
1. **数量精度问题**: qty=0.0007953，但exchange只支持0.0001精度
2. **最小订单量**: qty太小，低于exchange最小值
3. **保证金不足**: 账户余额不足以支持新订单
4. **API限流**: 超过exchange的订单速率限制
5. **价格精度**: price精度不符合exchange要求

**诊断方法**:
```bash
# 查找create_order失败日志
grep "Failed to create order" live_*.log

# 查找exchange错误
grep -i "error.*bitget\|rejected\|invalid" live_*.log
```

**典型错误**:
```
[ORDER_SYNC] Failed to create order: Order quantity below minimum
[ORDER_SYNC] Failed to create order: Insufficient balance
[ORDER_SYNC] Failed to create order: Invalid precision
```

**解决方案**:
- 检查exchange的最小订单量要求
- 检查账户余额
- 检查数量和价格精度

---

### 原因5: 日志级别过低，SELL hedge实际已生成

**问题**: SELL hedge订单实际已生成，但日志中没有明显的记录

**诊断方法**:
```bash
# 查找所有SELL订单相关日志
grep -i "sell.*hedge\|placed.*sell\|SELL.*L[0-9]" live_*.log

# 查找pending_limit_orders的状态
grep "pending_orders count" live_*.log

# 查找order sync日志
grep "ORDER_SYNC.*SELL" live_*.log
```

**解决方案**:
- 检查exchange上是否实际有SELL挂单
- 检查bot的status API: `http://localhost:5001/api/live-status`

---

## 诊断步骤

### 步骤1: 找到BUY fill事件

```bash
# 查找最近的BUY fill
grep "on_order_filled.*BUY\|Calling on_order_filled.*BUY" live_*.log | tail -20
```

**期望输出**:
```
2025-12-26 10:30:45 [FILL_HEDGE] Calling on_order_filled for BUY L9 (recovery) - will place hedge order
```

**关键信息**:
- 时间戳
- BUY level (L9 = level 8, 0-indexed)
- 是否是recovery fill

### 步骤2: 查看SELL hedge生成日志

```bash
# 在BUY fill后的5秒内查找SELL订单
# 假设BUY fill在10:30:45
grep "2025-12-26 10:30:4[5-9]\|2025-12-26 10:30:5" live_*.log | grep -i "sell.*L[0-9]\|PENDING_ORDER.*SELL"
```

**期望输出**:
```
2025-12-26 10:30:45 [PENDING_ORDER] Placed SELL L9 @ $87,800 (pending_orders count: 15)
```

**如果没有**:
- ❌ SELL hedge未被添加到pending_limit_orders
- 检查原因1（level超出范围）

### 步骤3: 查看SELL Protection检查

```bash
# 查找同一时间的SELL Protection日志
grep "2025-12-26 10:30" live_*.log | grep "SELL_PROTECTION"
```

**如果看到Blocked**:
```
[SELL_PROTECTION] ❌ CRITICAL: Blocked SELL order due to insufficient holdings!
SELL qty=0.000795 > exchange_long=0.000000
```
- ❌ SELL订单被保护逻辑阻止
- 检查原因2（holdings不足）

**如果看到Warning**:
```
[SELL_PROTECTION] ⚠️  SELL order will close most/all position.
SELL qty=0.000795, exchange_long=0.000800 (ratio=99.4%)
```
- ✅ SELL订单通过保护检查
- 继续下一步

### 步骤4: 查看Exchange订单创建

```bash
# 查找create_order调用和结果
grep "2025-12-26 10:30" live_*.log | grep -i "create.*order\|order.*created\|failed.*order"
```

**成功案例**:
```
[ORDER_SYNC] Created SELL limit order: order_id=123456789, coid=SELL_L9_xxx
```

**失败案例**:
```
[ORDER_SYNC] Failed to create order: Order quantity below minimum (0.0007 < 0.001)
```

### 步骤5: 检查Exchange实际挂单

**通过API检查**:
```bash
# 查看当前pending orders
curl -s http://localhost:5001/api/live-status | jq '.pending_orders'
```

**通过Exchange界面**:
- 登录Bitget
- 查看BTCUSDT永续合约的当前挂单
- 确认是否有对应的SELL订单

---

## 快速诊断命令

```bash
# 一键诊断脚本
LOG_FILE="live_20251226_*.log"

echo "=== 1. 最近的BUY fills ==="
grep "on_order_filled.*BUY" $LOG_FILE | tail -5

echo -e "\n=== 2. SELL hedge生成 ==="
grep "Placed.*SELL\|PENDING_ORDER.*SELL" $LOG_FILE | tail -5

echo -e "\n=== 3. SELL Protection检查 ==="
grep "SELL_PROTECTION" $LOG_FILE | tail -5

echo -e "\n=== 4. LEDGER DRIFT警告 ==="
grep "LEDGER_DRIFT" $LOG_FILE | tail -5

echo -e "\n=== 5. Exchange订单错误 ==="
grep "Failed to create order" $LOG_FILE | tail -5

echo -e "\n=== 6. Pending orders统计 ==="
grep "pending_orders count" $LOG_FILE | tail -3
```

---

## 常见问题和解决方案

### 场景A: 看到BUY fill，但完全没有SELL相关日志

**可能原因**: target_sell_level超出范围

**检查**:
```bash
# 查看grid配置
grep "grid_layers_buy\|grid_layers_sell" live_*.log | head -1

# 查看BUY fill的level
grep "on_order_filled.*BUY" live_*.log | tail -1
```

**解决**: 如果是最高level的BUY成交，这是正常的边界情况

---

### 场景B: 看到SELL添加到pending，但被Protection阻止

**可能原因**: Ledger和exchange不同步

**检查**:
```bash
# 查看LEDGER_DRIFT
grep "LEDGER_DRIFT" live_*.log | tail -5

# 查看最近的position verification
grep "FILL_RECOVERY.*exchange_long\|exchange_long=" live_*.log | tail -10
```

**解决**:
1. 检查BUY是否真的在exchange成交了
2. 如果是Fill Recovery误判，可能需要手动同步ledger
3. 重启bot让grid重新初始化

---

### 场景C: SELL订单到达exchange但被拒绝

**可能原因**: 数量/价格精度、余额不足

**检查**:
```bash
# 查看exchange错误
grep -i "failed.*order\|error.*order\|rejected" live_*.log | tail -10
```

**解决**:
1. 检查账户余额（保证金）
2. 检查订单精度配置
3. 检查exchange API文档的最小订单量要求

---

## 下一步行动

请执行以下命令并提供输出：

```bash
# 在服务器上执行
LOG_DIR="/opt/taoquant/logs"
LATEST_LOG=$(ls -t $LOG_DIR/taoquant_runner_*.log | head -1)

echo "=== Latest log file: $LATEST_LOG ==="
echo ""
echo "=== Last 5 BUY fills ==="
grep "on_order_filled.*BUY\|Calling on_order_filled.*BUY" $LATEST_LOG | tail -5
echo ""
echo "=== Corresponding SELL hedges ==="
grep "Placed.*sell.*limit\|PENDING_ORDER.*SELL" $LATEST_LOG | tail -5
echo ""
echo "=== SELL Protection events ==="
grep "SELL_PROTECTION" $LATEST_LOG | tail -5
echo ""
echo "=== LEDGER DRIFT warnings ==="
grep "LEDGER_DRIFT" $LATEST_LOG | tail -5
```

或者，如果可以提供：
1. **最近的BUY fill日志片段**（前后各10行）
2. **当前bot状态**: `curl -s http://localhost:5001/api/live-status | jq`
3. **Exchange上的实际挂单情况**（截图或文本）

这样我可以精确定位问题原因。
