# QuantConnect Lean 框架安装和设置指南

## 当前状态

根据检查，您的系统：
- ❌ Lean CLI 未安装
- ❌ Lean 目录不存在
- ❌ pythonnet 未安装

## 快速安装步骤

### 1. 安装 Lean CLI

```bash
pip install lean
```

### 2. 验证安装

```bash
lean --version
```

### 3. 初始化 Lean 项目

在项目根目录运行：

```bash
lean init
```

这会创建 `Lean/` 目录结构。

### 4. 安装 pythonnet（如果需要 Python 算法）

```bash
pip install pythonnet
```

## 详细设置步骤

### 步骤1: 安装依赖

```bash
# 安装 Lean CLI
pip install lean

# 安装 pythonnet（用于 Python 算法）
pip install pythonnet

# 验证
lean --version
```

### 步骤2: 初始化项目

```bash
# 在项目根目录
cd C:\Users\tzhang\PycharmProjects\taoquant
lean init
```

这会创建：
```
Lean/
├── Algorithm.Python/          # Python 算法目录
├── Data/                      # 数据目录
├── Launcher/                  # Lean 启动器
└── config.json               # 配置文件
```

### 步骤3: 创建 TaoGrid 算法

在 `Lean/Algorithm.Python/` 目录下创建 `TaoGridAlgorithm.py`：

```python
from AlgorithmImports import *
import sys
from pathlib import Path

# 添加项目路径以导入我们的算法
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig

class TaoGridAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2025, 9, 26)
        self.SetEndDate(2025, 10, 26)
        self.SetCash(100000)
        
        # 添加加密货币数据订阅
        self.symbol = self.AddCrypto("BTCUSDT", Resolution.Minute).Symbol
        
        # 初始化 TaoGrid 配置
        config = TaoGridLeanConfig(
            support=107000.0,
            resistance=123000.0,
            grid_layers_buy=40,
            grid_layers_sell=40,
            min_return=0.0012,
            leverage=50.0,
            enable_console_log=False,
        )
        
        # 初始化算法
        self.taogrid = TaoGridLeanAlgorithm(config)
        
        # 获取历史数据用于初始化
        history = self.History(self.symbol, 100, Resolution.Minute)
        if history is not None and len(history) > 0:
            # 转换为 pandas DataFrame
            import pandas as pd
            df = pd.DataFrame({
                'open': [float(bar.Open) for bar in history],
                'high': [float(bar.High) for bar in history],
                'low': [float(bar.Low) for bar in history],
                'close': [float(bar.Close) for bar in history],
                'volume': [float(bar.Volume) for bar in history],
            })
            df.index = [bar.Time for bar in history]
            
            # 初始化算法
            self.taogrid.initialize(
                str(self.symbol),
                self.Time,
                self.EndTime,
                df
            )
    
    def OnData(self, data):
        if self.symbol not in data:
            return
        
        bar = data[self.symbol]
        
        # 准备 bar 数据
        bar_data = {
            'open': float(bar.Open),
            'high': float(bar.High),
            'low': float(bar.Low),
            'close': float(bar.Close),
            'volume': float(bar.Volume),
            'trend_score': 0.0,  # 需要从指标计算
            'mr_z': 0.0,
            'breakout_risk_down': 0.0,
            'breakout_risk_up': 0.0,
            'range_pos': 0.5,
            'vol_score': 0.0,
            'funding_rate': 0.0,
            'minutes_to_funding': 0.0,
        }
        
        # 准备 portfolio 状态
        portfolio_state = {
            'equity': self.Portfolio.TotalPortfolioValue,
            'cash': self.Portfolio.Cash,
            'holdings': self.Portfolio[self.symbol].Quantity,
            'unrealized_pnl': self.Portfolio[self.symbol].UnrealizedProfit,
        }
        
        # 调用算法
        order = self.taogrid.on_data(self.Time, bar_data, portfolio_state)
        
        if order:
            quantity = order['quantity']
            if order['direction'] == 'buy':
                self.MarketOrder(self.symbol, quantity)
            else:
                self.MarketOrder(self.symbol, -quantity)
```

### 步骤4: 准备数据

Lean 需要特定格式的数据。您可以选择：

**选项A: 使用 Lean 数据下载（推荐）**

```bash
# 下载加密货币数据
lean data download --dataset "crypto" --symbol "BTCUSDT" --resolution "Minute" --start 20250926 --end 20251026
```

**选项B: 转换现有数据**

创建一个数据转换脚本将我们的数据格式转换为 Lean 格式。

### 步骤5: 运行回测

```bash
# 运行回测
lean backtest "TaoGridAlgorithm"

# 查看结果
lean report "TaoGridAlgorithm"
```

## 注意事项

1. **数据格式**: Lean 需要特定的数据格式。如果使用自己的数据，需要转换。

2. **指标计算**: Lean 的 `OnData` 中需要计算所有指标（trend_score, mr_z 等）。可能需要：
   - 在 Lean 中重新实现指标计算
   - 或预先计算并存储

3. **订单执行**: Lean 使用 `MarketOrder`，而我们的算法使用限价单。可能需要：
   - 修改算法以使用市价单
   - 或使用 Lean 的限价单功能

## 下一步

1. 运行 `pip install lean` 安装 Lean CLI
2. 运行 `lean init` 初始化项目
3. 创建 `TaoGridAlgorithm.py` 文件
4. 准备数据
5. 运行回测

## 参考

- [Lean 官方文档](https://www.quantconnect.com/docs)
- [Lean GitHub](https://github.com/QuantConnect/Lean)
- [Lean CLI 文档](https://www.quantconnect.com/docs/v2/lean-cli)

