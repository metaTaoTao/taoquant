#!/usr/bin/env python3
"""
测试脚本：验证 buy order fill 后 sell limit order 会立即挂上

使用方法：
1. 查看当前状态：python scripts/test_buy_fill_sell_order.py status
2. 分析最接近当前价格的 buy level：python scripts/test_buy_fill_sell_order.py analyze
3. 模拟测试（不实际修改订单）：python scripts/test_buy_fill_sell_order.py simulate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("Error: requests library not installed. Run: pip install requests")
    sys.exit(1)


def load_status_file(status_file: Path) -> Dict[str, Any]:
    """加载状态文件"""
    if not status_file.exists():
        print(f"❌ 状态文件不存在: {status_file}")
        sys.exit(1)
    
    try:
        with open(status_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 读取状态文件失败: {e}")
        sys.exit(1)


def get_dashboard_status(dashboard_url: str = "http://localhost:8000", token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """从 dashboard API 获取状态"""
    try:
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        response = requests.get(f"{dashboard_url}/api/status", headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print("⚠️  Dashboard 需要 token 认证")
            print(f"   使用: python {sys.argv[0]} --token YOUR_TOKEN")
            return None
        else:
            print(f"⚠️  Dashboard API 返回错误: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"⚠️  无法连接到 dashboard: {e}")
        return None


def format_price(price: float) -> str:
    """格式化价格"""
    return f"${price:,.2f}"


def format_pct_diff(price1: float, price2: float) -> str:
    """计算价格差异百分比"""
    if price2 == 0:
        return "N/A"
    diff_pct = ((price1 - price2) / price2) * 100
    sign = "+" if diff_pct >= 0 else ""
    return f"{sign}{diff_pct:.2f}%"


def show_status(status: Dict[str, Any]):
    """显示当前状态"""
    print("\n" + "="*80)
    print("📊 当前交易状态")
    print("="*80)
    
    # 市场价格
    market = status.get("market", {})
    current_price = market.get("close")
    if current_price:
        print(f"\n💰 当前价格: {format_price(float(current_price))}")
    else:
        print("\n⚠️  无法获取当前价格")
        return
    
    # 持仓信息
    portfolio = status.get("portfolio", {})
    if portfolio:
        equity = portfolio.get("equity", 0)
        holdings = portfolio.get("holdings", 0)
        unrealized_pnl = portfolio.get("unrealized_pnl", 0)
        print(f"📈 权益: ${equity:,.2f}")
        print(f"📦 持仓: {float(holdings):.6f} BTC")
        print(f"💵 未实现盈亏: ${unrealized_pnl:,.2f}")
    
    # 活跃订单
    active_orders = status.get("active_orders", [])
    if not active_orders:
        print("\n⚠️  当前没有活跃的 limit orders")
        return
    
    # 分类订单
    buy_orders = [o for o in active_orders if o.get("direction", "").lower() == "buy"]
    sell_orders = [o for o in active_orders if o.get("direction", "").lower() == "sell"]
    
    print(f"\n📋 活跃订单总数: {len(active_orders)}")
    print(f"   - BUY orders: {len(buy_orders)}")
    print(f"   - SELL orders: {len(sell_orders)}")
    
    # 显示 buy orders
    if buy_orders:
        print("\n🟢 BUY Limit Orders:")
        print(f"{'Level':<8} {'Price':<15} {'Size':<12} {'Distance':<12} {'Client OID':<30}")
        print("-" * 80)
        for order in sorted(buy_orders, key=lambda x: float(x.get("price", 0)), reverse=True):
            level = order.get("level", "N/A")
            price = float(order.get("price", 0))
            size = float(order.get("size", 0))
            client_oid = order.get("client_order_id", "")[:30]
            distance = format_pct_diff(price, float(current_price))
            print(f"L{level:<7} {format_price(price):<15} {size:<12.6f} {distance:<12} {client_oid:<30}")
    
    # 显示 sell orders
    if sell_orders:
        print("\n🔴 SELL Limit Orders:")
        print(f"{'Level':<8} {'Price':<15} {'Size':<12} {'Distance':<12} {'Client OID':<30}")
        print("-" * 80)
        for order in sorted(sell_orders, key=lambda x: float(x.get("price", 0))):
            level = order.get("level", "N/A")
            price = float(order.get("price", 0))
            size = float(order.get("size", 0))
            client_oid = order.get("client_order_id", "")[:30]
            distance = format_pct_diff(price, float(current_price))
            print(f"L{level:<7} {format_price(price):<15} {size:<12.6f} {distance:<12} {client_oid:<30}")


def analyze_closest_buy_order(status: Dict[str, Any]):
    """分析最接近当前价格的 buy order"""
    print("\n" + "="*80)
    print("🔍 分析最接近当前价格的 BUY Order")
    print("="*80)
    
    market = status.get("market", {})
    current_price = market.get("close")
    if not current_price:
        print("❌ 无法获取当前价格")
        return
    
    current_price = float(current_price)
    active_orders = status.get("active_orders", [])
    buy_orders = [o for o in active_orders if o.get("direction", "").lower() == "buy"]
    
    if not buy_orders:
        print("❌ 当前没有 BUY orders")
        return
    
    # 找到最接近当前价格的 buy order（价格低于当前价格）
    closest_order = None
    min_distance = float('inf')
    
    for order in buy_orders:
        price = float(order.get("price", 0))
        if price < current_price:  # 只考虑低于当前价格的 buy order
            distance = current_price - price
            if distance < min_distance:
                min_distance = distance
                closest_order = order
    
    if not closest_order:
        print("⚠️  所有 BUY orders 的价格都高于当前价格，无法被 fill")
        print("\n💡 建议：等待价格下跌，或者手动修改一个 buy order 的价格")
        return
    
    level = closest_order.get("level", "N/A")
    price = float(closest_order.get("price", 0))
    size = float(closest_order.get("size", 0))
    client_oid = closest_order.get("client_order_id", "")
    distance_pct = format_pct_diff(price, current_price)
    
    print(f"\n✅ 最接近当前价格的 BUY Order:")
    print(f"   Level: L{level}")
    print(f"   价格: {format_price(price)}")
    print(f"   数量: {size:.6f} BTC")
    print(f"   距离当前价格: {format_price(min_distance)} ({distance_pct})")
    print(f"   Client OID: {client_oid}")
    
    # 计算对应的 sell level
    strategy = status.get("strategy", {})
    sell_levels = None  # 需要从配置中获取
    
    print(f"\n📝 测试步骤:")
    print(f"   1. 当前价格: {format_price(current_price)}")
    print(f"   2. 最接近的 BUY: {format_price(price)} (L{level})")
    print(f"   3. 当价格跌到 {format_price(price)} 时，这个 BUY order 会被 fill")
    print(f"   4. Fill 后，系统应该立即挂上对应的 SELL limit order (L{level})")
    print(f"\n💡 测试方法:")
    print(f"   - 方法 A: 等待价格自然下跌到 {format_price(price)}")
    print(f"   - 方法 B: 在 Bitget 交易所手动修改这个 buy order 的价格到接近当前价格")
    print(f"   - 方法 C: 使用脚本临时修改价格（需要实现）")


def simulate_fill(status: Dict[str, Any], buy_level: Optional[int] = None):
    """模拟 buy order fill 的场景"""
    print("\n" + "="*80)
    print("🧪 模拟 BUY Order Fill 场景")
    print("="*80)
    
    market = status.get("market", {})
    current_price = market.get("close")
    if not current_price:
        print("❌ 无法获取当前价格")
        return
    
    current_price = float(current_price)
    active_orders = status.get("active_orders", [])
    buy_orders = [o for o in active_orders if o.get("direction", "").lower() == "buy"]
    
    if not buy_orders:
        print("❌ 当前没有 BUY orders")
        return
    
    # 选择要模拟的 buy order
    target_order = None
    if buy_level is not None:
        target_order = next((o for o in buy_orders if o.get("level") == buy_level), None)
        if not target_order:
            print(f"❌ 找不到 Level {buy_level} 的 BUY order")
            return
    else:
        # 选择最接近当前价格的
        min_distance = float('inf')
        for order in buy_orders:
            price = float(order.get("price", 0))
            if price < current_price:
                distance = current_price - price
                if distance < min_distance:
                    min_distance = distance
                    target_order = order
        
        if not target_order:
            print("⚠️  所有 BUY orders 的价格都高于当前价格")
            return
    
    level = target_order.get("level", "N/A")
    buy_price = float(target_order.get("price", 0))
    buy_size = float(target_order.get("size", 0))
    client_oid = target_order.get("client_order_id", "")
    
    print(f"\n📋 模拟场景:")
    print(f"   假设 BUY Order L{level} @ {format_price(buy_price)} 被 fill")
    print(f"   - Fill 价格: {format_price(buy_price)}")
    print(f"   - Fill 数量: {buy_size:.6f} BTC")
    print(f"   - Client OID: {client_oid}")
    
    # 根据策略逻辑，buy[i] fill 后应该挂 sell[i]
    print(f"\n✅ 预期行为:")
    print(f"   1. BUY L{level} fill 后，系统会调用 on_order_filled()")
    print(f"   2. 系统会移除已 fill 的 BUY L{level} order")
    print(f"   3. 系统会立即挂上 SELL L{level} limit order")
    print(f"   4. SELL 价格应该是 sell_levels[{level}]")
    
    print(f"\n🔍 验证方法:")
    print(f"   1. 监控日志: sudo journalctl -u taoquant-runner -f | grep -E 'ORDER_FILLED|Placed sell limit'")
    print(f"   2. 查看 dashboard 的 Active Limit Orders 表格")
    print(f"   3. 检查日志中是否有: 'Placed sell limit order at L{level+1} @ $...'")


def main():
    parser = argparse.ArgumentParser(
        description="测试 buy order fill 后 sell limit order 挂单逻辑",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查看当前状态
  python scripts/test_buy_fill_sell_order.py status

  # 分析最接近当前价格的 buy order
  python scripts/test_buy_fill_sell_order.py analyze

  # 模拟 fill 场景
  python scripts/test_buy_fill_sell_order.py simulate

  # 使用 dashboard API（需要 token）
  python scripts/test_buy_fill_sell_order.py status --dashboard --token YOUR_TOKEN
        """
    )
    
    parser.add_argument(
        "action",
        choices=["status", "analyze", "simulate"],
        help="要执行的操作"
    )
    
    parser.add_argument(
        "--status-file",
        type=Path,
        default=Path("state/live_status.json"),
        help="状态文件路径 (默认: state/live_status.json)"
    )
    
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="使用 dashboard API 而不是状态文件"
    )
    
    parser.add_argument(
        "--dashboard-url",
        default="http://localhost:8000",
        help="Dashboard URL (默认: http://localhost:8000)"
    )
    
    parser.add_argument(
        "--token",
        help="Dashboard API token (如果设置了 TAOQUANT_DASHBOARD_TOKEN)"
    )
    
    parser.add_argument(
        "--buy-level",
        type=int,
        help="指定要模拟的 buy level (仅用于 simulate 操作)"
    )
    
    args = parser.parse_args()
    
    # 获取状态
    if args.dashboard:
        status = get_dashboard_status(args.dashboard_url, args.token)
        if not status:
            print("\n💡 提示: 可以尝试使用状态文件:")
            print(f"   python {sys.argv[0]} {args.action} --status-file {args.status_file}")
            sys.exit(1)
    else:
        status_file = PROJECT_ROOT / args.status_file
        status = load_status_file(status_file)
    
    # 执行操作
    if args.action == "status":
        show_status(status)
    elif args.action == "analyze":
        analyze_closest_buy_order(status)
    elif args.action == "simulate":
        simulate_fill(status, args.buy_level)


if __name__ == "__main__":
    main()

