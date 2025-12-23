# GCP 快速部署指南

本指南提供最快速的部署步骤，适用于已经熟悉流程的用户。

## 前置条件

- GCP VM 已创建（Ubuntu 22.04+，2 vCPU，4GB RAM）
- 防火墙已配置（SSH 22，Dashboard 8000）
- Bitget API 凭证已准备

## 一键部署命令

### 1. 从本地上传并部署

```bash
# 在本地项目根目录执行
cd d:/Projects/PythonProjects/taoquant

# 上传部署文件
GCP_IP="YOUR_GCP_IP"
GCP_USER="your_username"

scp -r deploy/gcp/* ${GCP_USER}@${GCP_IP}:/tmp/taoquant-deploy/

# 上传项目代码（使用 rsync，排除不需要的文件）
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='state' --exclude='logs' \
  . ${GCP_USER}@${GCP_IP}:/tmp/taoquant-source/

# SSH 并执行部署
ssh ${GCP_USER}@${GCP_IP} << 'DEPLOY_EOF'
  # 移动文件到目标位置
  sudo mkdir -p /opt/taoquant
  sudo rsync -av /tmp/taoquant-source/ /opt/taoquant/
  sudo chown -R taoquant:taoquant /opt/taoquant 2>/dev/null || \
    (sudo useradd -r -s /bin/bash -d /opt/taoquant -m taoquant && \
     sudo chown -R taoquant:taoquant /opt/taoquant)
  
  # 运行部署脚本
  cd /tmp/taoquant-deploy
  chmod +x deploy.sh test_deployment.sh verify_live.sh
  sudo ./deploy.sh all
  
  # 等待部署完成
  sleep 10
DEPLOY_EOF
```

### 2. 配置环境变量

```bash
ssh ${GCP_USER}@${GCP_IP}

# 编辑 .env 文件
sudo nano /opt/taoquant/.env
```

**必须填入：**
```bash
BITGET_API_KEY=your_actual_api_key
BITGET_API_SECRET=your_actual_secret
BITGET_PASSPHRASE=your_actual_passphrase
TAOQUANT_DB_DSN=postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant
TAOQUANT_BOT_ID=BTCUSDT_swap
TAOQUANT_KILL_SWITCH=0
```

**获取 PostgreSQL 密码（如果部署脚本已创建）：**
```bash
# 查看容器日志中的密码
sudo docker logs taoquant-postgres 2>&1 | grep -i password

# 或者手动设置密码
sudo docker exec -it taoquant-postgres psql -U postgres -c "ALTER USER taoquant WITH PASSWORD 'YOUR_PASSWORD';"
```

### 3. 初始化数据库（如果使用）

```bash
# 如果 schema 未初始化，手动执行
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -f /opt/taoquant/persistence/schema.sql
```

### 4. 检查配置（实盘前重要！）

```bash
# 检查策略配置
sudo cat /opt/taoquant/config_bitget_live.json | grep -E "leverage|initial_cash"

# 确认：
# - leverage 合理（建议先用小杠杆测试）
# - initial_cash = 100.0（你的测试金额）
```

### 5. 启动服务

```bash
# 先启动 Dashboard（便于观察）
sudo systemctl start taoquant-dashboard
sudo systemctl status taoquant-dashboard

# 再启动 Runner（实盘交易）
sudo systemctl start taoquant-runner
sudo systemctl status taoquant-runner
```

### 6. 验证部署

```bash
# 运行验证脚本
cd /opt/taoquant/deploy/gcp
sudo bash verify_live.sh

# 检查日志
sudo journalctl -u taoquant-runner -f
```

### 7. 访问 Dashboard

```bash
# 从本地浏览器访问
http://YOUR_GCP_IP:8000
```

## 常用命令速查

```bash
# 查看服务状态
sudo systemctl status taoquant-runner
sudo systemctl status taoquant-dashboard

# 查看日志
sudo journalctl -u taoquant-runner -f
sudo journalctl -u taoquant-dashboard -f

# 重启服务
sudo systemctl restart taoquant-runner
sudo systemctl restart taoquant-dashboard

# 停止服务
sudo systemctl stop taoquant-runner
sudo systemctl stop taoquant-dashboard

# 检查数据库
export PGPASSWORD="YOUR_PASSWORD"
psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "SELECT COUNT(*) FROM bot_heartbeat;"

# 检查状态文件
ls -lh /opt/taoquant/state/live_status.json
cat /opt/taoquant/state/live_status.json | jq '.system.bot_status'
```

## 故障排查

**服务无法启动：**
```bash
# 查看详细错误
sudo journalctl -u taoquant-runner -n 100 --no-pager

# 手动测试
sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && python algorithms/taogrid/run_bitget_live.py --help"
```

**Dashboard 无法访问：**
```bash
# 检查端口
sudo netstat -tlnp | grep 8000

# 检查防火墙（GCP Console）
# VPC Network > Firewall Rules > 允许 TCP 8000
```

**数据库连接失败：**
```bash
# 检查容器
sudo docker ps | grep taoquant-postgres

# 重启容器
sudo docker restart taoquant-postgres
```

## 下一步

部署完成后，参考 `DEPLOYMENT_CHECKLIST.md` 进行完整的功能测试。
