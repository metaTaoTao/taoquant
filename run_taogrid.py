"""
TaoGrid 策略快速启动脚本

用法：
    python run_taogrid.py          # 运行回测
    python run_taogrid.py --dash   # 生成dashboard
    python run_taogrid.py --help   # 显示帮助
"""

import sys
from pathlib import Path

def main():
    """快速启动TaoGrid回测或dashboard。"""
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        print("\n可用命令：")
        print("  python run_taogrid.py              # 运行回测")
        print("  python run_taogrid.py --dash       # 生成dashboard")
        print("  python run_taogrid.py --dashboard  # 生成dashboard")
        print("\n结果保存在: run/results_lean_taogrid/")
        return

    if '--dash' in sys.argv or '--dashboard' in sys.argv:
        print("=" * 80)
        print("生成TaoGrid Dashboard")
        print("=" * 80)
        print()

        # 运行dashboard生成
        import subprocess
        result = subprocess.run(
            [sys.executable, "algorithms/taogrid/create_dashboard.py"],
            cwd=Path(__file__).parent
        )

        if result.returncode == 0:
            dashboard_path = Path("run/results_lean_taogrid/dashboard.html").absolute()
            print()
            print("=" * 80)
            print("Dashboard已生成！")
            print("=" * 80)
            print(f"\n文件位置: {dashboard_path}")
            print("\n在浏览器中打开:")
            print(f"  start {dashboard_path}  (Windows)")
            print(f"  open {dashboard_path}   (Mac)")
            print()
        else:
            print("\n❌ Dashboard生成失败！")
            print("请检查是否已运行回测: python run_taogrid.py")
    else:
        print("=" * 80)
        print("TaoGrid 网格策略回测")
        print("=" * 80)
        print()

        # 运行回测
        import subprocess
        result = subprocess.run(
            [sys.executable, "algorithms/taogrid/simple_lean_runner.py"],
            cwd=Path(__file__).parent
        )

        if result.returncode == 0:
            print()
            print("=" * 80)
            print("回测完成！")
            print("=" * 80)
            print("\n查看结果:")
            print("  1. 生成dashboard: python run_taogrid.py --dash")
            print("  2. 查看指标: cat run/results_lean_taogrid/metrics.json")
            print("  3. 查看交易: cat run/results_lean_taogrid/trades.csv")
            print()
        else:
            print("\n❌ 回测失败！请检查错误信息。")

if __name__ == "__main__":
    main()
