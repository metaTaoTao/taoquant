# SSH 密钥设置指南

本指南说明如何设置 SSH 密钥认证，实现免密登录 GCP 服务器。

## 为什么使用 SSH 密钥？

1. **更安全**：比密码认证更安全
2. **免密登录**：不需要每次输入密码
3. **自动化友好**：适合脚本和自动化工具

## 方式 1: 使用 GCP 自动生成的密钥（推荐）

GCP 在创建 VM 时会自动生成密钥对，或者你可以使用 GCP Console 的 SSH 功能。

### 在 GCP Console 中获取密钥

1. 进入 GCP Console
2. 选择你的 VM 实例
3. 点击 "SSH" 按钮（浏览器内 SSH）
4. GCP 会自动处理密钥认证

**注意**：这种方式在浏览器中很方便，但不太适合命令行脚本。

## 方式 2: 生成自己的 SSH 密钥对（推荐用于脚本）

### 步骤 1: 在本地生成密钥对

在 PowerShell 中运行：

```powershell
# 生成密钥对（如果还没有）
ssh-keygen -t rsa -b 4096 -f $env:USERPROFILE\.ssh\gcp_taoquant_key

# 或者使用默认位置
ssh-keygen -t rsa -b 4096
```

**提示**：
- 如果提示输入密码短语（passphrase），可以留空（直接回车）以便自动化
- 密钥文件通常保存在 `C:\Users\YourName\.ssh\` 目录

### 步骤 2: 将公钥添加到 GCP VM

**方法 A: 使用 GCP Console（最简单）**

1. 进入 GCP Console → Compute Engine → VM instances
2. 选择你的 VM 实例
3. 点击 "Edit"（编辑）
4. 展开 "SSH Keys" 部分
5. 点击 "Add Item"
6. 复制你的**公钥**内容（`gcp_taoquant_key.pub` 或 `id_rsa.pub`）
7. 粘贴到 "Enter entire key data" 字段
8. 保存

**方法 B: 使用命令行（如果已有 SSH 访问）**

```powershell
# 读取公钥内容
Get-Content $env:USERPROFILE\.ssh\gcp_taoquant_key.pub

# 复制输出的内容，然后 SSH 到服务器
ssh user@YOUR_GCP_IP

# 在服务器上执行
mkdir -p ~/.ssh
echo "你的公钥内容" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### 步骤 3: 测试密钥认证

```powershell
# 使用密钥文件连接
ssh -i $env:USERPROFILE\.ssh\gcp_taoquant_key user@YOUR_GCP_IP

# 如果成功连接且不需要输入密码，说明配置成功
```

## 方式 3: 使用密码认证（简单但不推荐）

如果你不想设置密钥，可以使用密码认证：

1. 确保 GCP VM 允许密码认证（默认可能不允许）
2. 在脚本运行时手动输入密码

**注意**：密码认证每次都需要手动输入，不适合自动化。

## 在脚本中使用密钥

### 部署脚本

```powershell
# 使用密钥文件
.\deploy\gcp\deploy_interactive.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -SSH_KEY "C:\Users\YourName\.ssh\gcp_taoquant_key"

# 或者交互式输入
.\deploy\gcp\deploy_interactive.ps1
# 脚本会询问是否使用密钥文件
```

### 运维脚本

```powershell
# 使用密钥文件
.\deploy\gcp\server_ops.ps1 -GCP_IP "YOUR_IP" -GCP_USER "ubuntu" -Action status -SSH_KEY "C:\Users\YourName\.ssh\gcp_taoquant_key"
```

## 常见问题

### 1. 权限错误

如果遇到 "Permissions are too open" 错误：

```powershell
# Windows 上设置密钥文件权限
icacls $env:USERPROFILE\.ssh\gcp_taoquant_key /inheritance:r
icacls $env:USERPROFILE\.ssh\gcp_taoquant_key /grant:r "$env:USERNAME:(R)"
```

### 2. 密钥格式问题

确保密钥文件是 OpenSSH 格式（不是 PuTTY 的 .ppk 格式）。

如果使用 PuTTY 生成的密钥，需要转换：

```powershell
# 使用 PuTTYgen 转换 .ppk 到 OpenSSH 格式
# 或使用 WSL 中的 puttygen 命令
```

### 3. 找不到密钥文件

确保使用完整路径：

```powershell
# 正确
-SSH_KEY "C:\Users\YourName\.ssh\gcp_taoquant_key"

# 错误（相对路径可能找不到）
-SSH_KEY "gcp_taoquant_key"
```

## 推荐配置

1. **生成专用密钥**：为 GCP 项目生成专用密钥对
   ```powershell
   ssh-keygen -t rsa -b 4096 -f $env:USERPROFILE\.ssh\gcp_taoquant_key -C "taoquant-gcp"
   ```

2. **添加到 GCP**：通过 GCP Console 添加公钥

3. **测试连接**：
   ```powershell
   ssh -i $env:USERPROFILE\.ssh\gcp_taoquant_key ubuntu@YOUR_GCP_IP
   ```

4. **在脚本中使用**：
   ```powershell
   .\deploy\gcp\deploy_interactive.ps1 -SSH_KEY "$env:USERPROFILE\.ssh\gcp_taoquant_key"
   ```

## 安全建议

1. **保护私钥**：不要分享私钥文件，设置适当的文件权限
2. **使用密码短语**：虽然不方便自动化，但更安全
3. **定期轮换**：定期更换密钥对
4. **限制访问**：在 GCP 防火墙中限制 SSH 访问来源 IP
