#!/usr/bin/env python3
"""Run a walk-forward backtest of the SET50 swing strategy.

Usage
-----
    python run_backtest.py                          # live yfinance
    python run_backtest.py --demo                   # synthetic prices (offline)
    python run_backtest.py --start 2022-01-03 --capital 2000000
    python run_backtest.py --no-stops               # disable intraday ATR stops

Outputs
-------
    reports/backtest.html  – interactive backtest report
    reports/trades.csv     – per-trade log
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.backtest import BTConfig, run_backtest
from src.backtest_report import render
from src.config import REPORTS_DIR, PARAMS
from src.data import fetch_prices, split_universe


def _load_demo() -> tuple[dict, pd.DataFrame]:
    # Generate ~5 years of synthetic SET50 history for an offline backtest.
    from demo import build_synth_prices                   # type: ignore
    from src.data import split_universe as _split

    # Patch demo's _synth_one length via monkey-patch on the function default.
    import demo as _d
    orig = _d._synth_one
    def _bigger(*a, **kw):
        kw.setdefault("n", 1300)                          # ~5 trading years
        return orig(*a, **kw)
    _d._synth_one = _bigger
    try:
        prices = build_synth_prices()
    finally:
        _d._synth_one = orig
    return _split(prices)


def _load_live(force: bool) -> tuple[dict, pd.DataFrame]:
    # Bump lookback to give the backtest more history.
    PARAMS_obj = PARAMS
    object.__setattr__(PARAMS_obj, "lookback_days", max(PARAMS.lookback_days, 1500))
    prices = fetch_prices(force=force)
    return split_universe(prices)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true",
                   help="run on synthetic prices (offline, illustrative only)")
    p.add_argument("--force", action="store_true", help="ignore the price cache")
    p.add_argument("--start", default="2023-01-02", help="first scan day (YYYY-MM-DD)")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--max-positions", type=int, default=8)
    p.add_argument("--max-pos-pct", type=float, default=0.15)
    p.add_argument("--no-stops", action="store_true",
                   help="disable intraday ATR stop checks")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level="INFO" if args.verbose else "WARNING",
                        format="%(message)s", stream=sys.stdout)

    if args.demo:
        print("» Loading synthetic SET50 history (DEMO)…")
        by_t, bench = _load_demo()
    else:
        print("» Fetching prices…")
        by_t, bench = _load_live(args.force)

    print(f"  {len(by_t)} tickers, benchmark rows: {len(bench)}")

    cfg = BTConfig(
        start_date=args.start,
        starting_capital=args.capital,
        max_positions=args.max_positions,
        max_position_pct=args.max_pos_pct,
        use_stops=not args.no_stops,
    )
    print(f"» Running backtest from {cfg.start_date} with ฿{cfg.starting_capital:,.0f}…")
    res = run_backtest(by_t, bench, cfg)

    # Print summary.
    s = res.stats
    print()
    print(f"  Total return  : {s['total_return_pct']:+.2f}%   "
          f"(SET buy-hold: {s['benchmark_return_pct']:+.2f}%   "
          f"alpha: {s['alpha_vs_set_pct']:+.2f}%)")
    print(f"  CAGR          : {s['cagr_pct']:+.2f}%")
    print(f"  Max drawdown  : {s['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe        : {s['sharpe']:.2f}")
    print(f"  Trades        : {s['n_trades']}   "
          f"win rate {s['win_rate_pct']:.1f}%   "
          f"avg P&L {s['avg_pnl_pct']:+.2f}%")
    print(f"  Final equity  : ฿{s['final_equity']:,.0f}")

    out = render(res)
    csv = REPORTS_DIR / "trades.csv"
    if len(res.trades):
        res.trades.to_csv(csv, index=False)
        print(f"\n✓ Backtest report : {out}")
        print(f"✓ Trade log       : {csv}")
    else:
        print(f"\n✓ Backtest report : {out}  (no trades — try a longer window)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
