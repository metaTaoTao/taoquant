## OKX 资金费率（Funding Rate）数据获取

### 能否通过 OKX API 获取？

可以。OKX 提供 **公开 REST API** 获取永续合约资金费率：
- **历史资金费率**：`/api/v5/public/funding-rate-history`
- **最新资金费率**：`/api/v5/public/funding-rate`

注意：OKX 公开接口通常只保留**有限的历史窗口**（更久远的资金费率可能无法通过 API 拉取）。
如果你要做很久以前的回测，建议：
- 使用 OKX 的 **历史数据下载**（网页数据中心）导出 funding 历史；或
- 在实盘/准实盘环境中定时拉取 funding 并落地到本地数据仓库。

### TaoQuant 里的用法（Data Layer）

我们把 funding 获取放在 data layer：`data/data_manager.py::DataManager.get_funding_rates()`。

示例：

```python
from datetime import datetime, timezone, timedelta
from data import DataManager

dm = DataManager()
end = datetime.now(timezone.utc)
start = end - timedelta(days=7)

# 返回 DataFrame：index=timestamp(UTC), column=["funding_rate"]
funding = dm.get_funding_rates(
    symbol="BTCUSDT",  # 会映射为 BTC-USDT-SWAP
    start=start,
    end=end,
    source="okx",
)
print(funding.tail())
```

### 如何对齐到 K 线（Runner/Orchestration 层做）

资金费率一般按 **8 小时**结算（也可能动态调整为 1 小时等），因此需要对齐到回测的 bar 时间轴：

```python
funding_aligned = funding.reindex(ohlcv.index, method="ffill").fillna(0.0)
```

原则：
- data layer 只负责“取到原始时间序列”
- 对齐/填充属于 runner/orchestration（避免策略层耦合外部 I/O）


