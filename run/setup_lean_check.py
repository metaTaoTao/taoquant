"""
检查 Lean 框架是否已安装和配置。
"""

import sys
import io
import subprocess
from pathlib import Path

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_lean_installation():
    """检查 Lean CLI 是否已安装"""
    try:
        result = subprocess.run(
            ["lean", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ Lean CLI 已安装: {result.stdout.strip()}")
            return True
        else:
            print("❌ Lean CLI 未正确安装")
            return False
    except FileNotFoundError:
        print("❌ Lean CLI 未安装")
        return False
    except Exception as e:
        print(f"❌ 检查 Lean CLI 时出错: {e}")
        return False

def check_lean_directory():
    """检查 Lean 目录是否存在"""
    project_root = Path(__file__).parent.parent
    lean_dir = project_root / "Lean"
    
    if lean_dir.exists():
        print(f"✅ Lean 目录存在: {lean_dir}")
        
        # 检查关键文件
        algorithm_dir = lean_dir / "Algorithm.Python"
        if algorithm_dir.exists():
            print(f"✅ Algorithm.Python 目录存在")
        else:
            print(f"⚠️  Algorithm.Python 目录不存在")
        
        config_file = lean_dir / "config.json"
        if config_file.exists():
            print(f"✅ config.json 存在")
        else:
            print(f"⚠️  config.json 不存在")
        
        return True
    else:
        print(f"❌ Lean 目录不存在: {lean_dir}")
        print(f"   运行 'lean init' 来初始化")
        return False

def check_pythonnet():
    """检查 pythonnet 是否已安装（Lean 需要）"""
    try:
        import clr
        print("✅ pythonnet 已安装")
        return True
    except ImportError:
        print("❌ pythonnet 未安装")
        print("   安装: pip install pythonnet")
        return False

def main():
    print("=" * 80)
    print("Lean 框架检查")
    print("=" * 80)
    print()
    
    lean_installed = check_lean_installation()
    print()
    
    lean_dir_exists = check_lean_directory()
    print()
    
    pythonnet_installed = check_pythonnet()
    print()
    
    print("=" * 80)
    if lean_installed and lean_dir_exists and pythonnet_installed:
        print("✅ Lean 框架已完全配置")
        print()
        print("下一步:")
        print("1. 创建算法文件: Lean/Algorithm.Python/TaoGridAlgorithm.py")
        print("2. 准备数据: lean data download ...")
        print("3. 运行回测: lean backtest 'TaoGridAlgorithm'")
    else:
        print("⚠️  Lean 框架未完全配置")
        print()
        print("安装步骤:")
        print("1. 安装 Lean CLI: pip install lean")
        print("2. 初始化项目: lean init")
        print("3. 安装 pythonnet: pip install pythonnet")
        print("4. 参考: docs/setup_lean_framework.md")
    print("=" * 80)

if __name__ == "__main__":
    main()

