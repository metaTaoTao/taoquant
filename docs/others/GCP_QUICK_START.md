# GCP快速开始指南

这是GCP部署的快速参考指南。完整文档请查看 [gcp_deployment_guide.md](gcp_deployment_guide.md)。

## 🎯 5分钟快速部署

### 前置条件

- GCP账户和项目
- Bitget API凭证（API Key, Secret, Passphrase）

### 步骤1: 创建VM

```bash
# 使用gcloud CLI创建VM
gcloud compute instances create taoquant-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --scopes=https://www.googleapis.com/auth/cloud-platform
```

或使用[网页控制台](https://console.cloud.google.com/compute/instances)创建。

### 步骤2: SSH连接

```bash
gcloud compute ssh taoquant-vm --zone=us-central1-a
```

### 步骤3: 运行部署脚本

```bash
# 克隆仓库
git clone https://github.com/metaTaoTao/taoquant.git
cd taoquant

# 运行部署脚本
bash scripts/gcp/setup_gcp.sh
```

### 步骤4: 配置API密钥

**方式A: GCP Secret Manager（推荐）**

```bash
# 创建Secret
echo -n "YOUR_API_KEY" | gcloud secrets create bitget-api-key --data-file=-
echo -n "YOUR_API_SECRET" | gcloud secrets create bitget-api-secret --data-file=-
echo -n "YOUR_PASSPHRASE" | gcloud secrets create bitget-passphrase --data-file=-
```

**方式B: 环境变量文件**

```bash
cat > ~/taoquant/.env << EOF
BITGET_API_KEY=your_key
BITGET_API_SECRET=your_secret
BITGET_PASSPHRASE=your_passphrase
EOF
chmod 600 ~/taoquant/.env
```

### 步骤5: 测试运行

```bash
cd ~/taoquant
source venv/bin/activate
source scripts/gcp/load_secrets.sh  # 如果使用Secret Manager

# Dry Run测试
python algorithms/taogrid/run_bitget_live.py \
    --symbol BTCUSDT \
    --dry-run \
    --config-file config_bitget_live.json
```

### 步骤6: 配置自动启动

```bash
# 创建systemd服务
bash scripts/gcp/create_systemd_service.sh

# 启动服务
bash scripts/gcp/manage.sh start
```

## 🔧 日常管理

### 查看状态和日志

```bash
# 使用管理脚本（推荐）
bash scripts/gcp/manage.sh status    # 查看状态
bash scripts/gcp/manage.sh logs      # 查看实时日志

# 或使用systemctl
sudo systemctl status taoquant.service
sudo journalctl -u taoquant.service -f
```

### 更新代码

```bash
bash scripts/gcp/update_code.sh
# 或
bash scripts/gcp/manage.sh update
```

### 停止/重启服务

```bash
bash scripts/gcp/manage.sh stop
bash scripts/gcp/manage.sh restart
```

## 📋 常用命令速查

| 操作 | 命令 |
|------|------|
| 查看状态 | `bash scripts/gcp/manage.sh status` |
| 查看日志 | `bash scripts/gcp/manage.sh logs` |
| 启动服务 | `bash scripts/gcp/manage.sh start` |
| 停止服务 | `bash scripts/gcp/manage.sh stop` |
| 重启服务 | `bash scripts/gcp/manage.sh restart` |
| Dry Run测试 | `bash scripts/gcp/manage.sh test` |
| 更新代码 | `bash scripts/gcp/manage.sh update` |

## 🔒 安全检查清单

- [ ] API密钥存储在Secret Manager中（而非代码中）
- [ ] 配置文件已调整策略参数
- [ ] 已使用Dry Run模式测试
- [ ] 防火墙规则已配置（限制访问）
- [ ] 日志目录权限正确
- [ ] 服务运行正常（检查日志）

## 📚 相关文档

- **完整部署指南**: [gcp_deployment_guide.md](gcp_deployment_guide.md)
- **脚本说明**: [scripts/gcp/README.md](../scripts/gcp/README.md)
- **Bitget实盘指南**: [algorithms/taogrid/BITGET_LIVE_README.md](../../algorithms/taogrid/BITGET_LIVE_README.md)

## ⚠️ 重要提示

1. **首次部署务必使用Dry Run模式测试**
2. **从小资金开始测试策略**
3. **定期检查日志确保正常运行**
4. **不要将API密钥提交到Git**

## 🆘 遇到问题？

1. 查看日志：`bash scripts/gcp/manage.sh logs-tail`
2. 检查服务状态：`bash scripts/gcp/manage.sh status`
3. 查看完整部署文档获取详细故障排查步骤
4. 提交Issue到GitHub

---

**祝交易顺利！** 🚀

