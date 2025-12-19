# QuantConnect Lean 框架设置指南

## 什么是 Lean 框架？

QuantConnect Lean 是 QuantConnect 的开源回测引擎，提供：
- 专业的回测引擎
- 完整的订单管理系统
- 精确的滑点和手续费模拟
- 丰富的性能指标
- Web Dashboard 可视化

## 安装 Lean CLI

### 方法1: 使用 pip 安装（推荐）

```bash
# 安装 Lean CLI
pip install lean

# 验证安装
lean --version
```

### 方法2: 从源码安装

```bash
# 克隆 Lean 仓库
git clone https://github.com/QuantConnect/Lean.git
cd Lean

# 安装依赖（Windows）
.\windows-install.ps1

# 或使用 Docker
docker build -t lean .
```

## 初始化 Lean 项目

```bash
# 在项目根目录初始化
lean init

# 这会创建以下结构：
# Lean/
# ├── Algorithm.Python/
# │   └── BasicTemplateAlgorithm.py
# ├── Data/
# ├── Launcher/
# └── config.json
```

## 将 TaoGrid 算法集成到 Lean

### 步骤1: 创建 Lean 算法文件

在 `Lean/Algorithm.Python/` 目录下创建 `TaoGridAlgorithm.py`：

```python
from AlgorithmImports import *
from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig

class TaoGridAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2025, 9, 26)
        self.SetEndDate(2025, 10, 26)
        self.SetCash(100000)
        
        # 添加数据订阅
        self.symbol = self.AddCrypto("BTCUSDT", Resolution.Minute).Symbol
        
        # 初始化 TaoGrid 算法
        config = TaoGridLeanConfig(
            support=107000.0,
            resistance=123000.0,
            grid_layers_buy=40,
            grid_layers_sell=40,
            min_return=0.0012,
            leverage=50.0,
        )
        
        self.taogrid = TaoGridLeanAlgorithm(config)
        self.taogrid.initialize(
            str(self.symbol),
            self.Time,
            self.EndTime,
            self.History(self.symbol, 100, Resolution.Minute)
        )
    
    def OnData(self, data):
        if self.symbol not in data:
            return
        
        bar = data[self.symbol]
        bar_data = {
            'open': float(bar.Open),
            'high': float(bar.High),
            'low': float(bar.Low),
            'close': float(bar.Close),
            'volume': float(bar.Volume),
        }
        
        portfolio_state = {
            'equity': self.Portfolio.TotalPortfolioValue,
            'cash': self.Portfolio.Cash,
            'holdings': self.Portfolio[self.symbol].Quantity,
            'unrealized_pnl': self.Portfolio[self.symbol].UnrealizedProfit,
        }
        
        order = self.taogrid.on_data(self.Time, bar_data, portfolio_state)
        
        if order:
            if order['direction'] == 'buy':
                self.MarketOrder(self.symbol, order['quantity'])
            else:
                self.MarketOrder(self.symbol, -order['quantity'])
```

### 步骤2: 配置数据源

编辑 `Lean/config.json`：

```json
{
  "algorithm-type-name": "TaoGridAlgorithm",
  "algorithm-language": "Python",
  "algorithm-location": "Algorithm.Python/TaoGridAlgorithm.py",
  "data-folder": "./Data",
  "results-folder": "./Results",
  "messaging-handler": "QuantConnect.Messaging.Messaging",
  "job-queue-handler": "QuantConnect.Queues.JobQueue",
  "api-handler": "QuantConnect.Api.Api",
  "map-file-provider": "QuantConnect.Data.Auxiliary.LocalDiskMapFileProvider",
  "factor-file-provider": "QuantConnect.Data.Auxiliary.LocalDiskFactorFileProvider",
  "data-provider": "QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider",
  "alpha-handler": "QuantConnect.Lean.Engine.Alphas.DefaultAlphaHandler",
  "data-channel-provider": "DataChannelProvider",
  "object-store": "QuantConnect.Lean.Engine.Storage.LocalObjectStore",
  "data-aggregator": "QuantConnect.Lean.Engine.DataFeeds.AggregationManager",
  "symbol-minute-limit": 10000,
  "symbol-second-limit": 10000,
  "symbol-tick-limit": 10000,
  "maximum-chart-series": 4000,
  "force-exchange-always-open": false,
  "transaction-log": "",
  "version-id": "",
  "algorithm-id": "",
  "environment": "backtesting",
  "algorithm-manager-time-loop-maximum": 20,
  "job-user-id": "0",
  "api-access-token": "",
  "job-organization-id": "",
  "messaging-handler-application-id": "",
  "job-name": "TaoGrid Backtest",
  "algorithm-version": "1.0.0"
}
```

### 步骤3: 准备数据

Lean 需要特定格式的数据。对于加密货币，需要：

```bash
# 下载数据（使用 Lean CLI）
lean data download --dataset "crypto" --symbol "BTCUSDT" --resolution "Minute" --start 20250926 --end 20251026

# 或手动准备数据文件
# Data/crypto/okx/minute/btcusdt/20250926_trade.zip
```

### 步骤4: 运行回测

```bash
# 运行回测
lean backtest "TaoGridAlgorithm"

# 查看结果
lean report "TaoGridAlgorithm"
```

## 与当前代码的集成

### 选项1: 保持 SimpleLeanRunner（推荐用于开发）

- 优点：快速迭代，无需 Lean 设置
- 缺点：功能有限，不是生产级

### 选项2: 迁移到完整 Lean 框架（推荐用于生产）

- 优点：专业回测引擎，完整功能
- 缺点：需要更多设置

### 选项3: 混合方案

- 开发阶段：使用 `SimpleLeanRunner`
- 生产阶段：使用 Lean 框架

## 常见问题

### Q: Lean CLI 安装失败？

```bash
# Windows: 确保安装了 .NET SDK
# 下载: https://dotnet.microsoft.com/download

# 验证
dotnet --version
```

### Q: 数据格式不匹配？

Lean 需要特定的数据格式。可以使用数据转换脚本：

```python
# 将我们的数据格式转换为 Lean 格式
from data import DataManager
import pandas as pd

data_manager = DataManager()
data = data_manager.get_klines("BTCUSDT", "1m", start, end)

# 转换为 Lean 格式
# 保存到 Lean/Data/crypto/okx/minute/btcusdt/
```

### Q: 算法无法找到？

确保 `Lean/Algorithm.Python/` 目录在 Python 路径中：

```python
import sys
sys.path.append("path/to/Lean/Algorithm.Python")
```

## 下一步

1. **安装 Lean CLI**: `pip install lean`
2. **初始化项目**: `lean init`
3. **创建算法文件**: 参考上面的 `TaoGridAlgorithm.py`
4. **准备数据**: 下载或转换数据到 Lean 格式
5. **运行回测**: `lean backtest "TaoGridAlgorithm"`

## 参考资源

- [Lean 官方文档](https://www.quantconnect.com/docs)
- [Lean GitHub](https://github.com/QuantConnect/Lean)
- [Lean CLI 文档](https://www.quantconnect.com/docs/v2/lean-cli)

