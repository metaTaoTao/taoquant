# TaoGrid Lean 手动安装指南

## 步骤1：安装Python依赖

```bash
# 安装pythonnet（Python与.NET互操作）
pip install pythonnet==3.0.1

# 安装QuantConnect SDK
pip install quantconnect
```

## 步骤2：克隆Lean源码

```bash
# 进入项目父目录
cd D:\Projects\PythonProjects

# 克隆Lean仓库
git clone https://github.com/QuantConnect/Lean.git

# 进入Lean目录
cd Lean
```

## 步骤3：验证Lean安装

```bash
# 查看Lean版本
cd Launcher
dotnet --version
```

## 步骤4：配置PYTHONPATH

为了让Lean能访问taoquant模块，需要设置环境变量：

**Windows（临时设置，当前会话有效）**：
```cmd
set PYTHONPATH=D:\Projects\PythonProjects\taoquant;%PYTHONPATH%
```

**Windows（永久设置）**：
1. 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
2. 在"用户变量"中新建：
   - 变量名：`PYTHONPATH`
   - 变量值：`D:\Projects\PythonProjects\taoquant`

## 步骤5：测试导入

```bash
python -c "import sys; sys.path.insert(0, r'D:\Projects\PythonProjects\taoquant'); from analytics.indicators.grid_generator import calculate_grid_spacing; print('Import successful!')"
```

如果显示 `Import successful!`，说明环境配置正确。

## 常见问题

### pythonnet安装失败

**错误**: `error: Microsoft Visual C++ 14.0 or greater is required`

**解决方案**：
1. 安装 Visual Studio Build Tools：https://visualstudio.microsoft.com/downloads/
2. 选择"Desktop development with C++"工作负载
3. 重新运行 `pip install pythonnet==3.0.1`

### Git克隆速度慢

**解决方案**：
1. 使用镜像：`git clone https://gitclone.com/github.com/QuantConnect/Lean.git`
2. 或直接下载ZIP：https://github.com/QuantConnect/Lean/archive/refs/heads/master.zip

### .NET SDK未找到

**解决方案**：
1. 确保安装的是SDK（不是Runtime）
2. 重启命令行窗口
3. 检查PATH环境变量中是否包含 `C:\Program Files\dotnet`
