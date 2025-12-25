# Lean框架完整使用指南

> **目标**: 使用Lean框架运行TaoGrid回测，并在Dashboard中查看结果

---

## 📦 安装状态

✅ Lean CLI已安装 (v1.0.221)
✅ .NET SDK已安装 (6.0.428)
✅ TaoGrid算法已创建

---

## 🚀 快速开始

### 步骤1: 初始化Lean项目

```bash
# 创建Lean项目目录
cd D:\Projects\PythonProjects
mkdir lean-taogrid
cd lean-taogrid

# 初始化Lean项目
lean init
```

**提示**:
- 选择语言: Python
- 选择cloud还是local: Local
- Organization ID: 留空或输入你的QuantConnect org ID

### 步骤2: 复制TaoGrid算法

初始化后，Lean会创建以下结构：

```
lean-taogrid/
├── .lean/
├── data/                # 历史数据
├── main.py             # 算法入口
├── research/           # Jupyter notebooks
└── lean.json           # 配置文件
```

**将我们的TaoGrid算法复制过去**:

```bash
# 从taoquant项目复制算法文件
copy D:\Projects\PythonProjects\taoquant\algorithms\taogrid\*.py .
```

### 步骤3: 修改main.py

替换`main.py`的内容为：

```python
from AlgorithmImports import *
from algorithm import TaoGridLeanAlgorithm
from config import TaoGridLeanConfig

class TaoGridStrategy(QCAlgorithm):
    """TaoGrid Strategy for Lean."""

    def Initialize(self):
        """Initialize algorithm."""
        # Set backtest period
        self.SetStartDate(2025, 7, 10)
        self.SetEndDate(2025, 8, 10)
        self.SetCash(100000)

        # Add crypto
        self.btc = self.AddCrypto("BTCUSDT", Resolution.Minute, Market.Binance)

        # Create TaoGrid config
        config = TaoGridLeanConfig(
            name="TaoGrid Lean",
            description="Grid strategy with S/R ranges",
            support=112000.0,
            resistance=123000.0,
            regime="NEUTRAL_RANGE",
            grid_layers_buy=5,
            grid_layers_sell=5,
            min_return=0.01,
            spacing_multiplier=0.15,
            enable_throttling=True,
        )

        # Initialize TaoGrid algorithm
        self.taogrid = TaoGridLeanAlgorithm(config)

        # Get historical data for grid setup
        history = self.History(self.btc.Symbol, 100, Resolution.Hour)
        if not history.empty:
            self.taogrid.setup_grid(history)

    def OnData(self, data: Slice):
        """Process new data."""
        if not data.ContainsKey(self.btc.Symbol):
            return

        bar = data[self.btc.Symbol]

        # Prepare bar data
        bar_data = {
            'open': float(bar.Open),
            'high': float(bar.High),
            'low': float(bar.Low),
            'close': float(bar.Close),
            'volume': float(bar.Volume),
        }

        # Prepare portfolio state
        portfolio_state = {
            'equity': float(self.Portfolio.TotalPortfolioValue),
            'cash': float(self.Portfolio.Cash),
            'holdings': float(self.Portfolio[self.btc.Symbol].Quantity),
        }

        # Process data with TaoGrid
        current_time = self.Time
        self.taogrid.on_data(current_time, bar_data, portfolio_state)
```

### 步骤4: 配置数据源

编辑`lean.json`，确保数据源配置正确：

```json
{
  "data-folder": "./data",
  "data-provider": "QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider",
  "debugging": false,
  "debugging-method": "LocalCmdline",
  "environments": {
    "live": {
      "live-mode": true
    },
    "backtesting": {
      "live-mode": false
    }
  }
}
```

### 步骤5: 下载数据

Lean需要历史数据。有两个选项：

**选项A: 使用QuantConnect数据**
```bash
# 需要QuantConnect账号
lean cloud pull
```

**选项B: 使用本地数据**
```bash
# 将taoquant的OKX数据转换为Lean格式
python convert_data_to_lean.py
```

我帮你创建数据转换脚本...

### 步骤6: 运行回测

```bash
# 运行回测
lean backtest "TaoGridStrategy"

# 或者指定项目路径
lean backtest --project=.
```

### 步骤7: 查看结果

回测完成后，Lean会生成：

1. **JSON结果**: `.lean/backtests/[timestamp]/results.json`
2. **日志**: `.lean/backtests/[timestamp]/log.txt`
3. **统计**: `.lean/backtests/[timestamp]/statistics.json`

**生成HTML报告**:
```bash
lean report
```

这会生成一个HTML dashboard，包括：
- 📈 Equity curve
- 📊 Trade statistics
- 💰 Drawdown chart
- 📉 Returns distribution
- 🎯 Performance metrics

**在浏览器中查看**:
```bash
# HTML报告会自动打开浏览器
# 或者手动打开
start .lean/backtests/[最新timestamp]/report.html
```

---

## 📊 Lean Dashboard功能

Lean的报告包含以下部分：

### 1. 概览 (Overview)
- Total return
- Sharpe ratio
- Max drawdown
- Win rate

### 2. Equity Curve
- 交互式图表
- 支持缩放和平移
- 显示回撤区域

### 3. 交易列表 (Trades)
- 每笔交易的详细信息
- 可排序、可过滤
- 盈亏分析

### 4. 持仓 (Holdings)
- 实时持仓变化
- 仓位占比
- 暴露度分析

### 5. 统计指标 (Statistics)
- 详细的性能指标
- 风险指标
- 交易统计

### 6. 图表 (Charts)
- 自定义图表
- 指标可视化
- 多时间框架

---

## 🔧 常见问题

### Q1: 数据在哪里？

Lean需要特定格式的数据。有3个选项：

1. **QuantConnect Cloud**: 使用QC的数据（需要账号）
2. **本地数据**: 转换OKX数据为Lean格式
3. **自定义数据源**: 实现IDataFeed接口

### Q2: 如何实时查看进度？

```bash
# 使用--verbose查看详细日志
lean backtest --verbose

# 或者tail日志文件
tail -f .lean/backtests/latest/log.txt
```

### Q3: 如何调试？

```bash
# 启用调试模式
lean backtest --debug pycharm

# 或者在代码中添加日志
self.Debug("Message here")
```

### Q4: 如何比较多次回测？

```bash
# 运行多次回测
lean backtest --name "test1"
lean backtest --name "test2"

# 生成对比报告
lean report --compare test1 test2
```

---

## 🎯 推荐工作流

### 完整的研究→回测→实盘流程

1. **Research (Jupyter)**
   ```bash
   lean research
   # 在notebook中分析数据、测试策略逻辑
   ```

2. **Backtest (本地)**
   ```bash
   lean backtest
   # 快速迭代，验证策略
   ```

3. **Cloud Backtest (云端)**
   ```bash
   lean cloud push
   lean cloud backtest
   # 使用完整数据集
   ```

4. **Live Paper Trading**
   ```bash
   lean live --environment paper
   # 实盘模拟
   ```

5. **Live Trading**
   ```bash
   lean live --environment live
   # 真实交易
   ```

---

## 📝 下一步

1. **初始化Lean项目**: `cd D:\Projects\PythonProjects && mkdir lean-taogrid && cd lean-taogrid && lean init`

2. **复制算法文件**: 从taoquant复制到lean-taogrid

3. **准备数据**: 转换OKX数据或使用QC数据

4. **运行回测**: `lean backtest`

5. **查看Dashboard**: 打开生成的HTML报告

---

**准备好了吗？让我知道你想从哪一步开始！**

