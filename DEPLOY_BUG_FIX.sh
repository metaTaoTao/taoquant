#!/bin/bash
# 部署Critical Bug修复脚本
# 执行日期: 2025-12-25
# 修复内容: Fill Recovery逻辑 + SELL订单保护

set -e  # 遇到错误立即退出

echo "========================================"
echo "🔧 TaoGrid Critical Bug Fix Deployment"
echo "========================================"
echo ""
echo "修复内容:"
echo "  1. Fill Recovery逻辑 - 验证持仓变化"
echo "  2. SELL订单保护 - 防止开空头"
echo ""
echo "⚠️  警告: 这是实盘系统，请仔细检查！"
echo ""

# 服务器信息
SERVER="liandongtrading@34.158.55.6"
REMOTE_DIR="/opt/taoquant"
LOCAL_FILE="algorithms/taogrid/bitget_live_runner.py"

# Step 1: 备份当前版本
echo "Step 1: 备份当前运行的代码..."
ssh $SERVER "sudo cp $REMOTE_DIR/$LOCAL_FILE $REMOTE_DIR/${LOCAL_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
echo "✅ 备份完成"
echo ""

# Step 2: 上传新代码
echo "Step 2: 上传修复后的代码..."
scp "$LOCAL_FILE" "$SERVER:/tmp/bitget_live_runner.py"
echo "✅ 上传完成"
echo ""

# Step 3: 移动到正确位置
echo "Step 3: 部署新代码..."
ssh $SERVER "sudo cp /tmp/bitget_live_runner.py $REMOTE_DIR/$LOCAL_FILE"
ssh $SERVER "sudo chown taoquant:taoquant $REMOTE_DIR/$LOCAL_FILE"
echo "✅ 部署完成"
echo ""

# Step 4: 重启服务
echo "Step 4: 重启交易Bot..."
echo "⚠️  即将重启服务，按Ctrl+C取消，或按Enter继续..."
read

ssh $SERVER "sudo systemctl restart taoquant-runner.service"
echo "✅ 服务已重启"
echo ""

# Step 5: 检查服务状态
echo "Step 5: 检查服务状态..."
sleep 3
ssh $SERVER "sudo systemctl status taoquant-runner.service --no-pager -l | head -20"
echo ""

# Step 6: 查看最新日志
echo "Step 6: 查看最新日志（前30行）..."
ssh $SERVER "sudo journalctl -u taoquant-runner.service -n 30 --no-pager"
echo ""

echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "请监控以下内容："
echo "  1. 检查日志中是否有 [FILL_RECOVERY] 相关信息"
echo "  2. 检查是否有 [SELL_PROTECTION] 保护日志"
echo "  3. 确认不再出现unexpected short position"
echo "  4. 监控LEDGER_DRIFT警告"
echo ""
echo "监控命令:"
echo "  ssh $SERVER 'sudo journalctl -u taoquant-runner.service -f | grep -E \"FILL_RECOVERY|SELL_PROTECTION|LEDGER_DRIFT|CRITICAL\"'"
echo ""
