# TaoQuant GCP Deployment Guide

本指南帮助你将 TaoQuant 网格策略和 Dashboard 部署到 GCP 服务器。

## 前置要求

- GCP VM 实例（推荐：Ubuntu 22.04 LTS，至少 2 vCPU，4GB RAM）
- 已配置防火墙规则（允许 SSH 和 Dashboard 端口 8000）
- Bitget API 凭证（API Key, Secret, Passphrase）

## 快速部署

### 方法 1: 从本地部署（推荐）

1. **上传部署文件到服务器**：

```bash
# 在本地项目根目录
scp -r deploy/gcp/* user@your-gcp-ip:/tmp/taoquant-deploy/
scp -r . user@your-gcp-ip:/tmp/taoquant-source/ --exclude='.git' --exclude='.venv' --exclude='__pycache__'
```

2. **SSH 到服务器并运行部署脚本**：

```bash
ssh user@your-gcp-ip
cd /tmp/taoquant-deploy
chmod +x deploy.sh
sudo ./deploy.sh all
```

3. **配置环境变量**：

```bash
sudo nano /opt/taoquant/.env
# 填入你的 Bitget API 凭证
```

并配置 PostgreSQL（同机低成本）：

```bash
TAOQUANT_DB_DSN=postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant
TAOQUANT_BOT_ID=BTCUSDT_swap
```

4.5 **安装并初始化 PostgreSQL（建议 Docker）**：

```bash
sudo apt-get update && sudo apt-get install -y docker.io postgresql-client
sudo systemctl enable --now docker

sudo mkdir -p /opt/taoquant/pgdata
sudo docker run -d --name taoquant-postgres \
  -e POSTGRES_DB=taoquant \
  -e POSTGRES_USER=taoquant \
  -e POSTGRES_PASSWORD=YOUR_PASSWORD \
  -p 127.0.0.1:5432:5432 \
  -v /opt/taoquant/pgdata:/var/lib/postgresql/data \
  postgres:16

psql \"postgresql://taoquant:YOUR_PASSWORD@127.0.0.1:5432/taoquant\" -f /opt/taoquant/persistence/schema.sql
```

4. **启动服务**：

```bash
sudo systemctl start taoquant-runner
sudo systemctl start taoquant-dashboard
```

### 方法 2: 在服务器上直接 Git Clone

```bash
# SSH 到服务器
ssh user@your-gcp-ip

# Clone 项目
cd /opt
sudo git clone https://github.com/your-repo/taoquant.git
sudo chown -R taoquant:taoquant /opt/taoquant

# 运行部署脚本
cd /opt/taoquant/deploy/gcp
sudo chmod +x deploy.sh
sudo ./deploy.sh all

# 配置环境变量
sudo nano /opt/taoquant/.env

# 启动服务
sudo systemctl start taoquant-runner
sudo systemctl start taoquant-dashboard
```

## 服务管理

### 查看状态

```bash
sudo systemctl status taoquant-runner
sudo systemctl status taoquant-dashboard
```

### 查看日志

```bash
# Runner 日志
sudo journalctl -u taoquant-runner -f

# Dashboard 日志
sudo journalctl -u taoquant-dashboard -f

# 或者查看文件日志
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

## 访问 Dashboard

部署完成后，Dashboard 会在 `http://your-gcp-ip:8000` 运行。

如果设置了 `TAOQUANT_DASHBOARD_TOKEN`，需要在请求头中携带：

```bash
curl -H "Authorization: Bearer your_token" http://your-gcp-ip:8000/api/status
```

## 防火墙配置

确保 GCP 防火墙允许以下端口：

- **22** (SSH)
- **8000** (Dashboard HTTP)

在 GCP Console 中：

1. 进入 **VPC Network > Firewall Rules**
2. 创建规则允许 TCP 8000 端口
3. 应用到你的 VM 实例

## 安全建议

1. **使用防火墙限制 Dashboard 访问**：只允许特定 IP 访问 8000 端口
2. **设置 Dashboard Token**：在 `.env` 中设置 `TAOQUANT_DASHBOARD_TOKEN`
3. **定期更新代码**：使用 `git pull` 更新后重启服务
4. **监控日志**：定期检查日志是否有异常
5. **备份配置**：定期备份 `/opt/taoquant/config_bitget_live.json` 和 `.env`

## 故障排查

### Runner 无法启动

1. 检查环境变量：
```bash
sudo -u taoquant cat /opt/taoquant/.env
```

2. 检查 Python 环境：
```bash
sudo -u taoquant /opt/taoquant/.venv/bin/python --version
```

3. 手动测试运行：
```bash
sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && python algorithms/taogrid/run_bitget_live.py --help"
```

### Dashboard 无法访问

1. 检查服务状态：
```bash
sudo systemctl status taoquant-dashboard
```

2. 检查端口占用：
```bash
sudo netstat -tlnp | grep 8000
```

3. 检查防火墙：
```bash
sudo ufw status
```

## 更新部署

当代码更新后：

```bash
# 停止服务
sudo systemctl stop taoquant-runner
sudo systemctl stop taoquant-dashboard

# 更新代码（如果使用 Git）
cd /opt/taoquant
sudo -u taoquant git pull

# 更新依赖（如果需要）
sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && pip install -r requirements.txt"

# 重启服务
sudo systemctl start taoquant-runner
sudo systemctl start taoquant-dashboard
```

## 完整测试流程

部署完成后，运行测试脚本验证所有组件：

```bash
# 1. 部署后测试（检查安装）
cd /opt/taoquant/deploy/gcp
sudo bash test_deployment.sh

# 2. 启动服务后验证（检查运行状态）
sudo bash verify_live.sh
```

详细测试步骤请参考：`DEPLOYMENT_CHECKLIST.md`

## 监控建议

1. **设置日志轮转**：防止日志文件过大
2. **监控系统资源**：使用 `htop` 或 `top` 监控 CPU/内存
3. **设置告警**：如果使用 GCP Monitoring，可以设置告警规则
4. **定期健康检查**：使用 `verify_live.sh` 定期检查服务状态
