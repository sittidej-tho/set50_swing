#!/usr/bin/env python3
"""SET50 Swing-Trade weekly runner.

Usage
-----
    python run_weekly.py            # use cache if fresh, regenerate dashboard
    python run_weekly.py --force    # force re-download from yfinance
    python run_weekly.py --top 15   # only show top-15 highest-conviction names

Outputs
-------
    reports/dashboard.html   – interactive dashboard (open in browser)
    reports/signals.csv      – machine-readable signals table
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# allow running this file directly OR via -m
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import REPORTS_DIR
from src.dashboard import render
from src.data import fetch_prices, split_universe
from src.strategy import score_universe


ACTION_RANK = {
    "BUY-STRONG": 0, "BUY-DIP": 1, "HOLD": 2, "TRIM": 3, "CUT": 4, "SELL-STRONG": 5,
}


def _print_report(signals, top: int | None = None) -> None:
    rows = []
    for s in signals:
        rows.append({
            "Ticker": s.ticker.replace(".BK", ""),
            "Action": s.action,
            "Score":  f"{s.score:+.0f}",
            "Price":  f"{s.price:>7.2f}",
            "Stop":   f"{s.stop:>7.2f}",
            "Target": f"{s.target:>7.2f}",
            "Trend":  f"{s.factors['trend']:+4.0f}",
            "Mom":    f"{s.factors['momentum']:+4.0f}",
            "MR":     f"{s.factors['mean_reversion']:+4.0f}",
            "RS":     f"{s.factors['relative_str']:+4.0f}",
            "Vol":    f"{s.factors['volume']:+4.0f}",
            "RSI":    f"{s.snapshot['RSI']:>4.0f}",
            "%B":     f"{s.snapshot['%B']:>4.2f}",
            "DD1y":   f"{s.snapshot['DD_252']:+5.1f}%",
        })
    df = pd.DataFrame(rows)
    df["_rank"] = df["Action"].map(ACTION_RANK)
    df = df.sort_values(["_rank", "Score"], ascending=[True, False]).drop(columns="_rank")

    if top:
        df = df.head(top)

    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 200)
    print()
    print(df.to_string(index=False))
    print()
    by_action = df["Action"].value_counts()
    line = "  ·  ".join(f"{a}: {n}" for a, n in by_action.items())
    print(f"Summary  ▸  {line}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="ignore price cache")
    p.add_argument("--top", type=int, default=None,
                   help="print only top-N rows (still saves full csv/html)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level="INFO" if args.verbose else "WARNING",
        format="%(message)s", stream=sys.stdout,
    )

    print("» Fetching prices…")
    prices = fetch_prices(force=args.force)
    by_t, bench = split_universe(prices)
    print(f"  loaded {len(by_t)} tickers, "
          f"benchmark rows: {len(bench)}, "
          f"latest: {prices['Date'].max().date()}")

    print("» Scoring universe…")
    signals = score_universe(by_t, bench)

    # Sort signals like the printed table.
    signals.sort(key=lambda s: (ACTION_RANK[s.action], -s.score))
    _print_report(signals, args.top)

    # Persist artefacts.
    csv_path = REPORTS_DIR / "signals.csv"
    pd.DataFrame([{
        "ticker": s.ticker, "action": s.action, "score": s.score,
        "price": s.price, "stop": s.stop, "target": s.target,
        **s.factors, **{f"snap_{k}": v for k, v in s.snapshot.items()},
        "rationale": s.rationale,
    } for s in signals]).to_csv(csv_path, index=False)

    html_path = render(signals)
    print(f"\n✓ Dashboard : {html_path}")
    print(f"✓ Signals   : {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
