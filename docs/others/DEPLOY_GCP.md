# GCP 部署完整指南

> **目标**：将 TaoQuant 网格策略和 Dashboard 部署到 GCP VM，实现 7x24 小时自动运行。

## 📋 部署清单

完整的部署文件位于 `deploy/gcp/` 目录：

- `deploy.sh` - 自动化部署脚本
- `taoquant-runner.service` - Runner systemd 服务文件
- `taoquant-dashboard.service` - Dashboard systemd 服务文件
- `env.template` - 环境变量模板（部署脚本会复制为 `/opt/taoquant/.env`）
- `README.md` - 快速部署说明

## 🚀 部署步骤

### Step 1: 准备 GCP VM

1. **创建 VM 实例**：
   - 推荐配置：Ubuntu 22.04 LTS，2 vCPU，4GB RAM，20GB 磁盘
   - 允许 HTTP/HTTPS 流量（Dashboard 需要）

2. **配置防火墙**：
   - 允许 SSH (22)
   - 允许 Dashboard (8000)

### Step 2: 上传代码到服务器

**选项 A: 使用 Git（推荐）**

```bash
# SSH 到服务器
ssh user@your-gcp-ip

# Clone 项目
cd /opt
sudo git clone https://github.com/your-repo/taoquant.git
sudo chown -R taoquant:taoquant /opt/taoquant
```

**选项 B: 使用 SCP**

```bash
# 在本地项目根目录
tar --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='state/*.json' --exclude='state/*.jsonl' \
    -czf taoquant-deploy.tar.gz .
scp taoquant-deploy.tar.gz user@your-gcp-ip:/tmp/
scp -r deploy/gcp/* user@your-gcp-ip:/tmp/taoquant-deploy/
```

### Step 3: 运行部署脚本

```bash
ssh user@your-gcp-ip
cd /tmp/taoquant-deploy  # 或 /opt/taoquant/deploy/gcp
chmod +x deploy.sh
sudo ./deploy.sh all
```

### Step 4: 配置环境变量

```bash
sudo nano /opt/taoquant/.env
```

填入你的 Bitget API 凭证：

```bash
BITGET_API_KEY=your_actual_api_key
BITGET_API_SECRET=your_actual_secret
BITGET_PASSPHRASE=your_actual_passphrase
BITGET_SUBACCOUNT_UID=  # 可选，如果有子账户
TAOQUANT_DASHBOARD_TOKEN=your_secure_token  # 可选，但强烈推荐
```

同时建议配置 PostgreSQL（同机低成本）：

```bash
# 让 dashboard/runner 优先读写 DB（推荐用 DSN）
TAOQUANT_DB_DSN=postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant

# dashboard 选择读取哪个 bot（格式: <SYMBOL>_<market_type>）
TAOQUANT_BOT_ID=BTCUSDT_swap
```

### Step 4.5: 安装并初始化 PostgreSQL（单机低成本）

推荐用 Docker（简单、易迁移、易备份），并绑定到 127.0.0.1 避免暴露公网：

```bash
sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl enable --now docker

sudo mkdir -p /opt/taoquant/pgdata
sudo docker run -d --name taoquant-postgres \
  -e POSTGRES_DB=taoquant \
  -e POSTGRES_USER=taoquant \
  -e POSTGRES_PASSWORD=YOUR_PASSWORD \
  -p 127.0.0.1:5432:5432 \
  -v /opt/taoquant/pgdata:/var/lib/postgresql/data \
  postgres:16
```

初始化表结构（只需一次）：

```bash
sudo apt-get install -y postgresql-client
psql "postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant" -f /opt/taoquant/persistence/schema.sql
```

### Step 5: 配置策略参数

```bash
sudo nano /opt/taoquant/config_bitget_live.json
```

**实盘前必须检查**：
- `leverage`: 建议先从 50x 降到 3x~5x 做 smoke test
- `initial_cash`: 确认是你能承受的金额
- `max_risk_loss_pct / max_risk_inventory_pct`: 设置合理的硬阈值

### Step 6: 启动服务

```bash
# 启动 Runner（网格策略）
sudo systemctl start taoquant-runner

# 启动 Dashboard
sudo systemctl start taoquant-dashboard

# 检查状态
sudo systemctl status taoquant-runner
sudo systemctl status taoquant-dashboard
```

### Step 7: 验证部署

1. **检查 Runner 日志**：
```bash
sudo journalctl -u taoquant-runner -f
```

应该看到：
- `Strategy initialized successfully`
- `Starting Live Trading Runner`
- `[PORTFOLIO]` 日志正常刷新

2. **检查 Dashboard**：
```bash
curl http://your-gcp-ip:8000/api/status
```

或在浏览器打开：`http://your-gcp-ip:8000`

3. **检查状态文件**：
```bash
sudo -u taoquant cat /opt/taoquant/state/live_status.json | jq '.mode'
# 应该输出: "live"
```

## 🔧 服务管理命令

### 查看状态
```bash
sudo systemctl status taoquant-runner
sudo systemctl status taoquant-dashboard
```

### 查看日志
```bash
# Systemd 日志
sudo journalctl -u taoquant-runner -f
sudo journalctl -u taoquant-dashboard -f

# 文件日志
tail -f /opt/taoquant/logs/bitget_live/live_*.log
```

### 重启服务
```bash
sudo systemctl restart taoquant-runner
sudo systemctl restart taoquant-dashboard
```

### 停止服务
```bash
sudo systemctl stop taoquant-runner
sudo systemctl stop taoquant-dashboard
```

### 禁用自动启动
```bash
sudo systemctl disable taoquant-runner
sudo systemctl disable taoquant-dashboard
```

## 🔒 安全配置

### 1. Dashboard Token（强烈推荐）

在 `.env` 中设置：
```bash
TAOQUANT_DASHBOARD_TOKEN=your_very_secure_random_token
```

然后访问 Dashboard 时需要：
```bash
curl -H "Authorization: Bearer your_very_secure_random_token" \
     http://your-gcp-ip:8000/api/status
```

### 2. 防火墙限制 Dashboard 访问

只允许特定 IP 访问 8000 端口：

```bash
sudo ufw allow from YOUR_IP_ADDRESS to any port 8000
sudo ufw enable
```

### 3. 使用 Nginx 反向代理（可选）

如果需要 HTTPS：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📊 监控建议

### 1. 系统资源监控

```bash
# 安装监控工具
sudo apt-get install htop iotop

# 查看资源使用
htop
```

### 2. 日志轮转

创建 `/etc/logrotate.d/taoquant`：

```
/opt/taoquant/logs/bitget_live/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 taoquant taoquant
}
```

### 2.5 PostgreSQL 备份（最小可用）

建议每天备份一次（文件放到 `/opt/taoquant/backups/`），并保留 7 天：

```bash
sudo mkdir -p /opt/taoquant/backups
sudo chown -R taoquant:taoquant /opt/taoquant/backups

# 备份（自定义密码/DSN）
sudo -u taoquant bash -c '
  export PGPASSWORD=YOUR_PASSWORD
  pg_dump -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -Fc > /opt/taoquant/backups/taoquant_$(date +%Y%m%d_%H%M%S).dump
'
```

恢复示例：

```bash
sudo -u taoquant bash -c '
  export PGPASSWORD=YOUR_PASSWORD
  pg_restore -h 127.0.0.1 -p 5432 -U taoquant -d taoquant --clean /opt/taoquant/backups/<dump_file>.dump
'
```

### 2.6 DB 降级缓冲说明

当 DB 不可用时，runner 会把待写入 payload 缓存在：
- `/opt/taoquant/state/db_outbox.jsonl`

DB 恢复后会自动回放并清空（分批处理）。这确保实盘不断线也不会因为 DB 挂了而中断交易主循环。

### 3. GCP Monitoring 告警（可选）

在 GCP Console 设置：
- CPU 使用率 > 80%
- 内存使用率 > 90%
- 磁盘使用率 > 80%

## 🐛 故障排查

### Runner 无法启动

1. **检查环境变量**：
```bash
sudo -u taoquant cat /opt/taoquant/.env
```

2. **手动测试运行**：
```bash
sudo -u taoquant bash -c "
    cd /opt/taoquant
    source .venv/bin/activate
    python algorithms/taogrid/run_bitget_live.py --help
"
```

3. **检查 Python 依赖**：
```bash
sudo -u taoquant bash -c "
    cd /opt/taoquant
    source .venv/bin/activate
    pip list | grep -E '(pandas|ccxt|fastapi)'
"
```

### Dashboard 无法访问

1. **检查服务状态**：
```bash
sudo systemctl status taoquant-dashboard
```

2. **检查端口占用**：
```bash
sudo netstat -tlnp | grep 8000
```

3. **检查防火墙**：
```bash
sudo ufw status
```

### 策略不执行交易

1. **检查日志**：
```bash
sudo journalctl -u taoquant-runner -n 100
```

2. **检查状态文件**：
```bash
sudo -u taoquant cat /opt/taoquant/state/live_status.json | jq '.risk.grid_enabled'
# 应该是: true
```

3. **检查账户余额**：
```bash
# 查看日志中的 [PORTFOLIO] 行
sudo journalctl -u taoquant-runner | grep PORTFOLIO | tail -5
```

## 🔄 更新部署

当代码更新后：

```bash
# 1. 停止服务
sudo systemctl stop taoquant-runner
sudo systemctl stop taoquant-dashboard

# 2. 更新代码
cd /opt/taoquant
sudo -u taoquant git pull

# 3. 更新依赖（如果需要）
sudo -u taoquant bash -c "
    cd /opt/taoquant
    source .venv/bin/activate
    pip install -r requirements.txt
"

# 4. 重启服务
sudo systemctl start taoquant-runner
sudo systemctl start taoquant-dashboard
```

## 📝 维护检查清单

### 每日检查
- [ ] Dashboard 可访问
- [ ] Runner 服务运行正常
- [ ] 日志无异常错误
- [ ] 风险等级正常（risk_level < 3）

### 每周检查
- [ ] 检查磁盘空间
- [ ] 检查日志文件大小
- [ ] 检查系统资源使用
- [ ] 备份配置文件

### 每月检查
- [ ] 更新代码（如有新版本）
- [ ] 检查 API 凭证有效期
- [ ] 审查交易记录和 PnL
- [ ] 优化策略参数（如需要）

## 🆘 紧急停止

如果需要立即停止交易：

```bash
# 停止 Runner（会取消所有挂单）
sudo systemctl stop taoquant-runner

# 或者手动取消所有订单（如果服务还在运行）
# 通过 Bitget 网页/App 手动取消，或使用 API
```

## 📞 支持

如果遇到问题：
1. 查看日志：`sudo journalctl -u taoquant-runner -n 200`
2. 检查状态文件：`cat /opt/taoquant/state/live_status.json`
3. 查看部署文档：`cat /opt/taoquant/deploy/gcp/README.md`
