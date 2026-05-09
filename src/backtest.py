"""Walk-forward backtest harness for the SET50 swing-trade strategy.

Design
------
* Cadence:   weekly Friday close → execute at next Monday's open
* Sizing:    equal-weight up to ``cfg.max_positions``, capped per-name at
             ``cfg.max_position_pct`` of total equity
* Exits:     SELL-STRONG / CUT / TRIM signals act on next bar's open;
             ATR stop-loss is checked daily on intraday Low (optional)
* Costs:     round-trip ``cost_bps`` + one-way ``slippage_bps``
* Benchmark: buy-and-hold of the SET index over the same window

The backtest pre-enriches all tickers once (full history) and then walks
forward through trading days, so signal generation is O(rebalance × names)
rather than O(rebalance × names × history).
"""

from __future__ import annotations

import dataclasses as dc
from dataclasses import dataclass, field
import datetime as dt
import logging
from typing import Optional

import numpy as np
import pandas as pd

from .config import PARAMS, StrategyParams
from .indicators import enrich
from .strategy import (
    _decide, _safe, mean_reversion_score, momentum_score,
    relative_strength_score, trend_score, volume_score,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config & result types
# ---------------------------------------------------------------------------
@dataclass
class BTConfig:
    start_date:      str   = "2023-01-02"   # first scan day (warmup happens before)
    starting_capital: float = 1_000_000.0
    max_positions:   int   = 8
    max_position_pct: float = 0.15
    cost_bps:        float = 15.0          # round-trip
    slippage_bps:    float = 5.0           # one-way
    use_stops:       bool  = True
    trim_fraction:   float = 0.5
    cut_fraction:    float = 0.7           # leave a 30% starter on CUT
    rebalance_dow:   int   = 4             # 0=Mon … 4=Fri


@dataclass
class Trade:
    ticker:      str
    entry_action: str
    open_date:   str
    open_price:  float
    close_date:  str
    close_price: float
    size_thb:    float
    pnl_thb:     float
    pnl_pct:     float
    reason:      str       # TRIM / CUT / SELL-STRONG / STOP / EOH


@dataclass
class BTResult:
    equity_curve:    pd.DataFrame   # index=date, cols=equity, cash, holdings, dd, n_pos
    benchmark_curve: pd.Series      # SET buy-hold normalised to starting capital
    trades:          pd.DataFrame
    monthly_returns: pd.Series      # %, end of month
    stats:           dict[str, float]
    by_action:       dict[str, dict]
    config:          BTConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_score(row: pd.Series, p: StrategyParams) -> tuple[float, dict, str]:
    factors = {
        "trend":          trend_score(row, p),
        "momentum":       momentum_score(row, p),
        "mean_reversion": mean_reversion_score(row, p),
        "relative_str":   relative_strength_score(row, p),
        "volume":         volume_score(row, p),
    }
    composite = sum(p.weights[k] * v for k, v in factors.items())
    action = _decide(composite, row, p)
    return composite, factors, action


def _atr_stop(row: pd.Series, p: StrategyParams) -> float:
    px  = float(row["Close"])
    atr = _safe(row.get("atr"), px * 0.02)
    return px - p.atr_stop_mult * atr


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def run_backtest(by_ticker: dict[str, pd.DataFrame],
                 bench: pd.DataFrame,
                 cfg: BTConfig = BTConfig(),
                 params: StrategyParams = PARAMS) -> BTResult:
    if not by_ticker:
        raise ValueError("Empty universe")

    # Pre-enrich every ticker once.
    bench_close = (bench["Close"] if not bench.empty
                   else pd.Series(1.0, index=next(iter(by_ticker.values())).index))
    enriched: dict[str, pd.DataFrame] = {}
    for tkr, df in by_ticker.items():
        e = enrich(df, params, bench_close)
        e["ret_1d"] = e["Close"].pct_change() * 100
        enriched[tkr] = e

    # Master trading-day index (union of all tickers).
    all_dates = pd.DatetimeIndex(sorted(set().union(
        *[df.index for df in enriched.values()])))
    start_ts = pd.Timestamp(cfg.start_date)
    sim_dates = all_dates[all_dates >= start_ts]
    if len(sim_dates) < 30:
        raise ValueError(f"Only {len(sim_dates)} days after {cfg.start_date}; "
                         "need a longer price history.")

    rebal_set = {d for d in sim_dates if d.dayofweek == cfg.rebalance_dow}
    log.info("Backtest %s → %s, %d trading days, %d weekly rebalances",
             sim_dates[0].date(), sim_dates[-1].date(),
             len(sim_dates), len(rebal_set))

    cost = cfg.cost_bps / 10_000.0
    slip = cfg.slippage_bps / 10_000.0

    cash = cfg.starting_capital
    positions: dict[str, dict] = {}
    trades: list[Trade] = []
    rows: list[dict] = []

    sim_dates_list = list(sim_dates)
    for i, d in enumerate(sim_dates_list):
        # ------- (1) mark-to-market & intra-day stop check ----------------
        holdings = 0.0
        for tkr in list(positions.keys()):
            edf = enriched[tkr]
            if d not in edf.index:
                continue
            bar = edf.loc[d]
            px  = float(bar["Close"])
            pos = positions[tkr]
            if cfg.use_stops and pos.get("stop") and bar["Low"] <= pos["stop"]:
                exit_px = float(pos["stop"]) * (1 - slip)
                proceeds = pos["shares"] * exit_px
                cash += proceeds * (1 - cost)
                pnl_thb = proceeds - pos["entry_value"]
                trades.append(Trade(
                    ticker=tkr, entry_action=pos["entry_action"],
                    open_date=str(pos["entry_date"]), open_price=pos["entry_price"],
                    close_date=str(d.date()), close_price=exit_px,
                    size_thb=pos["entry_value"], pnl_thb=pnl_thb,
                    pnl_pct=pnl_thb / pos["entry_value"] * 100,
                    reason="STOP",
                ))
                del positions[tkr]
            else:
                holdings += pos["shares"] * px

        # ------- (2) weekly rebalance -------------------------------------
        if d in rebal_set:
            # Score every name on day d.
            day_scores: list[tuple[str, float, str, pd.Series]] = []
            for tkr, edf in enriched.items():
                if d not in edf.index:
                    continue
                row = edf.loc[d]
                if pd.isna(row.get(f"ema{params.ema_slow}")):
                    continue
                composite, _factors, action = _row_score(row, params)
                day_scores.append((tkr, composite, action, row))
            sig_by = {t: (s, a, r) for t, s, a, r in day_scores}

            next_d = sim_dates_list[i + 1] if i + 1 < len(sim_dates_list) else None

            # ----- exits/trims for held names -----
            if next_d is not None:
                for tkr in list(positions.keys()):
                    if tkr not in sig_by:
                        continue
                    _score, action, _row = sig_by[tkr]
                    if action not in ("SELL-STRONG", "CUT", "TRIM"):
                        continue
                    edf = enriched[tkr]
                    if next_d not in edf.index:
                        continue
                    exec_px = float(edf.loc[next_d, "Open"]) * (1 - slip)
                    pos = positions[tkr]
                    frac = (cfg.trim_fraction if action == "TRIM"
                            else cfg.cut_fraction if action == "CUT" else 1.0)
                    sell_shares = pos["shares"] * frac
                    sold_value  = pos["entry_value"] * frac
                    proceeds    = sell_shares * exec_px
                    cash += proceeds * (1 - cost)
                    pnl_thb = proceeds - sold_value
                    trades.append(Trade(
                        ticker=tkr, entry_action=pos["entry_action"],
                        open_date=str(pos["entry_date"]), open_price=pos["entry_price"],
                        close_date=str(next_d.date()), close_price=exec_px,
                        size_thb=sold_value, pnl_thb=pnl_thb,
                        pnl_pct=pnl_thb / sold_value * 100,
                        reason=action,
                    ))
                    pos["shares"]      -= sell_shares
                    pos["entry_value"] -= sold_value
                    if pos["shares"] <= 1e-9 or action == "SELL-STRONG":
                        del positions[tkr]

            # ----- new entries -----
            if next_d is not None:
                slots = max(0, cfg.max_positions - len(positions))
                if slots > 0:
                    buys = [(t, s, r) for t, (s, a, r) in sig_by.items()
                            if a in ("BUY-STRONG", "BUY-DIP") and t not in positions]
                    buys.sort(key=lambda x: -x[1])
                    for tkr, _score, row in buys[:slots]:
                        edf = enriched[tkr]
                        if next_d not in edf.index:
                            continue
                        exec_px = float(edf.loc[next_d, "Open"]) * (1 + slip)
                        equity_now = cash + holdings
                        target = min(equity_now * cfg.max_position_pct,
                                     equity_now / cfg.max_positions * 1.5)
                        target = max(0.0, min(target, cash / (1 + cost)))
                        if target < 1_000:
                            continue
                        shares = target / exec_px
                        cash -= target * (1 + cost)
                        positions[tkr] = {
                            "shares":       shares,
                            "entry_price":  exec_px,
                            "entry_value":  target,
                            "entry_date":   next_d.date(),
                            "entry_action": ("BUY-STRONG" if _score >= params.score_buy_strong
                                             else "BUY-DIP"),
                            "stop":         _atr_stop(row, params),
                        }

        # ------- (3) record equity ----------------------------------------
        equity = cash + sum(
            pos["shares"] * float(enriched[t].loc[d, "Close"])
            for t, pos in positions.items() if d in enriched[t].index
        )
        rows.append({"date": d, "equity": equity, "cash": cash,
                     "holdings": equity - cash, "n_pos": len(positions)})

    # End-of-history: close remaining positions at last close.
    last_d = sim_dates_list[-1]
    for tkr, pos in list(positions.items()):
        edf = enriched[tkr]
        if last_d not in edf.index:
            continue
        px = float(edf.loc[last_d, "Close"])
        proceeds = pos["shares"] * px
        cash += proceeds * (1 - cost)
        pnl_thb = proceeds - pos["entry_value"]
        trades.append(Trade(
            ticker=tkr, entry_action=pos["entry_action"],
            open_date=str(pos["entry_date"]), open_price=pos["entry_price"],
            close_date=str(last_d.date()), close_price=px,
            size_thb=pos["entry_value"], pnl_thb=pnl_thb,
            pnl_pct=pnl_thb / pos["entry_value"] * 100, reason="EOH",
        ))

    eq = pd.DataFrame(rows).set_index("date").sort_index()
    eq["dd"] = (eq["equity"] / eq["equity"].cummax() - 1) * 100

    # Benchmark buy-hold normalised to starting capital.
    if not bench_close.empty:
        b = bench_close.loc[bench_close.index >= eq.index[0]]
        bench_curve = (b / b.iloc[0]) * cfg.starting_capital
    else:
        bench_curve = pd.Series(dtype=float)

    trades_df = pd.DataFrame([dc.asdict(t) for t in trades])
    monthly = (eq["equity"].resample("ME").last().pct_change().dropna() * 100)

    # Aggregate stats.
    if len(eq):
        total_ret = eq["equity"].iloc[-1] / cfg.starting_capital - 1
        years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-6)
        cagr = (1 + total_ret) ** (1 / years) - 1
        daily = eq["equity"].pct_change().dropna()
        sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
        max_dd = float(eq["dd"].min())
    else:
        total_ret = cagr = sharpe = max_dd = 0.0

    bench_total_ret = (bench_curve.iloc[-1] / bench_curve.iloc[0] - 1) if len(bench_curve) else 0.0

    stats = {
        "total_return_pct":  round(total_ret * 100, 2),
        "cagr_pct":          round(cagr * 100, 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "sharpe":            round(sharpe, 2),
        "n_trades":          int(len(trades_df)),
        "win_rate_pct":      round((trades_df["pnl_pct"] > 0).mean() * 100, 1)
                              if len(trades_df) else 0.0,
        "avg_pnl_pct":       round(trades_df["pnl_pct"].mean(), 2)
                              if len(trades_df) else 0.0,
        "starting_capital":  cfg.starting_capital,
        "final_equity":      round(float(eq["equity"].iloc[-1]), 2) if len(eq) else 0.0,
        "benchmark_return_pct": round(bench_total_ret * 100, 2),
        "alpha_vs_set_pct":  round((total_ret - bench_total_ret) * 100, 2),
    }

    by_action: dict[str, dict] = {}
    if len(trades_df):
        for a, g in trades_df.groupby("entry_action"):
            by_action[a] = {
                "n":           int(len(g)),
                "win_rate":    round((g["pnl_pct"] > 0).mean() * 100, 1),
                "avg_pnl_pct": round(g["pnl_pct"].mean(), 2),
                "best_pct":    round(g["pnl_pct"].max(), 2),
                "worst_pct":   round(g["pnl_pct"].min(), 2),
            }
        for r, g in trades_df.groupby("reason"):
            by_action[f"exit:{r}"] = {
                "n":           int(len(g)),
                "win_rate":    round((g["pnl_pct"] > 0).mean() * 100, 1),
                "avg_pnl_pct": round(g["pnl_pct"].mean(), 2),
            }

    return BTResult(
        equity_curve=eq, benchmark_curve=bench_curve,
        trades=trades_df, monthly_returns=monthly,
        stats=stats, by_action=by_action, config=cfg,
    )
