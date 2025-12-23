# 从本地 Windows 上传文件到 GCP 指南

本指南介绍如何从本地 Windows 机器上传代码到 GCP 服务器。

## 什么是 SCP？

**SCP (Secure Copy Protocol)** 是一种基于 SSH 的安全文件传输协议，可以在本地和远程服务器之间复制文件。

## 方法 1: 使用 PowerShell（推荐，Windows 10+）

Windows 10 和 Windows 11 自带 OpenSSH 客户端，可以直接使用 `scp` 命令。

### 1.1 检查是否已安装 SCP

打开 PowerShell，运行：
```powershell
scp
```

如果显示帮助信息，说明已安装。如果没有，需要安装 OpenSSH 客户端：
```powershell
# 以管理员身份运行 PowerShell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

### 1.2 上传部署文件

在本地项目根目录打开 PowerShell，执行：

```powershell
# 设置变量（替换为你的实际值）
$GCP_IP = "YOUR_GCP_IP"  # 例如: "34.123.45.67"
$GCP_USER = "your_username"  # 例如: "taoquant" 或 "ubuntu"

# 创建远程目录
ssh ${GCP_USER}@${GCP_IP} "mkdir -p /tmp/taoquant-deploy"

# 上传部署脚本
scp -r deploy/gcp/* ${GCP_USER}@${GCP_IP}:/tmp/taoquant-deploy/
```

### 1.3 上传项目代码

**选项 A: 使用 SCP（简单但较慢）**
```powershell
# 上传整个项目（排除不需要的文件）
# 注意：SCP 不支持 --exclude，需要先打包或使用其他方法
```

**选项 B: 使用 WinSCP（GUI 工具，推荐）**
见下面的方法 2。

**选项 C: 使用 WSL 或 Git Bash（支持 rsync）**
见下面的方法 3。

## 方法 2: 使用 WinSCP（图形界面，最简单）

WinSCP 是一个免费的 Windows GUI 工具，支持 SCP/SFTP。

### 2.1 下载和安装

1. 访问：https://winscp.net/eng/download.php
2. 下载并安装 WinSCP

### 2.2 连接到 GCP 服务器

1. 打开 WinSCP
2. 点击 "新建会话"
3. 填写信息：
   - **文件协议**: SFTP
   - **主机名**: 你的 GCP IP 地址
   - **端口号**: 22
   - **用户名**: 你的 GCP 用户名
   - **密码**: 你的 GCP 密码（或使用密钥文件）
4. 点击 "登录"

### 2.3 上传文件

1. **上传部署脚本**：
   - 左侧：本地 `d:\Projects\PythonProjects\taoquant\deploy\gcp\` 目录
   - 右侧：远程 `/tmp/taoquant-deploy/` 目录
   - 选中所有文件，拖拽到右侧

2. **上传项目代码**：
   - 左侧：本地 `d:\Projects\PythonProjects\taoquant\` 目录
   - 右侧：远程 `/tmp/taoquant-source/` 目录
   - 手动选择要上传的文件和文件夹（排除 `.git`, `.venv`, `__pycache__`, `state`, `logs`）

## 方法 3: 使用 WSL 或 Git Bash（支持 rsync）

如果你安装了 WSL (Windows Subsystem for Linux) 或 Git Bash，可以使用 `rsync`，它支持排除文件。

### 3.1 使用 WSL

```bash
# 在 WSL 中执行
cd /mnt/d/Projects/PythonProjects/taoquant

# 上传部署脚本
scp -r deploy/gcp/* user@YOUR_GCP_IP:/tmp/taoquant-deploy/

# 上传项目代码（排除不需要的文件）
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='state' --exclude='logs' \
  . user@YOUR_GCP_IP:/tmp/taoquant-source/
```

### 3.2 使用 Git Bash

Git Bash 通常包含 `scp`，但可能没有 `rsync`。可以：
1. 先上传部署脚本
2. 在服务器上使用 Git Clone（如果有 Git 仓库）

## 方法 4: 使用压缩包上传（最简单）

如果网络较慢或文件较多，可以先压缩再上传。

### 4.1 在本地压缩

在 PowerShell 中：
```powershell
cd d:\Projects\PythonProjects\taoquant

# 创建临时目录并复制需要的文件
$tempDir = "C:\temp\taoquant-upload"
New-Item -ItemType Directory -Force -Path $tempDir
Copy-Item -Path . -Destination $tempDir -Recurse -Exclude @('.git', '.venv', '__pycache__', 'state', 'logs')

# 压缩（需要 7-Zip 或使用 PowerShell 5.0+）
Compress-Archive -Path "$tempDir\*" -DestinationPath "C:\temp\taoquant.zip" -Force
```

### 4.2 上传压缩包

```powershell
$GCP_IP = "YOUR_GCP_IP"
$GCP_USER = "your_username"

scp C:\temp\taoquant.zip ${GCP_USER}@${GCP_IP}:/tmp/
```

### 4.3 在服务器上解压

```bash
ssh user@YOUR_GCP_IP
cd /tmp
unzip -q taoquant.zip -d taoquant-source
```

## 完整上传脚本（PowerShell）

创建一个 PowerShell 脚本 `upload_to_gcp.ps1`：

```powershell
# upload_to_gcp.ps1
# 使用方法: .\upload_to_gcp.ps1 -GCP_IP "34.123.45.67" -GCP_USER "ubuntu"

param(
    [Parameter(Mandatory=$true)]
    [string]$GCP_IP,
    
    [Parameter(Mandatory=$true)]
    [string]$GCP_USER
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "上传 TaoQuant 到 GCP" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 SCP 是否可用
try {
    $null = Get-Command scp -ErrorAction Stop
    Write-Host "✅ SCP 已安装" -ForegroundColor Green
} catch {
    Write-Host "❌ SCP 未安装，请安装 OpenSSH 客户端" -ForegroundColor Red
    Write-Host "   以管理员身份运行: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0" -ForegroundColor Yellow
    exit 1
}

# 切换到项目根目录
$projectRoot = "d:\Projects\PythonProjects\taoquant"
if (-not (Test-Path $projectRoot)) {
    Write-Host "❌ 项目目录不存在: $projectRoot" -ForegroundColor Red
    exit 1
}

Set-Location $projectRoot
Write-Host "📁 项目目录: $projectRoot" -ForegroundColor Cyan

# 步骤 1: 上传部署脚本
Write-Host ""
Write-Host "步骤 1: 上传部署脚本..." -ForegroundColor Yellow
ssh ${GCP_USER}@${GCP_IP} "mkdir -p /tmp/taoquant-deploy" 2>&1 | Out-Null

$deployFiles = Get-ChildItem -Path "deploy\gcp" -File
foreach ($file in $deployFiles) {
    Write-Host "  上传: $($file.Name)" -ForegroundColor Gray
    scp "deploy\gcp\$($file.Name)" "${GCP_USER}@${GCP_IP}:/tmp/taoquant-deploy/" 2>&1 | Out-Null
}

Write-Host "✅ 部署脚本上传完成" -ForegroundColor Green

# 步骤 2: 创建临时压缩包
Write-Host ""
Write-Host "步骤 2: 准备项目代码..." -ForegroundColor Yellow

$tempDir = "$env:TEMP\taoquant-upload"
$zipFile = "$env:TEMP\taoquant.zip"

# 清理旧文件
if (Test-Path $tempDir) { Remove-Item -Path $tempDir -Recurse -Force }
if (Test-Path $zipFile) { Remove-Item -Path $zipFile -Force }

# 复制文件（排除不需要的）
Write-Host "  复制文件到临时目录..." -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$excludeDirs = @('.git', '.venv', '__pycache__', 'state', 'logs', '*.pyc')
Get-ChildItem -Path . -Exclude $excludeDirs | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$tempDir\$($_.Name)" -Recurse -Force -ErrorAction SilentlyContinue
}

# 压缩
Write-Host "  压缩文件..." -ForegroundColor Gray
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipFile -Force

$zipSize = (Get-Item $zipFile).Length / 1MB
Write-Host "  压缩包大小: $([math]::Round($zipSize, 2)) MB" -ForegroundColor Gray

# 步骤 3: 上传压缩包
Write-Host ""
Write-Host "步骤 3: 上传项目代码（可能需要几分钟）..." -ForegroundColor Yellow
scp $zipFile "${GCP_USER}@${GCP_IP}:/tmp/taoquant.zip"

Write-Host "✅ 上传完成" -ForegroundColor Green

# 步骤 4: 在服务器上解压
Write-Host ""
Write-Host "步骤 4: 在服务器上解压..." -ForegroundColor Yellow
ssh ${GCP_USER}@${GCP_IP} "cd /tmp && unzip -q -o taoquant.zip -d taoquant-source && rm -f taoquant.zip"

Write-Host "✅ 解压完成" -ForegroundColor Green

# 清理本地临时文件
Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $zipFile -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ 上传完成！" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host "1. SSH 到服务器: ssh ${GCP_USER}@${GCP_IP}" -ForegroundColor White
Write-Host "2. 运行部署脚本: cd /tmp/taoquant-deploy && sudo ./deploy.sh all" -ForegroundColor White
Write-Host ""
```

使用方法：
```powershell
.\upload_to_gcp.ps1 -GCP_IP "34.123.45.67" -GCP_USER "ubuntu"
```

## 推荐方案总结

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **PowerShell SCP** | 系统自带，无需安装 | 不支持排除文件 | 小文件，简单场景 |
| **WinSCP** | 图形界面，直观 | 需要手动选择文件 | 不熟悉命令行的用户 |
| **WSL/Git Bash** | 支持 rsync，功能强大 | 需要额外安装 | 熟悉 Linux 的用户 |
| **压缩包上传** | 速度快，适合大文件 | 需要解压步骤 | 文件较多或网络较慢 |

## 快速开始（最简单）

如果你只想快速开始，推荐使用 **WinSCP**：

1. 下载安装 WinSCP
2. 连接到 GCP 服务器
3. 拖拽 `deploy/gcp` 文件夹到 `/tmp/taoquant-deploy/`
4. 手动选择项目文件上传到 `/tmp/taoquant-source/`

或者使用我提供的 PowerShell 脚本 `upload_to_gcp.ps1`（自动处理压缩和上传）。
