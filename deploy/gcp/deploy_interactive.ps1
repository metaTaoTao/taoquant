# deploy_interactive.ps1
# 交互式部署脚本 - 自动完成从本地上传到服务器部署的全过程

param(
    [string]$GCP_IP = "",
    [string]$GCP_USER = "",
    [string]$SSH_KEY = ""  # SSH 私钥文件路径（可选，如果使用密钥认证）
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "TaoQuant GCP 完整部署向导" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 步骤 1: 收集信息
if ([string]::IsNullOrEmpty($GCP_IP)) {
    $GCP_IP = Read-Host "请输入 GCP 服务器 IP 地址"
}
if ([string]::IsNullOrEmpty($GCP_USER)) {
    $GCP_USER = Read-Host "请输入 SSH 用户名 (通常是 'ubuntu' 或 'taoquant')"
}
if ([string]::IsNullOrEmpty($SSH_KEY)) {
    $useKey = Read-Host "是否使用 SSH 密钥文件？(Y/N，如果使用密码认证选 N)"
    if ($useKey -eq "Y" -or $useKey -eq "y") {
        $SSH_KEY = Read-Host "请输入 SSH 私钥文件路径 (例如: C:\Users\YourName\.ssh\id_rsa)"
        if (-not (Test-Path $SSH_KEY)) {
            Write-Host "⚠️  密钥文件不存在，将使用密码认证" -ForegroundColor Yellow
            $SSH_KEY = ""
        }
    }
}

Write-Host ""
Write-Host "配置信息：" -ForegroundColor Yellow
Write-Host "  GCP IP: $GCP_IP" -ForegroundColor White
Write-Host "  用户名: $GCP_USER" -ForegroundColor White
if (-not [string]::IsNullOrEmpty($SSH_KEY)) {
    Write-Host "  SSH 密钥: $SSH_KEY" -ForegroundColor White
} else {
    Write-Host "  认证方式: 密码认证（需要手动输入密码）" -ForegroundColor White
}
Write-Host ""

$confirm = Read-Host "确认继续？(Y/N)"
if ($confirm -ne "Y" -and $confirm -ne "y") {
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

# 检查 SCP 是否可用
Write-Host ""
Write-Host "检查环境..." -ForegroundColor Yellow
try {
    $null = Get-Command scp -ErrorAction Stop
    Write-Host "✅ SCP 已安装" -ForegroundColor Green
} catch {
    Write-Host "❌ SCP 未安装" -ForegroundColor Red
    Write-Host "   请以管理员身份运行: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0" -ForegroundColor Yellow
    exit 1
}

try {
    $null = Get-Command ssh -ErrorAction Stop
    Write-Host "✅ SSH 已安装" -ForegroundColor Green
} catch {
    Write-Host "❌ SSH 未安装" -ForegroundColor Red
    Write-Host "   请以管理员身份运行: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0" -ForegroundColor Yellow
    exit 1
}

# 切换到项目根目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

if (-not (Test-Path $projectRoot)) {
    Write-Host "❌ 项目目录不存在: $projectRoot" -ForegroundColor Red
    exit 1
}

Set-Location $projectRoot
Write-Host "📁 项目目录: $projectRoot" -ForegroundColor Cyan

# 构建 SSH 命令参数
$sshOptions = "-o ConnectTimeout=5 -o StrictHostKeyChecking=no"
if (-not [string]::IsNullOrEmpty($SSH_KEY)) {
    $sshOptions += " -i `"$SSH_KEY`""
    $scpOptions = "-o StrictHostKeyChecking=no -i `"$SSH_KEY`""
} else {
    $scpOptions = "-o StrictHostKeyChecking=no"
}

# 步骤 2: 测试 SSH 连接
Write-Host ""
Write-Host "步骤 1: 测试 SSH 连接..." -ForegroundColor Yellow
Write-Host "  正在连接到 $GCP_USER@$GCP_IP..." -ForegroundColor Gray

# 测试连接
$testConnection = ssh $sshOptions ${GCP_USER}@${GCP_IP} "echo 'Connection successful'" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  SSH 连接测试失败，可能需要手动输入密码" -ForegroundColor Yellow
    Write-Host "   请确保：" -ForegroundColor Yellow
    Write-Host "   1. GCP 防火墙允许 SSH (端口 22)" -ForegroundColor White
    Write-Host "   2. 服务器正在运行" -ForegroundColor White
    Write-Host "   3. 用户名和 IP 地址正确" -ForegroundColor White
    Write-Host ""
    $continue = Read-Host "是否继续尝试上传？(Y/N)"
    if ($continue -ne "Y" -and $continue -ne "y") {
        exit 1
    }
} else {
    Write-Host "✅ SSH 连接成功" -ForegroundColor Green
}

# 步骤 3: 上传文件
Write-Host ""
Write-Host "步骤 2: 上传部署文件..." -ForegroundColor Yellow

# 创建远程目录
Write-Host "  创建远程目录..." -ForegroundColor Gray
ssh $sshOptions ${GCP_USER}@${GCP_IP} "mkdir -p /tmp/taoquant-deploy" 2>&1 | Out-Null

# 上传部署脚本
$deployFiles = Get-ChildItem -Path "deploy\gcp" -File
foreach ($file in $deployFiles) {
    Write-Host "  上传: $($file.Name)" -ForegroundColor Gray
    scp $scpOptions "deploy\gcp\$($file.Name)" "${GCP_USER}@${GCP_IP}:/tmp/taoquant-deploy/" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✓ $($file.Name)" -ForegroundColor DarkGreen
    } else {
        Write-Host "    ✗ $($file.Name) 上传失败" -ForegroundColor Red
    }
}

Write-Host "✅ 部署脚本上传完成" -ForegroundColor Green

# 步骤 4: 准备并上传项目代码
Write-Host ""
Write-Host "步骤 3: 准备项目代码..." -ForegroundColor Yellow

$tempDir = "$env:TEMP\taoquant-upload"
$zipFile = "$env:TEMP\taoquant.zip"

# 清理旧文件
if (Test-Path $tempDir) { Remove-Item -Path $tempDir -Recurse -Force }
if (Test-Path $zipFile) { Remove-Item -Path $zipFile -Force }

# 复制文件
Write-Host "  复制文件到临时目录..." -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$itemsToCopy = @(
    "algorithms",
    "analytics",
    "data",
    "dashboard",
    "deploy",
    "docs",
    "execution",
    "notebooks",
    "orchestration",
    "persistence",
    "risk_management",
    "strategies",
    "utils",
    "config_bitget_live.json",
    "requirements.txt",
    "README.md"
)

foreach ($item in $itemsToCopy) {
    $sourcePath = Join-Path $projectRoot $item
    if (Test-Path $sourcePath) {
        $destPath = Join-Path $tempDir $item
        Copy-Item -Path $sourcePath -Destination $destPath -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

# 压缩
Write-Host "  压缩文件..." -ForegroundColor Gray
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipFile -Force

$zipSize = (Get-Item $zipFile).Length / 1MB
Write-Host "  压缩包大小: $([math]::Round($zipSize, 2)) MB" -ForegroundColor Gray

# 上传压缩包
Write-Host ""
Write-Host "步骤 4: 上传项目代码（可能需要几分钟）..." -ForegroundColor Yellow
scp $scpOptions $zipFile "${GCP_USER}@${GCP_IP}:/tmp/taoquant.zip"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 上传完成" -ForegroundColor Green
} else {
    Write-Host "❌ 上传失败" -ForegroundColor Red
    Write-Host "   请检查网络连接和服务器状态" -ForegroundColor Yellow
    exit 1
}

# 步骤 5: 在服务器上解压
Write-Host ""
Write-Host "步骤 5: 在服务器上解压..." -ForegroundColor Yellow
ssh $sshOptions ${GCP_USER}@${GCP_IP} "cd /tmp && unzip -q -o taoquant.zip -d taoquant-source && rm -f taoquant.zip"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 解压完成" -ForegroundColor Green
} else {
    Write-Host "⚠️  解压可能失败，请手动检查" -ForegroundColor Yellow
}

# 清理本地临时文件
Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $zipFile -Force -ErrorAction SilentlyContinue

# 步骤 6: 执行部署脚本
Write-Host ""
Write-Host "步骤 6: 在服务器上执行部署..." -ForegroundColor Yellow
Write-Host "  这可能需要几分钟，请耐心等待..." -ForegroundColor Gray

$deployCommand = @"
cd /tmp/taoquant-deploy
chmod +x deploy.sh test_deployment.sh verify_live.sh
sudo ./deploy.sh all
"@

ssh $sshOptions ${GCP_USER}@${GCP_IP} $deployCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 部署脚本执行完成" -ForegroundColor Green
} else {
    Write-Host "⚠️  部署脚本执行可能有问题，请检查输出" -ForegroundColor Yellow
}

# 步骤 7: 运行测试
Write-Host ""
Write-Host "步骤 7: 运行部署测试..." -ForegroundColor Yellow

$testCommand = @"
cd /opt/taoquant/deploy/gcp
sudo bash test_deployment.sh
"@

ssh $sshOptions ${GCP_USER}@${GCP_IP} $testCommand

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ 部署完成！" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作：" -ForegroundColor Yellow
Write-Host "1. 配置环境变量：" -ForegroundColor White
Write-Host "   ssh ${GCP_USER}@${GCP_IP}" -ForegroundColor Gray
Write-Host "   sudo nano /opt/taoquant/.env" -ForegroundColor Gray
Write-Host ""
Write-Host "2. 配置策略参数：" -ForegroundColor White
Write-Host "   sudo nano /opt/taoquant/config_bitget_live.json" -ForegroundColor Gray
Write-Host ""
Write-Host "3. 启动服务：" -ForegroundColor White
Write-Host "   sudo systemctl start taoquant-dashboard" -ForegroundColor Gray
Write-Host "   sudo systemctl start taoquant-runner" -ForegroundColor Gray
Write-Host ""
Write-Host "4. 访问 Dashboard：" -ForegroundColor White
Write-Host "   http://${GCP_IP}:8000" -ForegroundColor Gray
Write-Host ""
