"""
TaoGrid 分段寻优（BTC） - 基于手工 S/R 分段 + stress regime 约束。

目标：
- 多目标：同时追求高 ROE 与高 Sharpe
- 防止“伪优”：加入交易频率下限与成本敏感的离散参数空间
- 分段评估：不同 market regimes 分别回测，再做稳健聚合

用法：
  python run/taogrid_segmented_optimize_btc.py

输出：
  run/results_lean_taogrid_segmented_opt_btc/segmented_summary.csv
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import sys
from typing import Any

import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from data import DataManager


UTC = timezone.utc


@dataclass(frozen=True)
class Segment:
    name: str
    start: datetime
    end: datetime  # end is exclusive
    support: float
    resistance: float
    is_stress: bool = False

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0


def _dt(date_str: str) -> datetime:
    # date_str: "YYYY-MM-DD"
    return datetime.fromisoformat(date_str).replace(tzinfo=UTC)


def _next_day(dt_: datetime) -> datetime:
    # end-exclusive helper for day-level slicing
    return (dt_.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(UTC)


def get_btc_segments() -> list[Segment]:
    """
    BTC 手工分段（互不重叠，end-exclusive）。

    注意：用户给的是自然日区间，这里统一采用 [start, end_next_day) 口径。
    """
    segments = [
        Segment(
            name="A1_pre_range",
            start=_dt("2025-07-10"),
            end=_next_day(_dt("2025-07-14")),
            support=107_000.0,
            resistance=123_000.0,
        ),
        Segment(
            name="A2_main_range_narrow",
            start=_dt("2025-07-15"),
            end=_next_day(_dt("2025-07-31")),
            support=116_000.0,
            resistance=123_000.0,
        ),
        Segment(
            name="A3_range_wide",
            start=_dt("2025-08-01"),
            end=_next_day(_dt("2025-08-14")),
            support=107_000.0,
            resistance=123_000.0,
        ),
        Segment(
            name="B_mixed",
            start=_dt("2025-08-15"),
            end=_next_day(_dt("2025-10-08")),
            support=107_000.0,
            resistance=123_000.0,
        ),
        Segment(
            name="C_stress_1011",
            start=_dt("2025-10-09"),
            end=_next_day(_dt("2025-10-13")),
            support=120_000.0,
            resistance=126_000.0,
            is_stress=True,
        ),
        Segment(
            name="D_post_stress_rebalance",
            start=_dt("2025-10-14"),
            end=_next_day(_dt("2025-11-02")),
            support=107_000.0,
            resistance=116_000.0,
        ),
        Segment(
            name="E_downtrend_range1",
            start=_dt("2025-11-03"),
            end=_next_day(_dt("2025-11-17")),  # align with F start at 11/18
            support=94_000.0,
            resistance=108_000.0,
        ),
        Segment(
            name="F_downtrend_range2",
            start=_dt("2025-11-18"),
            end=_next_day(_dt("2025-12-14")),
            support=80_000.0,
            resistance=94_000.0,
        ),
    ]
    # Basic sanity checks
    for s in segments:
        if s.support >= s.resistance:
            raise ValueError(f"Invalid S/R in segment {s.name}: support >= resistance")
        if s.start >= s.end:
            raise ValueError(f"Invalid time range in segment {s.name}: start >= end")
    # Ensure non-overlap (sorted by start)
    seg_sorted = sorted(segments, key=lambda x: x.start)
    for prev, cur in zip(seg_sorted, seg_sorted[1:]):
        if prev.end > cur.start:
            raise ValueError(f"Segments overlap: {prev.name} end={prev.end} > {cur.name} start={cur.start}")
    return seg_sorted


def _annualize_return(total_return: float, days: float) -> float:
    if days <= 0:
        return 0.0
    # Stable for small returns as well.
    return (1.0 + float(total_return)) ** (365.0 / days) - 1.0


def fetch_klines_chunked(
    dm: DataManager,
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    source: str,
    chunk_days: int = 20,
) -> pd.DataFrame:
    """
    OKX 分钟线跨度太大时，单次拉取容易超时/缺数据；这里按天分块拉取并拼接。

    返回：覆盖 [start, end) 的完整 DataFrame（尽量无重复）。
    """
    if chunk_days <= 0:
        raise ValueError("chunk_days must be > 0")

    frames: list[pd.DataFrame] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        # simple retry-once for network flakiness
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                df = dm.get_klines(
                    symbol=symbol,
                    timeframe=timeframe,
                    start=cur,
                    end=nxt,
                    source=source,
                )
                frames.append(df)
                last_exc = None
                break
            except Exception as e:  # noqa: BLE001 (keep script robust)
                last_exc = e
        if last_exc is not None:
            raise last_exc
        cur = nxt

    if not frames:
        raise ValueError("No data fetched")

    full = pd.concat(frames, axis=0).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    return full


def _segment_metrics_to_row(seg: Segment, metrics: dict) -> dict[str, Any]:
    total_return = float(metrics.get("total_return", 0.0))
    max_dd = float(metrics.get("max_drawdown", 0.0))
    sharpe = float(metrics.get("sharpe_ratio", 0.0))
    total_trades = int(metrics.get("total_trades", 0))
    trades_per_day = (total_trades / seg.days) if seg.days > 0 else 0.0
    ann_ret = _annualize_return(total_return=total_return, days=seg.days)
    return {
        "segment": seg.name,
        "is_stress": bool(seg.is_stress),
        "start": seg.start.isoformat(),
        "end": seg.end.isoformat(),
        "days": seg.days,
        "support": seg.support,
        "resistance": seg.resistance,
        "total_return": total_return,
        "annualized_return": ann_ret,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "total_trades": total_trades,
        "trades_per_day": trades_per_day,
    }


def evaluate_config_on_segments(
    base_config: TaoGridLeanConfig,
    symbol: str,
    timeframe: str,
    segments: list[Segment],
    *,
    full_data: pd.DataFrame | None = None,
    output_dir: Path | None = None,
    save_top_level: bool = False,
) -> dict[str, Any]:
    """
    对一个 config 在多个分段上分别回测，并输出聚合评分。

    这里默认不保存每段的明细文件（避免寻优产生海量 CSV），仅在需要时保存 Top 配置。
    """
    seg_rows: list[dict[str, Any]] = []
    total_days = sum(s.days for s in segments)

    # Constraints / sanity gates
    # - 对“震荡/混合”段要求更高交易活跃度（避免伪优）
    # - 对“下跌段”更像是尾部风险约束：不强制高交易数（长期做多网格在下跌段很难完成闭环）
    active_segments = {
        "A1_pre_range",
        "A2_main_range_narrow",
        "A3_range_wide",
        "B_mixed",
        "D_post_stress_rebalance",
    }

    min_trades_per_day_active = 2.0
    min_trades_per_day_stress = 1.0
    stress_max_dd_floor = -0.35  # stress 段允许更深，但不能崩；后续可调
    downtrend_max_dd_floor = -0.35  # 下跌段尾部风控（先放宽，后续可收紧）

    violated = False
    violation_reasons: list[str] = []

    for seg in segments:
        cfg = replace(
            base_config,
            support=float(seg.support),
            resistance=float(seg.resistance),
        )

        runner = SimpleLeanRunner(
            config=cfg,
            symbol=symbol,
            timeframe=timeframe,
            start_date=seg.start,
            end_date=seg.end,
            data=full_data,
            output_dir=(output_dir / seg.name) if (save_top_level and output_dir is not None) else None,
            verbose=False,
            progress_every=50_000,
            collect_equity_detail=False,
        )

        results = runner.run()
        metrics = results["metrics"]

        # Optionally persist only for top configs
        if save_top_level and output_dir is not None:
            runner.save_results(results, output_dir / seg.name)

        row = _segment_metrics_to_row(seg, metrics)
        seg_rows.append(row)

        # Hard constraints
        tpd = float(row["trades_per_day"])
        mdd = float(row["max_drawdown"])
        if seg.is_stress:
            if tpd < min_trades_per_day_stress:
                violated = True
                violation_reasons.append(f"stress_low_trades({seg.name} tpd={tpd:.2f})")
            if mdd < stress_max_dd_floor:
                violated = True
                violation_reasons.append(f"stress_dd_too_deep({seg.name} mdd={mdd:.2%})")
        elif seg.name in active_segments:
            if tpd < min_trades_per_day_active:
                violated = True
                violation_reasons.append(f"low_trades({seg.name} tpd={tpd:.2f})")
        else:
            # Downtrend segments: do not force high churn, only enforce tail-risk sanity.
            if mdd < downtrend_max_dd_floor:
                violated = True
                violation_reasons.append(f"downtrend_dd_too_deep({seg.name} mdd={mdd:.2%})")

    seg_df = pd.DataFrame(seg_rows)

    # Aggregate (regime-robust): weighted by segment length
    # ROE proxy: annualized_return; risk-adjusted: sharpe_ratio (already annualized at daily freq)
    w = seg_df["days"] / total_days if total_days > 0 else 0.0
    w = w.fillna(0.0)

    # Clip Sharpe to avoid short-sample blow-ups dominating the score
    sharpe_clipped = seg_df["sharpe_ratio"].clip(lower=-5.0, upper=8.0)
    w_sharpe = float((sharpe_clipped * w).sum())
    w_ann_ret = float((seg_df["annualized_return"] * w).sum())
    worst_non_stress_ann = float(seg_df.loc[~seg_df["is_stress"], "annualized_return"].min()) if (~seg_df["is_stress"]).any() else float(seg_df["annualized_return"].min())
    worst_non_stress_sharpe = float(seg_df.loc[~seg_df["is_stress"], "sharpe_ratio"].min()) if (~seg_df["is_stress"]).any() else float(seg_df["sharpe_ratio"].min())
    stress_mdd = float(seg_df.loc[seg_df["is_stress"], "max_drawdown"].min()) if (seg_df["is_stress"]).any() else 0.0

    # Score: emphasize Sharpe + ROE, but enforce robustness via worst-segment terms
    score = (
        1.0 * w_sharpe
        + 0.25 * w_ann_ret
        + 0.5 * worst_non_stress_sharpe
        + 0.10 * worst_non_stress_ann
    )
    if violated:
        score -= 10.0  # hard gate penalty (keeps sorting simple)

    return {
        "score": float(score),
        "violated": bool(violated),
        "violation_reasons": "|".join(violation_reasons),
        "weighted_sharpe": w_sharpe,
        "weighted_annualized_return": w_ann_ret,
        "worst_non_stress_annualized_return": worst_non_stress_ann,
        "worst_non_stress_sharpe": worst_non_stress_sharpe,
        "stress_max_drawdown": stress_mdd,
        "segments": seg_df,
    }


def sample_param_configs(
    base: TaoGridLeanConfig,
    n: int,
    seed: int,
) -> list[TaoGridLeanConfig]:
    """
    随机采样一个“有意义的离散参数空间”，避免无意义的小数精确化。
    """
    rng = random.Random(seed)

    # Meaningful discrete sets (bps-level granularity)
    # With maker_fee=2bps per side, round-trip fees are ~4bps. We keep min_return >= 5bps.
    min_returns = [0.0005, 0.0008, 0.0012, 0.0016]  # 5/8/12/16 bps net
    grid_layers = [20, 30, 40, 60, 80]
    weight_ks = [0.0, 0.2, 0.5]
    risk_budgets = [0.3, 0.6, 1.0]
    leverages = [10.0, 20.0, 50.0]
    inventory_skews = [0.0, 0.5, 1.0]

    cfgs: list[TaoGridLeanConfig] = []
    for _ in range(int(n)):
        gl = int(rng.choice(grid_layers))
        cfgs.append(
            replace(
                base,
                min_return=float(rng.choice(min_returns)),
                grid_layers_buy=gl,
                grid_layers_sell=gl,
                weight_k=float(rng.choice(weight_ks)),
                risk_budget_pct=float(rng.choice(risk_budgets)),
                leverage=float(rng.choice(leverages)),
                inventory_skew_k=float(rng.choice(inventory_skews)),
            )
        )
    return cfgs


def main() -> None:
    segments = get_btc_segments()
    full_start = min(s.start for s in segments)
    full_end = max(s.end for s in segments)

    # Preload full OHLCV once to avoid repeated API calls/timeouts in sweeps.
    dm = DataManager()
    full_data = fetch_klines_chunked(
        dm,
        symbol="BTCUSDT",
        timeframe="1m",
        start=full_start,
        end=full_end,
        source="okx",
        chunk_days=20,
    )

    # Baseline config: keep current cost model defaults; start from reasonably active grid.
    base_config = TaoGridLeanConfig(
        name="TaoGrid Segmented Optimize (BTC)",
        description="Segmented regime optimization for BTC (manual S/R)",
        support=107_000.0,
        resistance=123_000.0,
        regime="NEUTRAL_RANGE",
        maker_fee=0.0002,
        volatility_k=0.6,
        cushion_multiplier=0.8,
        atr_period=14,
        enable_throttling=True,
        initial_cash=100_000.0,
        enable_console_log=False,
        # Keep MM risk zone ON: this is real behavior; we already fixed auto re-enable.
        enable_mm_risk_zone=True,
        # Keep factors at default (can extend in stage2 later)
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=False,
        enable_mr_trend_factor=True,
        # Disable funding during optimization to avoid external API dependence; can re-enable later.
        enable_funding_factor=False,
        enable_vol_regime_factor=True,
        # Structure defaults (will be sampled)
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        weight_k=0.2,
        spacing_multiplier=1.0,
        risk_budget_pct=0.6,
        leverage=20.0,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=0.9,
    )

    out_root = Path("run/results_lean_taogrid_segmented_opt_btc")
    out_root.mkdir(parents=True, exist_ok=True)

    # Stage 0: baseline evaluation
    baseline_eval = evaluate_config_on_segments(
        base_config,
        symbol="BTCUSDT",
        timeframe="1m",
        segments=segments,
        full_data=full_data,
        output_dir=out_root / "baseline",
        save_top_level=True,
    )
    baseline_eval["segments"].to_csv(out_root / "baseline_segments.csv", index=False)

    # Stage 1: random sampling (fast shortlist)
    seed = 42
    n_samples = 60  # keep modest; we can scale after validating speed
    cfgs = sample_param_configs(base_config, n=n_samples, seed=seed)

    rows: list[dict[str, Any]] = []

    # Fast shortlist segments: focus on core + stress + post-stress regime
    key_seg_names = {"A2_main_range_narrow", "B_mixed", "C_stress_1011", "D_post_stress_rebalance"}
    key_segments = [s for s in segments if s.name in key_seg_names]

    for i, cfg in enumerate(cfgs, start=1):
        eval_key = evaluate_config_on_segments(
            cfg,
            symbol="BTCUSDT",
            timeframe="1m",
            segments=key_segments,
            full_data=full_data,
            output_dir=None,
            save_top_level=False,
        )

        rows.append(
            {
                "run_id": i,
                "stage": "key_segments",
                "score": eval_key["score"],
                "violated": eval_key["violated"],
                "violation_reasons": eval_key["violation_reasons"],
                "weighted_sharpe": eval_key["weighted_sharpe"],
                "weighted_annualized_return": eval_key["weighted_annualized_return"],
                "worst_non_stress_sharpe": eval_key["worst_non_stress_sharpe"],
                "worst_non_stress_annualized_return": eval_key["worst_non_stress_annualized_return"],
                "stress_max_drawdown": eval_key["stress_max_drawdown"],
                # params
                "min_return": cfg.min_return,
                "grid_layers": cfg.grid_layers_buy,
                "weight_k": cfg.weight_k,
                "risk_budget_pct": cfg.risk_budget_pct,
                "leverage": cfg.leverage,
                "inventory_skew_k": cfg.inventory_skew_k,
            }
        )

    df_key = pd.DataFrame(rows).sort_values(by="score", ascending=False)
    df_key.to_csv(out_root / "stage1_key_segments_summary.csv", index=False)

    # Stage 1b: re-evaluate top-K on ALL segments and save only top results
    top_k = 8
    top_cfg_rows = df_key.head(top_k).to_dict(orient="records")

    rows_full: list[dict[str, Any]] = []
    for rank, row in enumerate(top_cfg_rows, start=1):
        cfg = replace(
            base_config,
            min_return=float(row["min_return"]),
            grid_layers_buy=int(row["grid_layers"]),
            grid_layers_sell=int(row["grid_layers"]),
            weight_k=float(row["weight_k"]),
            risk_budget_pct=float(row["risk_budget_pct"]),
            leverage=float(row["leverage"]),
            inventory_skew_k=float(row["inventory_skew_k"]),
        )

        run_dir = out_root / "top_configs" / f"rank_{rank:02d}"
        eval_full = evaluate_config_on_segments(
            cfg,
            symbol="BTCUSDT",
            timeframe="1m",
            segments=segments,
            full_data=full_data,
            output_dir=run_dir,
            save_top_level=True,
        )
        eval_full["segments"].to_csv(run_dir / "segments.csv", index=False)

        rows_full.append(
            {
                "rank": rank,
                "score": eval_full["score"],
                "violated": eval_full["violated"],
                "violation_reasons": eval_full["violation_reasons"],
                "weighted_sharpe": eval_full["weighted_sharpe"],
                "weighted_annualized_return": eval_full["weighted_annualized_return"],
                "worst_non_stress_sharpe": eval_full["worst_non_stress_sharpe"],
                "worst_non_stress_annualized_return": eval_full["worst_non_stress_annualized_return"],
                "stress_max_drawdown": eval_full["stress_max_drawdown"],
                # params
                "min_return": cfg.min_return,
                "grid_layers_buy": cfg.grid_layers_buy,
                "grid_layers_sell": cfg.grid_layers_sell,
                "weight_k": cfg.weight_k,
                "risk_budget_pct": cfg.risk_budget_pct,
                "leverage": cfg.leverage,
                "inventory_skew_k": cfg.inventory_skew_k,
                "output_dir": str(run_dir),
            }
        )

    df_full = pd.DataFrame(rows_full).sort_values(by="score", ascending=False)
    df_full.to_csv(out_root / "segmented_summary.csv", index=False)

    print("Baseline saved to:", str(out_root / "baseline"))
    print("Stage1 key-segments summary:", str(out_root / "stage1_key_segments_summary.csv"))
    print("Final segmented summary:", str(out_root / "segmented_summary.csv"))


if __name__ == "__main__":
    main()

