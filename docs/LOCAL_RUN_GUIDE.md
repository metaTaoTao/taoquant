# 本地运行指南 - TaoQuant实盘交易系统

本指南帮助您在本地Windows/Linux/Mac环境中运行TaoQuant实盘交易策略。

## 📋 前置要求

1. **Python 3.10+**
   ```bash
   python --version  # 检查版本
   ```

2. **Bitget API凭证**
   - API Key
   - API Secret
   - Passphrase

3. **网络连接**
   - 能够访问Bitget API (api.bitget.com)

## 🚀 快速开始

### 步骤1: 安装依赖

```bash
# 克隆仓库（如果还没有）
git clone https://github.com/metaTaoTao/taoquant.git
cd taoquant

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 确保ccxt已安装（Bitget依赖）
pip install "ccxt>=4.5.0"
```

### 步骤2: 配置API密钥

**方式A: 使用环境变量（推荐）**

Windows (PowerShell):
```powershell
$env:BITGET_API_KEY="your_api_key"
$env:BITGET_API_SECRET="your_api_secret"
$env:BITGET_PASSPHRASE="your_passphrase"
```

Windows (CMD):
```cmd
set BITGET_API_KEY=your_api_key
set BITGET_API_SECRET=your_api_secret
set BITGET_PASSPHRASE=your_passphrase
```

Linux/Mac:
```bash
export BITGET_API_KEY="your_api_key"
export BITGET_API_SECRET="your_api_secret"
export BITGET_PASSPHRASE="your_passphrase"
```

**方式B: 使用.env文件**

1. 复制模板文件：
```bash
cp .env.example .env
```

2. 编辑`.env`文件，填入您的API密钥：
```env
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_api_secret
BITGET_PASSPHRASE=your_passphrase
BITGET_SUBACCOUNT_UID=your_subaccount_uid  # 可选
```

**方式C: 命令行参数传递**

直接在运行时传递参数（见步骤3）

### 步骤3: 准备配置文件（可选）

```bash
# 复制默认配置
cp config_bitget_live.json config_live.json

# 根据需要编辑配置文件
# Windows: notepad config_live.json
# Linux/Mac: nano config_live.json 或 vim config_live.json
```

主要配置项：
- `support/resistance`: 支撑/阻力位
- `grid_layers_buy/sell`: 买卖网格层数
- `regime`: 市场状态 (NEUTRAL_RANGE, BULLISH, BEARISH等)
- `leverage`: 杠杆倍数
- `execution.market_type`: 市场类型 (spot 或 swap)

### 步骤4: 测试运行（Dry Run模式）

**强烈建议先使用Dry Run模式测试！**

```bash
# 使用环境变量
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --dry-run \
    --config-file config_live.json

# 或直接传递API密钥
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --dry-run \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE \
    --config-file config_live.json
```

观察日志输出，确认策略逻辑正常。

### 步骤5: 实盘运行

确认Dry Run测试通过后，移除`--dry-run`参数：

```bash
# 使用环境变量（推荐）
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json

# 或使用命令行参数
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --api-key YOUR_API_KEY \
    --api-secret YOUR_API_SECRET \
    --passphrase YOUR_PASSPHRASE \
    --config-file config_live.json
```

## 📝 完整命令参数

```bash
python algorithms/taogrid/run_bitget_live.py --help
```

主要参数：

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `--symbol` | ✅ | 交易对符号 | `BTCUSDT` |
| `--api-key` | ❌* | API密钥（或使用环境变量） | `your_key` |
| `--api-secret` | ❌* | API密钥（或使用环境变量） | `your_secret` |
| `--passphrase` | ❌* | API密钥（或使用环境变量） | `your_passphrase` |
| `--config-file` | ❌ | 策略配置文件 | `config_live.json` |
| `--dry-run` | ❌ | 模拟模式（不下单） | - |
| `--subaccount-uid` | ❌ | 子账户UID | `subaccount_123` |
| `--log-dir` | ❌ | 日志目录 | `logs/bitget_live` |

*API凭证可以通过环境变量提供，也可以通过命令行参数传递

## 💻 不同操作系统的说明

### Windows

**使用PowerShell运行：**

```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 设置环境变量（当前会话）
$env:BITGET_API_KEY="your_key"
$env:BITGET_API_SECRET="your_secret"
$env:BITGET_PASSPHRASE="your_passphrase"

# 运行
python algorithms\taogrid\run_bitget_live.py --symbol BTCUSDT --dry-run
```

**使用CMD运行：**

```cmd
# 激活虚拟环境
venv\Scripts\activate.bat

# 设置环境变量（当前会话）
set BITGET_API_KEY=your_key
set BITGET_API_SECRET=your_secret
set BITGET_PASSPHRASE=your_passphrase

# 运行
python algorithms\taogrid\run_bitget_live.py --symbol BTCUSDT --dry-run
```

**长期运行（使用任务计划程序或作为服务）：**

可以创建批处理文件 `start_taoquant.bat`：

```batch
@echo off
cd /d %~dp0
call venv\Scripts\activate.bat
set BITGET_API_KEY=your_key
set BITGET_API_SECRET=your_secret
set BITGET_PASSPHRASE=your_passphrase
python algorithms\taogrid\run_bitget_live.py --symbol BTCUSDT --config-file config_live.json
pause
```

### Linux/Mac

**终端运行：**

```bash
# 激活虚拟环境
source venv/bin/activate

# 设置环境变量（当前会话）
export BITGET_API_KEY="your_key"
export BITGET_API_SECRET="your_secret"
export BITGET_PASSPHRASE="your_passphrase"

# 运行
python algorithms/taogrid/run_bitget_live.py --symbol BTCUSDT --dry-run
```

**后台运行（使用nohup或screen/tmux）：**

```bash
# 方式1: 使用nohup
nohup python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json \
    > logs/run.log 2>&1 &

# 方式2: 使用screen（推荐）
screen -S taoquant
# 在screen中运行
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json
# 按 Ctrl+A 然后 D 退出screen
# 重新连接: screen -r taoquant

# 方式3: 使用tmux
tmux new -s taoquant
# 在tmux中运行
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json
# 按 Ctrl+B 然后 D 退出tmux
# 重新连接: tmux attach -t taoquant
```

**使用systemd（Linux系统服务）：**

创建 `/etc/systemd/system/taoquant.service`:

```ini
[Unit]
Description=TaoQuant Live Trading Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/taoquant
Environment="PATH=/path/to/taoquant/venv/bin"
Environment="BITGET_API_KEY=your_key"
Environment="BITGET_API_SECRET=your_secret"
Environment="BITGET_PASSPHRASE=your_passphrase"
ExecStart=/path/to/taoquant/venv/bin/python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

然后：
```bash
sudo systemctl daemon-reload
sudo systemctl enable taoquant
sudo systemctl start taoquant
sudo systemctl status taoquant
```

## 📊 查看日志

日志文件保存在 `logs/bitget_live/` 目录下：

```bash
# Windows
dir logs\bitget_live

# Linux/Mac
ls -lh logs/bitget_live/

# 查看最新日志
# Windows PowerShell
Get-Content logs\bitget_live\*.log -Tail 50

# Linux/Mac
tail -f logs/bitget_live/*.log
```

## 🔧 常见问题

### 1. 导入错误 / 模块未找到

```bash
# 确保虚拟环境已激活
# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

### 2. API连接失败

- 检查网络连接：`ping api.bitget.com`
- 验证API密钥是否正确
- 检查防火墙设置
- 确认API权限设置（需要交易权限）

### 3. 权限错误（Windows）

如果遇到脚本执行权限问题：

```powershell
# 以管理员身份运行PowerShell，执行：
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4. 程序意外退出

- 检查日志文件查看错误信息
- 确认API密钥有效
- 检查账户余额
- 验证配置文件格式正确

### 5. 如何停止程序

- **前台运行**: 按 `Ctrl+C`
- **后台运行**: 
  - screen: `screen -r taoquant` 然后 `Ctrl+C`
  - tmux: `tmux attach -t taoquant` 然后 `Ctrl+C`
  - nohup: `ps aux | grep run_bitget_live` 找到PID，然后 `kill PID`

## 🔒 安全建议

1. **不要将API密钥提交到Git**
   - `.env` 文件已在 `.gitignore` 中
   - 使用环境变量或配置文件（不要提交）

2. **使用子账户隔离风险**
   - 为交易bot创建独立的子账户
   - 设置适当的权限和资金限额

3. **定期检查日志**
   - 监控异常交易行为
   - 检查错误和警告信息

4. **从小资金开始测试**
   - 先使用Dry Run模式
   - 实盘从小额资金开始
   - 逐步增加资金量

## 📈 监控建议

1. **定期检查日志**
   ```bash
   # 查看错误
   grep -i error logs/bitget_live/*.log
   
   # 查看订单执行
   grep -i "ORDER_FILLED" logs/bitget_live/*.log
   ```

2. **监控系统资源**
   - CPU和内存使用情况
   - 网络连接状态
   - 磁盘空间（日志文件）

3. **设置告警**（可选）
   - 使用监控工具（如Windows任务管理器、Linux的htop）
   - 配置异常退出告警

## 🎯 下一步

- [ ] 使用Dry Run模式测试策略
- [ ] 调整配置文件参数
- [ ] 设置后台运行（screen/tmux/systemd）
- [ ] 配置日志轮转（避免日志文件过大）
- [ ] 设置监控和告警

## 📚 相关文档

- **Bitget实盘详细说明**: [algorithms/taogrid/BITGET_LIVE_README.md](../algorithms/taogrid/BITGET_LIVE_README.md)
- **策略配置说明**: 查看 `config_bitget_live.json` 中的注释

## 💡 提示

- **首次运行务必使用 `--dry-run` 模式测试**
- **保持终端/窗口打开，以便查看实时日志**
- **定期备份配置文件**
- **记录重要的策略参数调整**

---

**祝交易顺利！** 🚀

