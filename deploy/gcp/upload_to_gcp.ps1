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
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $projectRoot  # 从 deploy/gcp 回到项目根目录

if (-not (Test-Path $projectRoot)) {
    Write-Host "❌ 项目目录不存在: $projectRoot" -ForegroundColor Red
    Write-Host "   请确保在项目根目录运行此脚本" -ForegroundColor Yellow
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

# 手动复制需要的文件和目录
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
        Copy-Item -Path $sourcePath -Destination $destPath -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "    ✓ $item" -ForegroundColor DarkGray
    }
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

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 上传完成" -ForegroundColor Green
} else {
    Write-Host "❌ 上传失败，请检查网络连接和服务器地址" -ForegroundColor Red
    exit 1
}

# 步骤 4: 在服务器上解压
Write-Host ""
Write-Host "步骤 4: 在服务器上解压..." -ForegroundColor Yellow
ssh ${GCP_USER}@${GCP_IP} "cd /tmp && unzip -q -o taoquant.zip -d taoquant-source && rm -f taoquant.zip"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 解压完成" -ForegroundColor Green
} else {
    Write-Host "⚠️  解压可能失败，请手动检查" -ForegroundColor Yellow
}

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
Write-Host "2. 运行部署脚本: cd /tmp/taoquant-deploy && chmod +x deploy.sh && sudo ./deploy.sh all" -ForegroundColor White
Write-Host ""
