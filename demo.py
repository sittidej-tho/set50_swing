#!/usr/bin/env python3
"""Demo runner — synthesises realistic OHLCV for SET50 and runs the engine.

Use this when you want to preview the dashboard without internet access,
or to sanity-check the strategy logic. The signals it produces are
illustrative only — real trading decisions should use `run_weekly.py`
which pulls live yfinance data.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import REPORTS_DIR, SET50_TICKERS, BENCHMARK_TICKER
from src.dashboard import render
from src.data import split_universe
from src.strategy import score_universe


def _synth_one(seed: int, n: int = 520, start_price: float = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    drift = rng.uniform(-0.0006, 0.0010)              # daily drift
    vol = rng.uniform(0.012, 0.030)                   # daily vol
    s0 = start_price or rng.uniform(8, 350)
    # add a regime change ~70% in to create varied trends
    regime_idx = int(n * rng.uniform(0.4, 0.85))
    drift_late = drift + rng.uniform(-0.0015, 0.0015)
    rets = np.concatenate([
        rng.normal(drift,       vol, regime_idx),
        rng.normal(drift_late,  vol, n - regime_idx),
    ])
    # occasional gap days
    rets[rng.choice(n, size=4, replace=False)] += rng.normal(0, 0.04, 4)
    close = s0 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.008, n)))
    low  = close * (1 - np.abs(rng.normal(0, 0.008, n)))
    open_ = (high + low) / 2
    vol_avg = rng.uniform(2e6, 3e7)
    volume = (rng.lognormal(0, 0.4, n) * vol_avg).astype(np.int64)
    dates = pd.bdate_range(end=dt.date.today(), periods=n)
    return pd.DataFrame({
        "Date": dates, "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume,
    })


def build_synth_prices() -> pd.DataFrame:
    rows = []
    for i, tkr in enumerate(SET50_TICKERS):
        df = _synth_one(seed=42 + i)
        df["Ticker"] = tkr
        rows.append(df)
    bench = _synth_one(seed=7, start_price=1500)
    bench["Ticker"] = BENCHMARK_TICKER
    rows.append(bench)
    out = pd.concat(rows, ignore_index=True)[
        ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]]
    return out


def main() -> int:
    print("» Building synthetic SET50 history (this is a DEMO)…")
    prices = build_synth_prices()
    by_t, bench = split_universe(prices)
    print(f"  {len(by_t)} tickers, "
          f"benchmark rows: {len(bench)}, "
          f"latest: {prices['Date'].max().date()}")

    print("» Scoring universe…")
    signals = score_universe(by_t, bench)

    summary: dict[str, int] = {}
    for s in signals:
        summary[s.action] = summary.get(s.action, 0) + 1
    print("\nDemo signal mix:", summary)

    out = render(signals)
    csv = REPORTS_DIR / "signals.csv"
    pd.DataFrame([{
        "ticker": s.ticker, "action": s.action, "score": s.score,
        "price": s.price, "stop": s.stop, "target": s.target,
        **s.factors, **{f"snap_{k}": v for k, v in s.snapshot.items()},
        "rationale": s.rationale,
    } for s in signals]).to_csv(csv, index=False)
    print(f"\n✓ Dashboard preview : {out}")
    print(f"✓ Demo signals CSV  : {csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
