# GCP部署指南 - TaoQuant实盘交易系统

本指南将帮助您在Google Cloud Platform (GCP)上部署TaoQuant实盘交易策略。

## 📋 前置要求

1. **GCP账户**
   - 已激活的Google Cloud账户
   - 已创建或选择GCP项目
   - 已安装并配置gcloud CLI（可选，也可使用网页控制台）

2. **Bitget API凭证**
   - API Key
   - API Secret
   - Passphrase

3. **GitHub访问**
   - 代码仓库：https://github.com/metaTaoTao/taoquant

## 🚀 部署步骤

### 步骤1: 创建GCP项目（如未创建）

```bash
# 使用gcloud CLI
gcloud projects create taoquant-live --name="TaoQuant Live Trading"

# 设置默认项目
gcloud config set project taoquant-live

# 或者使用网页控制台：https://console.cloud.google.com/
```

### 步骤2: 启用必要的API

```bash
# 启用Compute Engine API
gcloud services enable compute.googleapis.com

# 启用Secret Manager API（用于安全存储API密钥）
gcloud services enable secretmanager.googleapis.com
```

### 步骤3: 配置Secret Manager（推荐方式）

使用GCP Secret Manager安全存储API凭证：

```bash
# 创建Secret存储API密钥
echo -n "YOUR_BITGET_API_KEY" | gcloud secrets create bitget-api-key --data-file=-

echo -n "YOUR_BITGET_API_SECRET" | gcloud secrets create bitget-api-secret --data-file=-

echo -n "YOUR_BITGET_PASSPHRASE" | gcloud secrets create bitget-passphrase --data-file=-

# 如果使用子账户
echo -n "YOUR_SUBACCOUNT_UID" | gcloud secrets create bitget-subaccount-uid --data-file=-
```

**重要**：如果使用网页控制台：
1. 进入 [Secret Manager](https://console.cloud.google.com/security/secret-manager)
2. 点击"创建密钥"
3. 输入密钥名称（如`bitget-api-key`）
4. 输入密钥值
5. 点击"创建密钥"

### 步骤4: 创建VM实例

#### 方式A: 使用gcloud CLI

```bash
# 创建VM实例（Ubuntu 22.04 LTS）
gcloud compute instances create taoquant-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --boot-disk-type=pd-standard \
    --tags=http-server,https-server \
    --scopes=https://www.googleapis.com/auth/cloud-platform
```

#### 方式B: 使用网页控制台

1. 进入 [Compute Engine](https://console.cloud.google.com/compute/instances)
2. 点击"创建实例"
3. 配置：
   - **名称**: `taoquant-vm`
   - **区域**: 选择最近的区域（如`us-central1-a`）
   - **机器类型**: `e2-medium` (2 vCPU, 4 GB内存)
   - **启动磁盘**: Ubuntu 22.04 LTS
   - **磁盘大小**: 20 GB
   - **访问权限**: 允许"允许对Cloud API的完整访问权限"
4. 点击"创建"

### 步骤5: SSH连接到VM

```bash
# 使用gcloud CLI
gcloud compute ssh taoquant-vm --zone=us-central1-a

# 或使用网页控制台：点击实例名称 -> "SSH"按钮
```

### 步骤6: 在VM上安装依赖

连接到VM后，运行以下命令：

```bash
# 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 安装Python 3.10+和pip
sudo apt-get install -y python3 python3-pip python3-venv git curl

# 安装Google Cloud SDK（用于访问Secret Manager）
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# 初始化gcloud（使用您的GCP项目）
gcloud init
```

### 步骤7: 克隆代码仓库

```bash
# 创建工作目录
mkdir -p ~/taoquant
cd ~/taoquant

# 克隆仓库
git clone https://github.com/metaTaoTao/taoquant.git .

# 或使用SSH（如果您已配置SSH密钥）
# git clone git@github.com:metaTaoTao/taoquant.git .
```

### 步骤8: 设置Python虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 确保安装了ccxt（Bitget依赖）
pip install ccxt>=4.5.0
```

### 步骤9: 配置API凭证

有两种方式配置API凭证：

#### 方式A: 使用环境变量文件（推荐用于测试）

```bash
# 创建环境变量文件
cat > ~/taoquant/.env << EOF
BITGET_API_KEY=your_api_key_here
BITGET_API_SECRET=your_api_secret_here
BITGET_PASSPHRASE=your_passphrase_here
BITGET_SUBACCOUNT_UID=your_subaccount_uid_here  # 可选
EOF

# 设置权限（仅所有者可读）
chmod 600 ~/taoquant/.env
```

#### 方式B: 使用GCP Secret Manager（推荐用于生产）

创建脚本来从Secret Manager读取凭证：

```bash
cat > ~/taoquant/scripts/load_secrets.sh << 'EOF'
#!/bin/bash
# 从GCP Secret Manager加载密钥

export BITGET_API_KEY=$(gcloud secrets versions access latest --secret="bitget-api-key")
export BITGET_API_SECRET=$(gcloud secrets versions access latest --secret="bitget-api-secret")
export BITGET_PASSPHRASE=$(gcloud secrets versions access latest --secret="bitget-passphrase")

# 可选：子账户UID
if gcloud secrets describe bitget-subaccount-uid &>/dev/null; then
    export BITGET_SUBACCOUNT_UID=$(gcloud secrets versions access latest --secret="bitget-subaccount-uid")
fi
EOF

chmod +x ~/taoquant/scripts/load_secrets.sh
```

### 步骤10: 创建配置文件（可选）

复制并编辑配置文件：

```bash
cd ~/taoquant
cp config_bitget_live.json config_live.json

# 编辑配置文件（使用nano或vim）
nano config_live.json
```

根据您的策略需求调整参数（支撑位、阻力位、网格层数等）。

### 步骤11: 测试运行（Dry Run模式）

```bash
cd ~/taoquant
source venv/bin/activate

# 如果使用Secret Manager加载凭证
source scripts/load_secrets.sh

# 运行Dry Run测试（不实际下单）
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --dry-run \
    --config-file config_live.json
```

观察日志输出，确保一切正常。

### 步骤12: 配置systemd服务（自动启动和运行）

创建systemd服务文件以实现自动启动和后台运行：

```bash
sudo nano /etc/systemd/system/taoquant.service
```

内容如下：

```ini
[Unit]
Description=TaoQuant Live Trading Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/taoquant
Environment="PATH=/home/$USER/taoquant/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/home/$USER/taoquant/scripts/load_secrets.sh
ExecStart=/home/$USER/taoquant/venv/bin/python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json \
    --log-dir logs/bitget_live
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**注意**：将`$USER`替换为您的实际用户名，或使用绝对路径。

如果使用环境变量文件而非Secret Manager：

```ini
[Unit]
Description=TaoQuant Live Trading Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/taoquant
Environment="PATH=/home/$USER/taoquant/venv/bin"
EnvironmentFile=/home/$USER/taoquant/.env
ExecStart=/home/$USER/taoquant/venv/bin/python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --config-file config_live.json \
    --log-dir logs/bitget_live
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable taoquant.service

# 启动服务
sudo systemctl start taoquant.service

# 检查服务状态
sudo systemctl status taoquant.service

# 查看日志
sudo journalctl -u taoquant.service -f
```

### 步骤13: 配置日志轮转（可选但推荐）

创建logrotate配置以管理日志文件：

```bash
sudo nano /etc/logrotate.d/taoquant
```

内容：

```
/home/USER/taoquant/logs/bitget_live/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 USER USER
}
```

替换`USER`为您的用户名。

## 🔧 管理命令

### 查看服务状态

```bash
sudo systemctl status taoquant.service
```

### 查看实时日志

```bash
# systemd日志
sudo journalctl -u taoquant.service -f

# 或直接查看日志文件
tail -f ~/taoquant/logs/bitget_live/*.log
```

### 停止服务

```bash
sudo systemctl stop taoquant.service
```

### 重启服务

```bash
sudo systemctl restart taoquant.service
```

### 禁用自动启动

```bash
sudo systemctl disable taoquant.service
```

### 更新代码

```bash
cd ~/taoquant
source venv/bin/activate
git pull origin master
# 如有新的依赖
pip install -r requirements.txt
sudo systemctl restart taoquant.service
```

## 📊 监控和告警

### 设置Cloud Monitoring告警（可选）

1. 进入 [Cloud Monitoring](https://console.cloud.google.com/monitoring)
2. 创建告警策略
3. 监控指标：
   - VM CPU使用率
   - VM内存使用率
   - 磁盘使用率
   - 网络流量

### 查看VM资源使用

```bash
# CPU和内存
htop

# 磁盘空间
df -h

# 查看进程
ps aux | grep python
```

## 🔒 安全最佳实践

1. **API密钥安全**
   - ✅ 使用GCP Secret Manager存储密钥
   - ✅ 不要将密钥提交到Git
   - ✅ 定期轮换API密钥
   - ✅ 使用最小权限原则设置API权限

2. **VM安全**
   - ✅ 使用防火墙规则限制访问
   - ✅ 定期更新系统包
   - ✅ 禁用不必要的端口
   - ✅ 使用SSH密钥而非密码

3. **网络安全**
   ```bash
   # 删除默认防火墙规则（如果存在）
   gcloud compute firewall-rules delete default-allow-http
   gcloud compute firewall-rules delete default-allow-https
   
   # 只允许SSH访问（从特定IP）
   gcloud compute firewall-rules create allow-ssh \
       --allow tcp:22 \
       --source-ranges YOUR_IP/32 \
       --description "Allow SSH from specific IP"
   ```

## 💰 成本优化

1. **选择合适机器类型**
   - `e2-small`或`e2-medium`通常足够
   - 定期监控资源使用情况

2. **使用抢占式实例（不推荐用于生产）**
   - 成本可降低80%，但可能随时中断

3. **设置预算告警**
   - 在GCP控制台设置预算和告警

## 🐛 故障排查

### 服务无法启动

```bash
# 检查服务状态
sudo systemctl status taoquant.service

# 查看详细错误
sudo journalctl -u taoquant.service -n 50

# 手动运行测试
cd ~/taoquant
source venv/bin/activate
source scripts/load_secrets.sh  # 如果使用Secret Manager
python algorithms/taogrid/run_bitget_live.py --symbol BTCUSDT --dry-run
```

### API连接失败

- 检查API密钥是否正确
- 验证网络连接：`curl -I https://api.bitget.com`
- 检查防火墙规则

### 内存不足

```bash
# 检查内存使用
free -h

# 如果内存不足，考虑升级到更大的机器类型
gcloud compute instances set-machine-type taoquant-vm \
    --machine-type e2-standard-4 \
    --zone us-central1-a
```

### 日志文件过大

- 配置logrotate（见步骤13）
- 定期清理旧日志

## 📝 下一步

- [ ] 配置监控和告警
- [ ] 设置日志聚合（可选：使用Cloud Logging）
- [ ] 定期备份配置文件
- [ ] 设置代码自动更新（使用GitHub Actions或其他CI/CD）

## 📞 支持

如有问题，请查看：
- 项目GitHub Issues: https://github.com/metaTaoTao/taoquant/issues
- Bitget API文档: https://bitgetlimited.github.io/apidoc/zh/swap/
- GCP文档: https://cloud.google.com/docs

---

**祝交易顺利！** 🚀

