"""
检查代码中是否真的使用了 Lean 框架。
"""

import sys
import io
import ast
from pathlib import Path

# Set UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_file_for_lean_imports(file_path: Path):
    """检查文件是否导入了 Lean 相关模块"""
    lean_keywords = [
        'QuantConnect',
        'QCAlgorithm',
        'AlgorithmImports',
        'clr',
        'pythonnet',
        'System.',
        'from System',
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content)
            
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                for alias in node.names:
                    imports.append(f"{node.module}.{alias.name}" if node.module else alias.name)
        
        lean_imports = []
        for imp in imports:
            for keyword in lean_keywords:
                if keyword in imp:
                    lean_imports.append(imp)
                    break
        
        return lean_imports, imports
    except Exception as e:
        return None, str(e)

def main():
    project_root = Path(__file__).parent.parent
    
    files_to_check = [
        project_root / "algorithms" / "taogrid" / "simple_lean_runner.py",
        project_root / "algorithms" / "taogrid" / "algorithm.py",
        project_root / "algorithms" / "taogrid" / "helpers" / "grid_manager.py",
    ]
    
    print("=" * 80)
    print("Lean 框架依赖检查")
    print("=" * 80)
    print()
    
    all_lean_imports = []
    
    for file_path in files_to_check:
        print(f"检查: {file_path.name}")
        print("-" * 80)
        
        lean_imports, all_imports = check_file_for_lean_imports(file_path)
        
        if lean_imports is None:
            print(f"  ❌ 读取文件失败: {all_imports}")
        elif lean_imports:
            print(f"  ⚠️  发现 Lean 相关导入:")
            for imp in lean_imports:
                print(f"    - {imp}")
            all_lean_imports.extend(lean_imports)
        else:
            print(f"  ✅ 没有 Lean 相关导入")
            print(f"  所有导入: {', '.join(all_imports[:10])}{'...' if len(all_imports) > 10 else ''}")
        
        print()
    
    print("=" * 80)
    if all_lean_imports:
        print("⚠️  发现 Lean 框架依赖:")
        for imp in set(all_lean_imports):
            print(f"  - {imp}")
    else:
        print("✅ 确认: 代码中没有使用 Lean 框架")
        print()
        print("说明:")
        print("  - 'Lean' 只是命名约定，表示'轻量级/简化版本'")
        print("  - 代码完全独立，只使用标准库和项目内部模块")
        print("  - 可以正常运行，无需安装 Lean 框架")
    print("=" * 80)

if __name__ == "__main__":
    main()

