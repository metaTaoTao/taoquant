"""
诊断回测结果差异的原因。

检查：
1. 时间范围
2. 数据范围
3. 代码版本（Git commit）
4. Python/包版本
5. 随机性（如果有）
"""

import sys
import io
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import json

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np

def check_git_version():
    """检查Git版本和当前commit"""
    print("=" * 80)
    print("1. Git版本检查")
    print("=" * 80)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            print(f"当前commit: {commit_hash}")
            
            # 获取commit信息
            result2 = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%H%n%an%n%ae%n%ad%n%s", "--date=iso"],
                capture_output=True,
                text=True,
                cwd=project_root
            )
            if result2.returncode == 0:
                lines = result2.stdout.strip().split('\n')
                if len(lines) >= 5:
                    print(f"  作者: {lines[1]}")
                    print(f"  时间: {lines[3]}")
                    print(f"  信息: {lines[4]}")
        else:
            print("无法获取Git commit信息")
    except Exception as e:
        print(f"Git检查失败: {e}")
    print()

def check_python_versions():
    """检查Python和关键包版本"""
    print("=" * 80)
    print("2. Python/包版本检查")
    print("=" * 80)
    print(f"Python版本: {sys.version}")
    print()
    
    key_packages = ['pandas', 'numpy', 'taoquant']
    for pkg in key_packages:
        try:
            if pkg == 'taoquant':
                # 尝试导入taoquant并获取版本
                try:
                    import taoquant
                    version = getattr(taoquant, '__version__', 'unknown')
                    print(f"{pkg}: {version}")
                except:
                    print(f"{pkg}: 无法获取版本")
            else:
                mod = __import__(pkg)
                version = getattr(mod, '__version__', 'unknown')
                print(f"{pkg}: {version}")
        except Exception as e:
            print(f"{pkg}: 无法获取版本 ({e})")
    print()

def check_data_ranges():
    """检查数据范围"""
    print("=" * 80)
    print("3. 数据范围检查")
    print("=" * 80)
    
    from data import DataManager
    
    # 检查缓存数据
    cache_file = project_root / "data" / "cache" / "okx_btcusdt_1m.parquet"
    if cache_file.exists():
        try:
            cached_data = pd.read_parquet(cache_file)
            if not cached_data.empty:
                print(f"缓存数据文件: {cache_file}")
                print(f"  时间范围: {cached_data.index.min()} 到 {cached_data.index.max()}")
                print(f"  数据条数: {len(cached_data)}")
                print(f"  列: {list(cached_data.columns)}")
        except Exception as e:
            print(f"读取缓存数据失败: {e}")
    else:
        print("未找到缓存数据文件")
    
    print()
    
    # 检查两个时间范围的数据
    ranges = [
        ("参数寻优范围", datetime(2025, 7, 10, tzinfo=timezone.utc), datetime(2025, 8, 10, tzinfo=timezone.utc)),
        ("默认回测范围", datetime(2025, 9, 26, tzinfo=timezone.utc), datetime(2025, 10, 26, tzinfo=timezone.utc)),
    ]
    
    for name, start, end in ranges:
        print(f"{name}: {start.date()} 到 {end.date()}")
        try:
            dm = DataManager()
            data = dm.get_klines(
                symbol="BTCUSDT",
                timeframe="1m",
                start=start,
                end=end,
                source="okx",
                use_cache=False,  # 强制从API获取
            )
            if not data.empty:
                print(f"  数据条数: {len(data)}")
                print(f"  实际范围: {data.index.min()} 到 {data.index.max()}")
            else:
                print(f"  无数据")
        except Exception as e:
            print(f"  获取数据失败: {e}")
        print()

def check_config_defaults():
    """检查配置默认值"""
    print("=" * 80)
    print("4. 配置默认值检查")
    print("=" * 80)
    
    from algorithms.taogrid.config import TaoGridLeanConfig
    
    config = TaoGridLeanConfig()
    
    # 检查关键参数
    key_params = [
        'leverage', 'grid_layers_buy', 'grid_layers_sell', 'min_return',
        'risk_budget_pct', 'support', 'resistance',
        'enable_funding_factor', 'enable_mm_risk_zone',
        'breakout_band_atr_mult', 'breakout_band_pct',
        'range_top_band_start', 'range_buy_k', 'range_sell_k',
    ]
    
    for param in key_params:
        value = getattr(config, param, None)
        print(f"{param}: {value}")
    print()

def check_random_seeds():
    """检查是否有随机数生成"""
    print("=" * 80)
    print("5. 随机性检查")
    print("=" * 80)
    
    # 检查代码中是否有random调用
    import re
    
    code_files = [
        project_root / "algorithms" / "taogrid" / "algorithm.py",
        project_root / "algorithms" / "taogrid" / "helpers" / "grid_manager.py",
        project_root / "algorithms" / "taogrid" / "simple_lean_runner.py",
    ]
    
    for code_file in code_files:
        if code_file.exists():
            content = code_file.read_text(encoding='utf-8')
            # 查找random相关调用
            random_patterns = [
                r'import\s+random',
                r'from\s+random\s+import',
                r'np\.random',
                r'random\.',
            ]
            matches = []
            for pattern in random_patterns:
                if re.search(pattern, content):
                    matches.append(pattern)
            if matches:
                print(f"{code_file.name}: 发现随机数使用 - {matches}")
    
    print("如果代码中没有随机数，回测应该是确定性的")
    print()

def main():
    print("=" * 80)
    print("回测结果差异诊断")
    print("=" * 80)
    print()
    
    check_git_version()
    check_python_versions()
    check_data_ranges()
    check_config_defaults()
    check_random_seeds()
    
    print("=" * 80)
    print("诊断完成")
    print("=" * 80)
    print()
    print("请提供以下信息以便进一步诊断：")
    print("1. 家里电脑的回测结果（ROE、Sharpe、交易数、最大回撤等）")
    print("2. 公司电脑的回测结果（如果已运行）")
    print("3. 你运行的具体时间范围（家里和公司是否相同？）")
    print("4. 你运行的具体配置（是否使用了simple_lean_runner.py的默认配置？）")

if __name__ == "__main__":
    main()

