# Lean 框架快速开始指南

## ✅ 已完成的步骤

1. ✅ Lean CLI 已安装 (版本 1.0.221)
2. ✅ pythonnet 已安装

## ⚠️ 需要完成的步骤

### 选项1: 使用 QuantConnect 账号（推荐）

如果您有 QuantConnect 账号：

1. **获取凭证**:
   - 访问: https://www.quantconnect.com/account
   - 获取 User ID 和 API Token

2. **初始化项目**:
   ```bash
   lean init
   # 输入 User ID 和 API Token
   ```

### 选项2: 手动创建 Lean 目录结构（无需账号）

如果只想在本地运行回测，可以手动创建目录结构：

```bash
# 创建目录结构
mkdir Lean
mkdir Lean\Algorithm.Python
mkdir Lean\Data
mkdir Lean\Launcher

# 创建基本配置文件
```

## 当前状态

- ✅ Lean CLI: 已安装
- ✅ pythonnet: 已安装  
- ⚠️ Lean 目录: 需要初始化
- ⚠️ 算法文件: 需要创建

## 下一步

1. **选择初始化方式**:
   - 如果有 QuantConnect 账号: 运行 `lean init` 并输入凭证
   - 如果只想本地测试: 我可以帮您手动创建目录结构

2. **创建算法文件**: 在 `Lean/Algorithm.Python/` 下创建 `TaoGridAlgorithm.py`

3. **准备数据**: 下载或转换数据到 Lean 格式

4. **运行回测**: `lean backtest "TaoGridAlgorithm"`

## 重要提示

**您当前的 `simple_lean_runner.py` 已经可以运行回测，不需要 Lean 框架！**

Lean 框架的优势：
- 更专业的回测引擎
- 更好的订单管理
- 更精确的滑点模拟
- Web Dashboard

但如果您只是想快速测试策略，`simple_lean_runner.py` 已经足够了。

## 建议

**如果您想继续使用 `simple_lean_runner.py`**:
- 继续修复当前的订单触发逻辑问题
- 不需要设置 Lean 框架

**如果您想使用 Lean 框架**:
- 需要 QuantConnect 账号（免费）
- 或手动创建目录结构
- 需要将算法适配到 Lean 的接口

您想选择哪种方式？

