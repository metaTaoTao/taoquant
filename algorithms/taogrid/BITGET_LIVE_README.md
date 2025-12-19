# Bitget实盘交易系统使用指南

## 概述

本系统实现了TaoGrid策略在Bitget交易所的实盘交易功能，支持子账户管理和实时策略执行。

## 功能特性

- ✅ Bitget API集成（数据获取和交易执行）
- ✅ 子账户支持
- ✅ 实时策略执行（每分钟处理新K线）
- ✅ Dry run模式（模拟交易，不下单）
- ✅ 完整的日志记录
- ✅ 订单状态跟踪和成交处理

## 安装依赖

```bash
pip install bitget-python
```

或安装所有依赖：

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 基本使用

```bash
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE
```

### 2. Dry Run模式（推荐先测试）

```bash
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --dry-run \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE
```

### 3. 使用子账户

```bash
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE \
    --subaccount-uid SUBACCOUNT_UID
```

### 4. 使用配置文件

创建配置文件 `config.json`:

```json
{
  "strategy": {
    "support": 104000.0,
    "resistance": 126000.0,
    "regime": "NEUTRAL_RANGE",
    "grid_layers_buy": 5,
    "grid_layers_sell": 5,
    "initial_cash": 1000.0
  },
  "execution": {
    "max_fills_per_bar": 6,
    "active_buy_levels": 6,
    "cooldown_minutes": 2
  }
}
```

然后运行：

```bash
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config.json \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE
```

## 子账户管理

### 列出子账户

```python
from execution.engines.bitget_subaccount import BitgetSubaccountManager

manager = BitgetSubaccountManager(
    main_api_key="YOUR_MAIN_API_KEY",
    main_api_secret="YOUR_MAIN_API_SECRET",
    main_passphrase="YOUR_MAIN_PASSPHRASE"
)

subaccounts = manager.list_subaccounts()
for subaccount in subaccounts:
    print(f"UID: {subaccount['uid']}, Name: {subaccount['sub_account_name']}")
```

### 创建子账户

```python
subaccount = manager.create_subaccount(
    subaccount_name="taogrid_test",
    passphrase="secure_passphrase",
    permissions=["spot_trade"]
)
```

### 获取子账户API密钥

```python
api_keys = manager.get_subaccount_api_keys(subaccount_uid="SUBACCOUNT_UID")
```

### 创建子账户API密钥

```python
api_key_info = manager.create_subaccount_apikey(
    subaccount_uid="SUBACCOUNT_UID",
    label="taogrid_live",
    permissions=["read", "spot_trade"]
)
```

## 日志

日志文件保存在 `logs/bitget_live/` 目录下，包含：

- 交易信号记录
- 订单执行记录
- 账户状态更新
- 错误和异常信息

## 注意事项

### 安全

1. **API密钥安全**：
   - 不要将API密钥提交到Git
   - 使用环境变量或配置文件（不要提交到版本控制）
   - 建议使用子账户隔离风险

2. **权限设置**：
   - 实盘交易需要 `spot_trade` 权限
   - 建议只授予必要的权限

### 测试建议

1. **先Dry Run**：使用 `--dry-run` 模式测试策略逻辑
2. **小资金测试**：使用子账户，从小资金（$100-500）开始
3. **监控日志**：密切关注日志输出，确保策略正常运行
4. **逐步增加**：验证无误后，再逐步增加资金量

### 常见问题

1. **API连接失败**：
   - 检查API密钥是否正确
   - 检查网络连接
   - 确认API权限设置

2. **订单执行失败**：
   - 检查账户余额是否充足
   - 检查订单价格是否合理
   - 查看日志了解详细错误信息

3. **数据获取失败**：
   - 检查交易对符号格式（如BTCUSDT）
   - 确认Bitget支持该交易对

## 系统架构

```
run_bitget_live.py (命令行入口)
    ↓
BitgetLiveRunner (实盘运行器)
    ├── BitgetSDKDataSource (数据源)
    ├── BitgetExecutionEngine (交易执行)
    ├── TaoGridLeanAlgorithm (策略逻辑)
    └── LiveLogger (日志系统)
```

## 开发说明

### 文件结构

```
data/sources/
├── bitget_sdk.py          # Bitget数据源

execution/engines/
├── bitget_engine.py       # Bitget交易执行器
└── bitget_subaccount.py   # 子账户管理

algorithms/taogrid/
├── bitget_live_runner.py  # 实盘运行器
├── live_logger.py         # 日志系统
└── run_bitget_live.py     # 命令行接口
```

### 扩展功能

如需添加新功能，可以：

1. **扩展数据源**：修改 `BitgetSDKDataSource` 添加新的数据获取方法
2. **扩展执行器**：修改 `BitgetExecutionEngine` 添加新的交易功能
3. **自定义策略**：修改 `TaoGridLeanConfig` 调整策略参数

## 支持

如有问题或建议，请查看日志文件或联系开发团队。
