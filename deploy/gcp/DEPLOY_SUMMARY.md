# GCP 完整部署总结

本文档汇总了所有部署相关的文件和步骤。

## 📁 部署文件清单

### 核心部署脚本
- `deploy.sh` - 主部署脚本（安装依赖、设置环境、安装服务）
- `test_deployment.sh` - 部署后测试（检查安装是否正确）
- `verify_live.sh` - 运行后验证（检查服务是否正常工作）

### 服务配置
- `taoquant-runner.service` - 交易 Runner 的 systemd 服务文件
- `taoquant-dashboard.service` - Dashboard 的 systemd 服务文件

### 配置文件
- `env.template` - 环境变量模板（需要复制为 `.env` 并填入实际值）

### 文档
- `README.md` - 基础部署指南
- `QUICK_START.md` - 快速部署步骤
- `DEPLOYMENT_CHECKLIST.md` - 完整检查清单（推荐按此执行）
- `DEPLOY_SUMMARY.md` - 本文档

## 🚀 部署流程（3 个阶段）

### 阶段 1: 初始部署（5-10 分钟）

1. **上传代码到服务器**
   ```bash
   # 从本地上传
   scp -r deploy/gcp/* user@GCP_IP:/tmp/taoquant-deploy/
   rsync -av --exclude='.git' --exclude='.venv' . user@GCP_IP:/tmp/taoquant-source/
   ```

2. **执行部署脚本**
   ```bash
   ssh user@GCP_IP
   cd /tmp/taoquant-deploy
   chmod +x deploy.sh test_deployment.sh verify_live.sh
   sudo ./deploy.sh all
   ```

3. **运行部署测试**
   ```bash
   cd /opt/taoquant/deploy/gcp
   sudo bash test_deployment.sh
   ```

### 阶段 2: 配置（5 分钟）

1. **配置环境变量**
   ```bash
   sudo nano /opt/taoquant/.env
   ```
   
   **必须配置：**
   - `BITGET_API_KEY`
   - `BITGET_API_SECRET`
   - `BITGET_PASSPHRASE`
   - `TAOQUANT_DB_DSN`（如果使用数据库）

2. **检查策略配置**
   ```bash
   sudo cat /opt/taoquant/config_bitget_live.json
   ```
   
   **关键检查：**
   - `leverage` - 杠杆倍数（实盘前确认）
   - `initial_cash` - 初始资金（100 USDT）

3. **初始化数据库（如果使用）**
   ```bash
   export PGPASSWORD="YOUR_PASSWORD"
   psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -f /opt/taoquant/persistence/schema.sql
   ```

### 阶段 3: 启动和验证（5 分钟）

1. **启动服务**
   ```bash
   sudo systemctl start taoquant-dashboard
   sudo systemctl start taoquant-runner
   ```

2. **验证运行状态**
   ```bash
   cd /opt/taoquant/deploy/gcp
   sudo bash verify_live.sh
   ```

3. **访问 Dashboard**
   ```
   http://YOUR_GCP_IP:8000
   ```

## ✅ 验证检查点

### 部署后检查（test_deployment.sh）
- [x] 系统服务已安装
- [x] PostgreSQL 容器运行
- [x] `.env` 文件存在
- [x] Python 环境正常
- [x] 关键文件存在
- [x] 依赖包已安装

### 运行后检查（verify_live.sh）
- [x] Runner 服务运行中
- [x] Dashboard 服务运行中
- [x] Dashboard API 响应
- [x] 无严重错误日志
- [x] 状态文件最近更新
- [x] 数据库连接正常（如果配置）
- [x] Kill switch 未激活

### 功能检查（手动）
- [x] Dashboard 显示实时数据
- [x] PnL 数据更新
- [x] 订单列表显示
- [x] 活跃限价单表格显示
- [x] 数据库记录写入（如果使用）

## 🔧 常用维护命令

```bash
# 服务管理
sudo systemctl status taoquant-runner
sudo systemctl restart taoquant-runner
sudo systemctl stop taoquant-runner

# 日志查看
sudo journalctl -u taoquant-runner -f
sudo journalctl -u taoquant-dashboard -f
tail -f /opt/taoquant/logs/bitget_live/live_*.log

# 数据库操作
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant

# 健康检查
cd /opt/taoquant/deploy/gcp
sudo bash verify_live.sh
```

## 🚨 实盘前最后检查

**⚠️ 重要：在启动实盘交易前，确认以下事项：**

1. **API 权限**
   - [ ] Bitget API Key 有**交易权限**（非只读）
   - [ ] API Key 已正确配置在 `.env` 中

2. **账户资金**
   - [ ] 合约账户有足够余额（100 USDT）
   - [ ] 确认账户类型正确（合约账户，非现货）

3. **策略配置**
   - [ ] `leverage` 设置合理（建议先用小杠杆测试）
   - [ ] `initial_cash` = 100.0（你的测试金额）
   - [ ] `support` / `resistance` 区间合理

4. **安全设置**
   - [ ] `TAOQUANT_KILL_SWITCH=0`（正常模式）
   - [ ] 已了解如何激活 kill switch（创建 `/opt/taoquant/state/kill_switch` 文件）

5. **监控就绪**
   - [ ] Dashboard 可访问
   - [ ] 日志监控已设置
   - [ ] 知道如何查看服务状态

## 📊 部署架构

```
GCP VM (Ubuntu 22.04)
├── Systemd Services
│   ├── taoquant-runner.service (交易 Runner)
│   └── taoquant-dashboard.service (Dashboard API)
├── PostgreSQL (Docker)
│   └── taoquant-postgres (容器)
│       └── 数据库: taoquant
│           ├── bot_heartbeat
│           ├── bot_state_current
│           ├── order_blotter
│           └── ...
├── Application
│   └── /opt/taoquant/
│       ├── .env (环境变量)
│       ├── config_bitget_live.json (策略配置)
│       ├── state/ (状态文件)
│       └── logs/ (日志文件)
└── Network
    ├── 22 (SSH)
    └── 8000 (Dashboard HTTP)
```

## 📚 参考文档

- **快速开始**: `QUICK_START.md`
- **详细步骤**: `DEPLOYMENT_CHECKLIST.md`
- **基础指南**: `README.md`
- **GCP 部署文档**: `../../docs/DEPLOY_GCP.md`

## 🆘 获取帮助

如果遇到问题：

1. **查看日志**
   ```bash
   sudo journalctl -u taoquant-runner -n 100 --no-pager
   ```

2. **运行诊断**
   ```bash
   cd /opt/taoquant/deploy/gcp
   sudo bash test_deployment.sh
   sudo bash verify_live.sh
   ```

3. **检查常见问题**
   - 参考 `README.md` 的"故障排查"部分
   - 参考 `DEPLOYMENT_CHECKLIST.md` 的"故障排查"部分

---

**🎉 部署完成后，你的 TaoQuant 网格策略将在 GCP 上实盘运行！**
