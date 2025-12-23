# server_ops.ps1
# 服务器运维助手 - 提供常用的服务器管理命令

param(
    [Parameter(Mandatory=$true)]
    [string]$GCP_IP,
    
    [Parameter(Mandatory=$true)]
    [string]$GCP_USER,
    
    [Parameter(Mandatory=$true)]
    [ValidateSet("status", "logs", "restart", "stop", "start", "config", "test", "verify", "help")]
    [string]$Action,
    
    [string]$SSH_KEY = ""  # SSH 私钥文件路径（可选）
)

function Show-Help {
    Write-Host "TaoQuant 服务器运维助手" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法: .\server_ops.ps1 -GCP_IP <IP> -GCP_USER <USER> -Action <ACTION>" -ForegroundColor White
    Write-Host ""
    Write-Host "可用操作：" -ForegroundColor Yellow
    Write-Host "  status   - 查看服务状态" -ForegroundColor White
    Write-Host "  logs     - 查看实时日志" -ForegroundColor White
    Write-Host "  restart  - 重启所有服务" -ForegroundColor White
    Write-Host "  stop     - 停止所有服务" -ForegroundColor White
    Write-Host "  start    - 启动所有服务" -ForegroundColor White
    Write-Host "  config   - 编辑配置文件" -ForegroundColor White
    Write-Host "  test     - 运行部署测试" -ForegroundColor White
    Write-Host "  verify   - 运行运行验证" -ForegroundColor White
    Write-Host "  help     - 显示帮助信息" -ForegroundColor White
    Write-Host ""
}

# 构建 SSH 命令参数
$sshOptions = "-o StrictHostKeyChecking=no"
if (-not [string]::IsNullOrEmpty($SSH_KEY) -and (Test-Path $SSH_KEY)) {
    $sshOptions += " -i `"$SSH_KEY`""
}

function Invoke-SSHCommand {
    param([string]$Command)
    ssh $sshOptions ${GCP_USER}@${GCP_IP} $Command
}

switch ($Action) {
    "help" {
        Show-Help
    }
    
    "status" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "服务状态检查" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        Write-Host "Runner 服务：" -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl status taoquant-runner --no-pager -l"
        
        Write-Host ""
        Write-Host "Dashboard 服务：" -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl status taoquant-dashboard --no-pager -l"
        
        Write-Host ""
        Write-Host "PostgreSQL 容器：" -ForegroundColor Yellow
        Invoke-SSHCommand "sudo docker ps --filter name=taoquant-postgres"
    }
    
    "logs" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "实时日志（按 Ctrl+C 退出）" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "选择要查看的日志：" -ForegroundColor Yellow
        Write-Host "1. Runner 日志" -ForegroundColor White
        Write-Host "2. Dashboard 日志" -ForegroundColor White
        Write-Host "3. Runner 文件日志" -ForegroundColor White
        
        $choice = Read-Host "请选择 (1-3)"
        
        switch ($choice) {
            "1" {
                Write-Host "查看 Runner 日志（最后 50 行）..." -ForegroundColor Gray
                Invoke-SSHCommand "sudo journalctl -u taoquant-runner -n 50 --no-pager"
                Write-Host ""
                Write-Host "要查看实时日志，运行：" -ForegroundColor Yellow
                Write-Host "ssh ${GCP_USER}@${GCP_IP} 'sudo journalctl -u taoquant-runner -f'" -ForegroundColor Gray
            }
            "2" {
                Write-Host "查看 Dashboard 日志（最后 50 行）..." -ForegroundColor Gray
                Invoke-SSHCommand "sudo journalctl -u taoquant-dashboard -n 50 --no-pager"
                Write-Host ""
                Write-Host "要查看实时日志，运行：" -ForegroundColor Yellow
                Write-Host "ssh ${GCP_USER}@${GCP_IP} 'sudo journalctl -u taoquant-dashboard -f'" -ForegroundColor Gray
            }
            "3" {
                Write-Host "查看 Runner 文件日志..." -ForegroundColor Gray
                Invoke-SSHCommand "tail -n 50 /opt/taoquant/logs/bitget_live/live_*.log 2>/dev/null | tail -50"
            }
        }
    }
    
    "restart" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "重启服务" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        Write-Host "重启 Dashboard..." -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl restart taoquant-dashboard"
        
        Write-Host "重启 Runner..." -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl restart taoquant-runner"
        
        Write-Host ""
        Write-Host "✅ 服务已重启" -ForegroundColor Green
        Write-Host ""
        Write-Host "检查状态：" -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl status taoquant-runner --no-pager -l | head -10"
    }
    
    "stop" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "停止服务" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        $confirm = Read-Host "确认停止所有服务？(Y/N)"
        if ($confirm -eq "Y" -or $confirm -eq "y") {
            Write-Host "停止 Runner..." -ForegroundColor Yellow
            Invoke-SSHCommand "sudo systemctl stop taoquant-runner"
            
            Write-Host "停止 Dashboard..." -ForegroundColor Yellow
            Invoke-SSHCommand "sudo systemctl stop taoquant-dashboard"
            
            Write-Host ""
            Write-Host "✅ 服务已停止" -ForegroundColor Green
        } else {
            Write-Host "已取消" -ForegroundColor Yellow
        }
    }
    
    "start" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "启动服务" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        Write-Host "启动 Dashboard..." -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl start taoquant-dashboard"
        
        Write-Host "启动 Runner..." -ForegroundColor Yellow
        Invoke-SSHCommand "sudo systemctl start taoquant-runner"
        
        Write-Host ""
        Write-Host "✅ 服务已启动" -ForegroundColor Green
        Write-Host ""
        Write-Host "检查状态：" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        Invoke-SSHCommand "sudo systemctl status taoquant-runner --no-pager -l | head -10"
    }
    
    "config" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "配置文件编辑" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "选择要编辑的文件：" -ForegroundColor Yellow
        Write-Host "1. 环境变量 (.env)" -ForegroundColor White
        Write-Host "2. 策略配置 (config_bitget_live.json)" -ForegroundColor White
        
        $choice = Read-Host "请选择 (1-2)"
        
        switch ($choice) {
            "1" {
                Write-Host ""
                Write-Host "编辑 .env 文件..." -ForegroundColor Yellow
                Write-Host "（在服务器上使用 nano 编辑器）" -ForegroundColor Gray
                Write-Host ""
                ssh -t $sshOptions ${GCP_USER}@${GCP_IP} "sudo nano /opt/taoquant/.env"
            }
            "2" {
                Write-Host ""
                Write-Host "编辑策略配置文件..." -ForegroundColor Yellow
                Write-Host "（在服务器上使用 nano 编辑器）" -ForegroundColor Gray
                Write-Host ""
                ssh -t $sshOptions ${GCP_USER}@${GCP_IP} "sudo nano /opt/taoquant/config_bitget_live.json"
            }
        }
    }
    
    "test" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "运行部署测试" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        Invoke-SSHCommand "cd /opt/taoquant/deploy/gcp && sudo bash test_deployment.sh"
    }
    
    "verify" {
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "运行运行验证" -ForegroundColor Cyan
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host ""
        
        Invoke-SSHCommand "cd /opt/taoquant/deploy/gcp && sudo bash verify_live.sh"
    }
}
