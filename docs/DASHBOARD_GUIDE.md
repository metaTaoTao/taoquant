# 策略监控面板（云上）- 最小可用版

目标：无论你在本地还是云服务器跑，我们提供一个 **FastAPI Dashboard**（默认只读）：
- 实时看 **PnL/风险/网格状态**
- 看最近日志

你当前更偏好的流程是：**手动停机器人 → 手动改参数 → 手动启动**。所以 Dashboard 默认不提供启停/应用配置按钮，避免误触。

## 1) 安装依赖

```bash
pip install -r requirements.txt
```

（已将 `fastapi`/`uvicorn` 加到 `requirements.txt` 里）

## 2) 运行 dashboard

在云服务器上：

```bash
cd /path/to/taoquant
uvicorn dashboard.server:app --host 0.0.0.0 --port 8000
```

浏览器打开：`http://<你的服务器IP>:8000/`

## 本地（Windows）怎么用？

你现在在本地跑的话，Dashboard 依然能用来**监控 PnL/风险/网格状态**（读 `state/live_status.json`）。

启动命令（PowerShell）：

```powershell
cd C:\Users\tzhang\PycharmProjects\taoquant
python -m pip install -r requirements.txt
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8000
```

浏览器打开：`http://127.0.0.1:8000/`

## 3) 让 dashboard 能读到状态

`BitgetLiveRunner` 会每分钟写一份快照到：
- `state/live_status.json`

如果你看不到数据，确认服务器上的 `taoquant` 目录下能创建 `state/` 目录。

## （可选）启用控制能力（未来你需要时再开）

如果你以后想让 Dashboard 也能“启停服务/应用配置版本”，可以在云服务器上显式开启：

```bash
export TAOQUANT_ENABLE_CONTROL=1
export TAOQUANT_SERVICE_NAME=taoquant.service
```

默认不设置 `TAOQUANT_ENABLE_CONTROL` 时，Dashboard 为**只读监控**。

## 5) 安全（强烈建议）

设置一个 token（开启后所有 API 都需要 Bearer token）：

```bash
export TAOQUANT_DASHBOARD_TOKEN="replace-with-strong-token"
```

然后前端（或 curl）请求时带：

```
Authorization: Bearer <token>
```

（当前内置 HTML demo 没有带 token；如果你开启了 token，建议先放到反向代理（nginx）里做 BasicAuth 或者我们下一步把前端升级为正式 React 并支持 token。）

## 6) 下一步（你说 PnL/风险更重要）

我建议下一步把面板完善成两页：
1. **PnL/风险页（默认页）**：权益、unreal/realized、risk_level、grid_enabled、区间偏离、最大回撤等
2. **执行稳定性页**：最近 1h 订单失败数、成交延迟、API 报错、LEDGER_DRIFT 告警


