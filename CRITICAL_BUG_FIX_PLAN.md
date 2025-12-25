# 🔴 实盘严重Bug修复方案

**日期**: 2025-12-25
**严重程度**: CRITICAL
**影响**: 错误地开空头头寸，违反long-only策略

---

## 问题总结

### Bug #1: Fill Recovery错误假设订单已成交

**位置**: `bitget_live_runner.py:1395-1425`

**问题**:
```python
if order_status is None:
    # ❌ 直接假设订单已成交！
    self.logger.log_warning("Assuming FILLED and triggering hedge")
    # 触发hedge → 生成SELL订单
```

**触发条件**:
- 订单不在open orders列表中
- `get_order_status()` 返回 `None`

**错误后果**:
1. Bot假设BUY订单已成交
2. 更新内部ledger（增加long_holdings）
3. 触发hedge逻辑（生成SELL订单）
4. **但Exchange实际持仓=0**（订单未成交）
5. SELL订单执行 → 开空头！

### Bug #2: SELL订单缺少持仓数量检查

**位置**: `bitget_live_runner.py:2007-2104`

**问题**:
- 在下SELL订单前没有检查实际long_holdings
- 如果long_holdings < SELL数量 → 会开空头

**错误后果**:
- NEUTRAL_RANGE（long-only）模式下开空头
- 违反策略设计

---

## 修复方案

### 修复#1: Fix Fill Recovery逻辑

**修改文件**: `bitget_live_runner.py`

**位置**: 第1395行附近

**修改前**:
```python
if order_status is None:
    # Assume filled at limit price (错误!)
    fill_price = float(order_info.get("price", 0.0))
    fill_qty = float(order_info.get("quantity", 0.0))

    self.logger.log_warning(
        f"[FILL_RECOVERY] order_id={order_id} not in open orders and "
        f"get_order_status returned None. Assuming FILLED and triggering hedge."
    )

    # Create filled_order event
    filled_order = {...}
    # Trigger hedge
```

**修改后**:
```python
if order_status is None:
    # ✅ 验证exchange实际持仓变化
    expected_side = order_info.get("side", "").lower()
    expected_qty = float(order_info.get("quantity", 0.0))

    # 获取当前exchange持仓
    portfolio_state = self._get_portfolio_state()
    exchange_long = float(portfolio_state.get("long_holdings", 0.0))
    exchange_short = float(portfolio_state.get("short_holdings", 0.0))

    # 获取ledger预期持仓
    ledger_long = float(self._paper_long_holdings) if self.dry_run else self._get_ledger_long()
    ledger_short = float(self._paper_short_holdings) if self.dry_run else self._get_ledger_short()

    # 检查持仓变化是否符合预期
    position_matches = False

    if expected_side == "buy":
        # BUY订单应该增加long持仓
        # 如果exchange持仓 >= ledger + 预期数量(允许5%误差) → 确认成交
        if exchange_long >= (ledger_long + expected_qty * 0.95):
            position_matches = True
            self.logger.log_info(
                f"[FILL_RECOVERY] Confirmed BUY fill via position check. "
                f"exchange_long={exchange_long:.6f}, ledger_long={ledger_long:.6f}, "
                f"expected_qty={expected_qty:.6f}"
            )
    elif expected_side == "sell":
        # SELL订单应该减少long持仓或增加short持仓
        if leg == "long":
            # Long leg SELL: 应该减少long持仓
            if exchange_long <= (ledger_long - expected_qty * 0.95):
                position_matches = True
        elif leg == "short_open":
            # Short open: 应该增加short持仓
            if exchange_short >= (ledger_short + expected_qty * 0.95):
                position_matches = True

    if position_matches:
        # ✅ 持仓变化确认成交
        fill_price = float(order_info.get("price", 0.0))
        fill_qty = expected_qty

        self.logger.log_warning(
            f"[FILL_RECOVERY] order_id={order_id} status=None but position confirms fill. "
            f"Triggering hedge. side={expected_side} level={order_info.get('level')} "
            f"price={fill_price:.2f} qty={fill_qty:.6f}"
        )

        # Create filled_order event to trigger hedge logic
        filled_order = {
            "direction": expected_side,
            "price": fill_price,
            "quantity": fill_qty,
            "level": int(order_info.get("level", -1)),
            "timestamp": datetime.now(timezone.utc),
            "leg": order_info.get("leg"),
        }
        # 继续触发hedge...
    else:
        # ❌ 持仓未变化 → 订单未成交
        self.logger.log_warning(
            f"[FILL_RECOVERY] order_id={order_id} status=None and position unchanged. "
            f"Order NOT filled. Removing from pending_orders without hedge. "
            f"exchange_long={exchange_long:.6f}, ledger_long={ledger_long:.6f}, "
            f"expected_side={expected_side}, expected_qty={expected_qty:.6f}"
        )

        # 移除订单记录，但不触发hedge
        del self.pending_orders[order_id]

        # 记录到数据库
        self._log_order_event(
            client_order_id=order_info.get("client_order_id", ""),
            event_type="EXPIRED_OR_CANCELLED",
            trigger="fill_recovery",
            new_status="expired",
            old_status="unknown",
            exchange_order_id=order_id,
            details={
                "reason": "status_none_position_unchanged",
                "exchange_long": exchange_long,
                "ledger_long": ledger_long,
            },
        )
        continue  # 跳过hedge逻辑
```

### 修复#2: 添加SELL订单持仓保护

**修改文件**: `bitget_live_runner.py`

**位置**: 第2007-2014行之间

**添加代码**:
```python
for o in planned:
    if not allow_place:
        break
    direction = str(o.get("direction"))
    level_index = int(o.get("level_index"))
    price = float(o.get("price"))
    leg = o.get("leg")
    qty = float(o.get("quantity"))
    order_key = self._order_key(direction, level_index, leg)

    # ✅ 新增：SELL订单持仓保护（CRITICAL for long-only strategy）
    if direction == "sell" and leg == "long":
        # 获取当前exchange实际持仓
        portfolio_state = self._get_portfolio_state()
        exchange_long = float(portfolio_state.get("long_holdings", 0.0))

        # SELL订单不能超过实际持仓（防止开空头）
        if exchange_long < qty * 0.95:  # 允许5%误差
            self.logger.log_error(
                f"[SELL_PROTECTION] ❌ CRITICAL: Blocked SELL order due to insufficient holdings! "
                f"SELL qty={qty:.6f} > exchange_long={exchange_long:.6f}. "
                f"This would open SHORT position in LONG-ONLY mode! "
                f"level={level_index}, leg={leg}"
            )

            # 记录严重错误到数据库
            self._log_db_error(
                level="CRITICAL",
                message=f"Blocked SELL order: insufficient holdings (would open short)",
                component="order_sync",
                order_id=None,
                details={
                    "direction": direction,
                    "level": level_index,
                    "leg": leg,
                    "sell_qty": qty,
                    "exchange_long": exchange_long,
                    "deficit": qty - exchange_long,
                },
            )

            # 跳过此订单
            continue

        # 如果SELL数量接近或等于总持仓，警告
        if exchange_long > 0 and qty >= exchange_long * 0.9:
            self.logger.log_warning(
                f"[SELL_PROTECTION] ⚠️  SELL order will close most/all position. "
                f"SELL qty={qty:.6f}, exchange_long={exchange_long:.6f} "
                f"(ratio={qty/exchange_long*100:.1f}%). level={level_index}"
            )

    # 继续原有逻辑...
    if order_key in open_by_order_key:
        ...
```

### 修复#3: 辅助函数（如果不存在）

添加获取ledger持仓的辅助函数（如果还没有）：

```python
def _get_ledger_long(self) -> float:
    """获取内部ledger记录的long持仓"""
    if self.dry_run:
        return float(self._paper_long_holdings)
    else:
        # 从ledger数据库或内存中获取
        # 这里需要根据实际实现调整
        total_long = 0.0
        for level_idx, positions in self.algorithm.grid_manager.buy_positions.items():
            for pos in positions:
                total_long += float(pos.get("size", 0.0))
        return total_long

def _get_ledger_short(self) -> float:
    """获取内部ledger记录的short持仓"""
    if self.dry_run:
        return float(self._paper_short_holdings)
    else:
        total_short = 0.0
        for level_idx, positions in self.algorithm.grid_manager.short_positions.items():
            for pos in positions:
                total_short += float(pos.get("size", 0.0))
        return total_short
```

---

## 测试方案

### 测试场景1: Fill Recovery with No Position Change

**设置**:
1. 启动bot
2. 下BUY订单
3. 手动在交易所取消BUY订单（不要成交）
4. 等待fill recovery检查

**预期**:
- ✅ 检测到订单不存在
- ✅ 检查exchange持仓 = 0（未变化）
- ✅ 不触发hedge
- ✅ 不生成SELL订单
- ✅ 日志显示 "Order NOT filled. Removing without hedge"

### 测试场景2: SELL Order Protection

**设置**:
1. Exchange持仓: long = 0.001 BTC
2. 尝试下SELL订单 qty = 0.002 BTC

**预期**:
- ✅ SELL订单被阻止
- ✅ 日志显示 "Blocked SELL order: insufficient holdings"
- ✅ 不下单
- ✅ 不开空头

### 测试场景3: 正常BUY-SELL流程

**设置**:
1. BUY订单成交（exchange_long增加）
2. fill recovery检测

**预期**:
- ✅ 确认持仓增加
- ✅ 触发hedge
- ✅ 生成SELL订单（数量 <= BUY数量）
- ✅ SELL订单通过持仓检查
- ✅ 正常下单

---

## 部署计划

### 阶段1: 代码审查（现在）

1. ✅ 用户确认修复方案
2. ✅ 深入理解问题根源
3. ✅ 确认修复不会引入新bug

### 阶段2: 实施修复（用户确认后）

1. 修改 `bitget_live_runner.py`
2. 添加测试日志
3. 本地测试（如果可能）

### 阶段3: 部署（谨慎）

1. **先停止实盘bot**
2. **手动平掉当前空头头寸**
3. 备份当前代码
4. 上传修复后的代码
5. **仔细检查配置**
6. 启动bot
7. **密切监控前30分钟**
8. 检查日志确认修复生效

### 阶段4: 监控（持续）

1. 监控LEDGER_DRIFT警告
2. 监控SELL_PROTECTION日志
3. 确认不再开空头
4. 验证SELL订单数量 <= long holdings

---

## 风险评估

### 修复风险: 🟡 MEDIUM

**潜在问题**:
1. 持仓检查逻辑可能有edge cases
2. 5%误差阈值可能需要调整
3. 可能影响正常的订单流程

**缓解措施**:
1. 详细日志记录所有决策
2. 谨慎的条件判断（宁可漏过不可错判）
3. 保留原有的ledger drift检测
4. 部署后密切监控

### 不修复的风险: 🔴 CRITICAL

**后果**:
1. 继续错误开空头
2. 违反策略设计（long-only）
3. 不可预测的盈亏
4. 用户信任损失

---

## 后续改进

### P1（本周）

1. 添加持仓一致性检查（定期对比exchange vs ledger）
2. 添加告警：检测到unexpected short position
3. 完善fill recovery测试覆盖

### P2（下周）

1. 实现更robust的订单状态追踪
2. 添加订单生命周期审计日志
3. 实现position reconciliation机制

---

**修复准备完成**: 等待用户确认后实施
**预计修复时间**: 15-20分钟
**建议停机时间**: 30分钟（包括测试）
