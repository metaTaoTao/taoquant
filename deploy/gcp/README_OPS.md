# 服务器运维指南

本指南说明如何使用自动化脚本进行服务器运维。

## SSH 认证设置

在开始之前，建议先设置 SSH 密钥认证（免密登录）：

1. **生成密钥对**（如果还没有）：
   ```powershell
   ssh-keygen -t rsa -b 4096 -f $env:USERPROFILE\.ssh\gcp_taoquant_key
   ```

2. **将公钥添加到 GCP VM**：
   - 通过 GCP Console → VM → Edit → SSH Keys
   - 或参考 `SSH_SETUP.md` 详细说明

3. **测试连接**：
   ```powershell
   ssh -i $env:USERPROFILE\.ssh\gcp_taoquant_key ubuntu@YOUR_GCP_IP
   ```

**详细说明请参考：`SSH_SETUP.md`**

## 快速开始

### 方式 1: 交互式部署（推荐新手）

运行交互式部署脚本，它会引导你完成所有步骤：

```powershell
cd d:\Projects\PythonProjects\taoquant

# 使用密钥文件（推荐）
.\deploy\gcp\deploy_interactive.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -SSH_KEY "C:\Users\YourName\.ssh\gcp_taoquant_key"

# 或交互式输入（会询问是否使用密钥）
.\deploy\gcp\deploy_interactive.ps1
```

脚本会：
1. 询问 GCP IP 和用户名
2. 测试 SSH 连接
3. 自动上传所有文件
4. 在服务器上执行部署
5. 运行测试验证

### 方式 2: 分步执行

如果你想分步执行，可以使用：

```powershell
# 1. 上传文件
.\deploy\gcp\upload_to_gcp.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu"

# 2. SSH 到服务器手动执行部署
ssh user@YOUR_IP
cd /tmp/taoquant-deploy
sudo ./deploy.sh all
```

## 服务器运维命令

使用 `server_ops.ps1` 进行日常运维：

### 查看服务状态

```powershell
# 使用密钥文件（推荐）
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action status -SSH_KEY "C:\Users\YourName\.ssh\gcp_taoquant_key"

# 使用密码认证（需要手动输入密码）
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action status
```

### 查看日志

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action logs
```

### 重启服务

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action restart
```

### 停止服务

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action stop
```

### 启动服务

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action start
```

### 编辑配置

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action config
```

### 运行测试

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action test
```

### 运行验证

```powershell
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action verify
```

## 完整部署流程示例

```powershell
# 1. 运行交互式部署（首次部署）
.\deploy\gcp\deploy_interactive.ps1

# 2. 配置环境变量（SSH 到服务器或使用 config 命令）
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action config

# 3. 启动服务
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action start

# 4. 验证运行
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action verify

# 5. 查看日志
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action logs
```

## 注意事项

1. **SSH 密码**: 首次连接时可能需要输入 SSH 密码
2. **sudo 权限**: 部署脚本需要 sudo 权限，可能需要输入密码
3. **防火墙**: 确保 GCP 防火墙允许 SSH (22) 和 Dashboard (8000)
4. **网络连接**: 确保本地能访问 GCP 服务器

## 故障排查

如果遇到问题：

1. **SSH 连接失败**
   - 检查 GCP IP 地址是否正确
   - 检查防火墙规则
   - 确认服务器正在运行

2. **上传失败**
   - 检查网络连接
   - 确认 SSH 连接正常
   - 检查磁盘空间

3. **部署失败**
   - 查看服务器日志
   - 检查 sudo 权限
   - 确认系统依赖已安装

## 使用 AI 助手进行运维

你可以直接告诉我：
- "帮我检查服务器状态"
- "帮我查看 Runner 日志"
- "帮我重启服务"
- "帮我更新代码并重新部署"

我会使用这些脚本帮你执行相应的操作。
