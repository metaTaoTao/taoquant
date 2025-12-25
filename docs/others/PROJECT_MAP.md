# 项目地图（不迷路版）

这份文档把 taoquant 按“你现在要做什么”快速分层：**实盘**、**回测/研究**、**历史遗留/产物**。你只需要先看“实盘最短路径”那几份文件即可。

## 实盘（Bitget）最短路径（你只要先盯住这条链路）

入口与调用链：

- **入口**：`algorithms/taogrid/run_bitget_live.py`
- **Runner（1m循环 / 下单同步 / 处理成交）**：`algorithms/taogrid/bitget_live_runner.py`
- **策略/网格核心逻辑**：`algorithms/taogrid/algorithm.py`
- **参数配置（TaoGridLeanConfig）**：`algorithms/taogrid/config.py`
- **网格管理/触发/配对**：`algorithms/taogrid/helpers/grid_manager.py`
- **数据源（Bitget行情，CCXT）**：`data/sources/bitget_sdk.py`
- **执行引擎（Bitget下单/撤单/查询，CCXT）**：`execution/engines/bitget_engine.py`
- **日志**：`algorithms/taogrid/live_logger.py`

你想“确认实盘在做什么”，按这个顺序读就不会散：
1) `run_bitget_live.py`（参数/环境变量/启动配置）
2) `bitget_live_runner.py`（主循环、成交处理、订单同步）
3) `algorithm.py`（策略状态机、风控开关、信号）
4) `grid_manager.py`（网格生成、触发、配对、仓位与风控细节）
5) `bitget_engine.py`（交易所交互细节）

## 回测/研究最短路径（如果你在调参数）

- `algorithms/taogrid/simple_lean_runner.py`：主要回测入口（本项目里标注“运行这个”）
- `orchestration/backtest_runner.py` + `execution/engines/vectorbt_engine.py`：VectorBT回测框架链路

## 顶层目录怎么理解（先看这一段就不迷路）

- **必须（实盘/回测会用到）**
  - `algorithms/taogrid/`：TaoGrid主实现（实盘+回测都在这）
  - `execution/`：引擎与执行相关
  - `data/`：数据管理与交易所数据源
  - `analytics/`：指标/因子（实盘runner里也会算部分因子）
  - `risk_management/`：风控工具
  - `utils/`：通用工具

- **高噪声（建议默认忽略/不看）**
  - `run/`：大量一次性实验脚本与输出（文件数巨大，很容易把你带偏）
  - `logs/`：运行产物

- **可选（只有你需要时再看）**
  - `tests/`：单测
  - `scripts/`：运维脚本（本地/部署）
  - `docs/`：设计与研究文档（内容多，但不是运行必需）

- **历史/归档**
  - `legacy/`：旧代码与旧文档
  - `TV/`：TradingView脚本/文本
  - `notebooks/`：notebook实验

## “不迷路”工作方式（推荐）

1) 先只打开/搜索 **实盘最短路径**那几个文件  
2) 需要回测验证时再看 `simple_lean_runner.py`  
3) 其余目录默认不搜索（我已加 `.cursorignore` 来隐藏 `run/legacy/notebooks/TV/logs` 等高噪声目录）


