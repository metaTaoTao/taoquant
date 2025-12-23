# GCP 完整部署检查清单

本清单用于确保所有组件（实盘交易、Dashboard、PostgreSQL）正确部署和测试。

## 阶段 1: 初始部署

### 1.1 准备 GCP VM
- [ ] 创建 GCP VM 实例（Ubuntu 22.04 LTS，至少 2 vCPU，4GB RAM）
- [ ] 配置防火墙规则：
  - [ ] 允许 SSH (端口 22)
  - [ ] 允许 Dashboard (端口 8000)
- [ ] 记录 GCP VM 的公网 IP 地址

### 1.2 上传代码到服务器

**选项 A: 从本地上传（推荐）**

**Windows 用户（最简单）：**
```powershell
# 在项目根目录执行 PowerShell 脚本
cd d:\Projects\PythonProjects\taoquant
.\deploy\gcp\upload_to_gcp.ps1 -GCP_IP "YOUR_GCP_IP" -GCP_USER "your_username"
```

**或者使用 WinSCP（图形界面）：**
1. 下载安装 WinSCP: https://winscp.net/
2. 连接到 GCP 服务器（SFTP，端口 22）
3. 拖拽 `deploy/gcp` 文件夹到 `/tmp/taoquant-deploy/`
4. 选择项目文件上传到 `/tmp/taoquant-source/`

**Linux/Mac/WSL 用户：**
```bash
# 在本地项目根目录执行
cd /path/to/taoquant

# 创建临时目录并上传
ssh user@YOUR_GCP_IP "mkdir -p /tmp/taoquant-deploy"
scp -r deploy/gcp/* user@YOUR_GCP_IP:/tmp/taoquant-deploy/

# 上传项目代码（排除不需要的文件）
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='state/*.json' --exclude='state/*.jsonl' \
  --exclude='logs' \
  . user@YOUR_GCP_IP:/tmp/taoquant-source/
```

**详细上传指南请参考：`UPLOAD_GUIDE.md`**

**选项 B: 在服务器上 Git Clone**
```bash
ssh user@YOUR_GCP_IP
cd /opt
sudo git clone YOUR_REPO_URL taoquant
sudo chown -R taoquant:taoquant /opt/taoquant
```

### 1.3 运行部署脚本
```bash
ssh user@YOUR_GCP_IP
cd /tmp/taoquant-deploy  # 或 /opt/taoquant/deploy/gcp
chmod +x deploy.sh test_deployment.sh verify_live.sh
sudo ./deploy.sh all
```

部署脚本会自动：
- [x] 安装系统依赖（Python 3.11, Docker 等）
- [x] 创建 `taoquant` 系统用户
- [x] 设置项目目录 `/opt/taoquant`
- [x] 创建 Python 虚拟环境
- [x] 安装 PostgreSQL (Docker)
- [x] 初始化数据库 schema
- [x] 安装 systemd 服务

### 1.4 运行部署测试
```bash
cd /opt/taoquant/deploy/gcp
sudo bash test_deployment.sh
```

检查所有测试项是否通过：
- [ ] 系统服务已安装
- [ ] PostgreSQL 容器运行中
- [ ] `.env` 文件存在
- [ ] Python 环境正常
- [ ] 关键文件存在
- [ ] 依赖包已安装

## 阶段 2: 配置

### 2.1 配置环境变量
```bash
sudo nano /opt/taoquant/.env
```

**必须配置：**
- [ ] `BITGET_API_KEY` - Bitget API Key
- [ ] `BITGET_API_SECRET` - Bitget API Secret
- [ ] `BITGET_PASSPHRASE` - Bitget Passphrase
- [ ] `TAOQUANT_DB_PASSWORD` - PostgreSQL 密码（如果使用 DB）

**推荐配置：**
- [ ] `TAOQUANT_DB_DSN` - 完整数据库连接字符串
  ```
  TAOQUANT_DB_DSN=postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant
  ```
- [ ] `TAOQUANT_BOT_ID` - Bot 标识符（默认：`BTCUSDT_swap`）
- [ ] `TAOQUANT_KILL_SWITCH` - 设为 `0`（正常模式）

**可选配置：**
- [ ] `TAOQUANT_DASHBOARD_TOKEN` - Dashboard 访问令牌（安全）
- [ ] `BITGET_SUBACCOUNT_UID` - 子账户 UID（如果使用）

### 2.2 配置策略参数
```bash
sudo nano /opt/taoquant/config_bitget_live.json
```

**关键检查项（实盘前）：**
- [ ] `leverage` - 确认杠杆倍数（建议先用小杠杆测试）
- [ ] `initial_cash` - 初始资金（100 USDT）
- [ ] `support` / `resistance` - 网格区间合理
- [ ] `grid_layers_buy` / `grid_layers_sell` - 网格层数

### 2.3 验证 PostgreSQL（如果使用）
```bash
# 检查容器状态
sudo docker ps | grep taoquant-postgres

# 测试连接
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "SELECT COUNT(*) FROM bot_heartbeat;"

# 如果表不存在，手动初始化 schema
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -f /opt/taoquant/persistence/schema.sql
```

## 阶段 3: 启动服务

### 3.1 启动 Dashboard（先启动，便于观察）
```bash
sudo systemctl start taoquant-dashboard
sudo systemctl status taoquant-dashboard
```

**验证：**
- [ ] 服务状态为 `active (running)`
- [ ] 检查日志无错误：`sudo journalctl -u taoquant-dashboard -n 50`
- [ ] 本地访问测试：`curl http://127.0.0.1:8000/api/status`

### 3.2 启动 Runner（实盘交易）
```bash
sudo systemctl start taoquant-runner
sudo systemctl status taoquant-runner
```

**验证：**
- [ ] 服务状态为 `active (running)`
- [ ] 检查日志无错误：`sudo journalctl -u taoquant-runner -n 50`
- [ ] 检查状态文件生成：`ls -lh /opt/taoquant/state/live_status.json`

### 3.3 运行完整验证
```bash
cd /opt/taoquant/deploy/gcp
sudo bash verify_live.sh
```

**检查项：**
- [ ] Runner 服务运行中
- [ ] Dashboard 服务运行中
- [ ] Dashboard API 响应正常
- [ ] 无严重错误日志
- [ ] 状态文件最近更新（< 5 分钟）
- [ ] 数据库连接正常（如果配置）
- [ ] Kill switch 未激活

## 阶段 4: 功能测试

### 4.1 Dashboard 访问测试
```bash
# 从本地浏览器访问（需要防火墙允许）
http://YOUR_GCP_IP:8000
```

**检查：**
- [ ] Dashboard 页面加载
- [ ] 显示实时状态（非 mock data）
- [ ] PnL 数据更新
- [ ] 市场数据正确
- [ ] 订单列表显示
- [ ] 活跃限价单表格显示

### 4.2 数据库功能测试（如果使用）
```bash
# 检查心跳记录
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "
  SELECT 
    bot_id, 
    MAX(ts) as last_heartbeat,
    NOW() - MAX(ts) as age
  FROM bot_heartbeat 
  GROUP BY bot_id;
"

# 检查订单记录
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "
  SELECT COUNT(*) as order_count, 
         MAX(ts) as latest_order
  FROM order_blotter;
"

# 检查持仓快照
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "
  SELECT * FROM exchange_positions_current 
  WHERE bot_id = 'BTCUSDT_swap' 
  ORDER BY ts DESC LIMIT 1;
"
```

### 4.3 交易功能测试（小资金）

**⚠️ 实盘前最后检查：**
- [ ] 确认 `config_bitget_live.json` 中 `leverage` 合理
- [ ] 确认 `initial_cash` 为测试金额（100 USDT）
- [ ] 确认 API 权限正确（交易权限，非只读）
- [ ] 确认合约账户有足够余额

**观察日志：**
```bash
# 实时查看 runner 日志
sudo journalctl -u taoquant-runner -f

# 观察关键事件：
# - 网格初始化
# - 订单下单
# - 订单成交
# - 持仓更新
# - 错误/异常
```

**检查 Dashboard：**
- [ ] 实时 PnL 更新
- [ ] 订单列表实时更新
- [ ] 持仓信息正确
- [ ] 风险指标计算正确

### 4.4 重启恢复测试
```bash
# 停止 runner
sudo systemctl stop taoquant-runner

# 等待 30 秒

# 重新启动
sudo systemctl start taoquant-runner

# 检查日志，确认：
# - 取消旧订单
# - 从交易所同步持仓
# - 重放历史成交
# - 恢复网格运行
```

## 阶段 5: 监控和维护

### 5.1 设置日志监控
```bash
# 查看实时日志
sudo journalctl -u taoquant-runner -f
sudo journalctl -u taoquant-dashboard -f

# 查看文件日志
tail -f /opt/taoquant/logs/bitget_live/live_*.log
```

### 5.2 设置定期检查
```bash
# 创建检查脚本
cat > /opt/taoquant/check_health.sh << 'EOF'
#!/bin/bash
echo "=== TaoQuant Health Check ==="
echo "Runner: $(systemctl is-active taoquant-runner)"
echo "Dashboard: $(systemctl is-active taoquant-dashboard)"
echo "PostgreSQL: $(sudo docker ps --filter name=taoquant-postgres --format '{{.Status}}')"
echo "Last status update: $(stat -c %y /opt/taoquant/state/live_status.json 2>/dev/null || echo 'N/A')"
EOF

chmod +x /opt/taoquant/check_health.sh

# 可以设置 cron 定期执行
# crontab -e
# */5 * * * * /opt/taoquant/check_health.sh >> /opt/taoquant/logs/health.log 2>&1
```

### 5.3 数据库备份（如果使用）
```bash
# 创建备份脚本
cat > /opt/taoquant/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/taoquant/backups"
mkdir -p "$BACKUP_DIR"
export PGPASSWORD="${TAOQUANT_DB_PASSWORD:-taoquant}"
pg_dump -h 127.0.0.1 -p 5432 -U taoquant -d taoquant \
  -F c -f "$BACKUP_DIR/taoquant_$(date +%Y%m%d_%H%M%S).dump"
EOF

chmod +x /opt/taoquant/backup_db.sh

# 设置每日备份（crontab）
# 0 2 * * * /opt/taoquant/backup_db.sh
```

## 故障排查

### 常见问题

**1. Runner 无法启动**
```bash
# 检查环境变量
sudo -u taoquant cat /opt/taoquant/.env

# 手动测试运行
sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && python algorithms/taogrid/run_bitget_live.py --help"

# 查看详细错误
sudo journalctl -u taoquant-runner -n 100 --no-pager
```

**2. Dashboard 无法访问**
```bash
# 检查服务状态
sudo systemctl status taoquant-dashboard

# 检查端口
sudo netstat -tlnp | grep 8000

# 检查防火墙
sudo ufw status
# 或 GCP Console: VPC Network > Firewall Rules
```

**3. 数据库连接失败**
```bash
# 检查容器
sudo docker ps -a | grep taoquant-postgres

# 检查日志
sudo docker logs taoquant-postgres

# 测试连接
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "SELECT 1;"
```

**4. 订单未执行**
```bash
# 检查 kill switch
ls -l /opt/taoquant/state/kill_switch

# 检查 API 权限
# 在 Bitget 后台确认 API Key 有交易权限

# 检查账户余额
# 在 Dashboard 或日志中查看
```

## 完成检查

部署完成后，确认：
- [x] 所有服务正常运行
- [x] Dashboard 可访问并显示实时数据
- [x] 数据库连接正常（如果使用）
- [x] 交易功能测试通过
- [x] 重启恢复测试通过
- [x] 监控和备份已设置

**🎉 部署完成！现在可以开始实盘交易了。**
