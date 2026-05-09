"""Data fetcher with on-disk cache.

Pulls daily OHLCV via yfinance for the SET50 universe + the SET benchmark.
Cache lives at `data/prices.parquet` (or .csv fallback) and is refreshed if
older than `cache_max_age_hours`.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import yfinance as yf
except ImportError as exc:                                 # pragma: no cover
    raise SystemExit(
        "yfinance is required. Install with:  pip install -r requirements.txt"
    ) from exc

from .config import (
    BENCHMARK_FALLBACK, BENCHMARK_TICKER, DATA_DIR, PARAMS, SET50_TICKERS,
)

log = logging.getLogger(__name__)


CACHE_PARQUET = DATA_DIR / "prices.parquet"
CACHE_CSV = DATA_DIR / "prices.csv"


def _to_long(df: pd.DataFrame) -> pd.DataFrame:
    """Convert yfinance multi-ticker frame -> tidy long format."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.stack(level=1, future_stack=True).rename_axis(["Date", "Ticker"]).reset_index()
    else:
        df = df.reset_index().assign(Ticker=df.columns.name or "UNKNOWN")
    df.columns = [str(c).strip() for c in df.columns]
    keep = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]
    df = df[[c for c in keep if c in df.columns]].dropna(subset=["Close"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    return df.sort_values(["Ticker", "Date"]).reset_index(drop=True)


def _download(tickers: Iterable[str], period_days: int) -> pd.DataFrame:
    end = dt.date.today() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=period_days)
    log.info("Downloading %s tickers from yfinance (%s → %s)…",
             len(list(tickers)), start, end)
    raw = yf.download(
        tickers=list(tickers),
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no data – check connectivity / tickers.")
    return _to_long(raw)


def fetch_prices(force: bool = False, cache_max_age_hours: int = 12) -> pd.DataFrame:
    """Return a tidy DataFrame: Date, Ticker, Open, High, Low, Close, Volume."""
    if not force and CACHE_PARQUET.exists():
        age_h = (time.time() - CACHE_PARQUET.stat().st_mtime) / 3600
        if age_h < cache_max_age_hours:
            log.info("Using cached prices (%.1fh old)", age_h)
            return pd.read_parquet(CACHE_PARQUET)
    if not force and CACHE_CSV.exists() and not CACHE_PARQUET.exists():
        age_h = (time.time() - CACHE_CSV.stat().st_mtime) / 3600
        if age_h < cache_max_age_hours:
            log.info("Using cached CSV prices (%.1fh old)", age_h)
            return pd.read_csv(CACHE_CSV, parse_dates=["Date"])

    universe = list(SET50_TICKERS) + [BENCHMARK_TICKER]
    try:
        df = _download(universe, PARAMS.lookback_days)
    except Exception as exc:                                # pragma: no cover
        log.warning("Primary download failed (%s); retrying without benchmark…", exc)
        df = _download(SET50_TICKERS, PARAMS.lookback_days)

    # Make sure benchmark exists; fall back if needed.
    if BENCHMARK_TICKER not in df["Ticker"].unique():
        try:
            log.info("Benchmark %s missing – falling back to %s",
                     BENCHMARK_TICKER, BENCHMARK_FALLBACK)
            fb = _download([BENCHMARK_FALLBACK], PARAMS.lookback_days)
            fb["Ticker"] = BENCHMARK_TICKER
            df = pd.concat([df, fb], ignore_index=True)
        except Exception as exc:                            # pragma: no cover
            log.warning("Benchmark fallback also failed: %s", exc)

    # Cache.
    try:
        df.to_parquet(CACHE_PARQUET, index=False)
    except Exception:                                       # pragma: no cover
        df.to_csv(CACHE_CSV, index=False)
    log.info("Fetched %s rows for %s tickers.",
             len(df), df["Ticker"].nunique())
    return df


def split_universe(prices: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return (per-ticker dict, benchmark frame)."""
    by_t: dict[str, pd.DataFrame] = {}
    bench = pd.DataFrame()
    for tkr, g in prices.groupby("Ticker", sort=False):
        g = g.set_index("Date").sort_index()
        if tkr == BENCHMARK_TICKER:
            bench = g
        else:
            if len(g) >= 60:           # need enough history to score
                by_t[tkr] = g
    return by_t, bench


if __name__ == "__main__":                                  # quick smoke-test
    logging.basicConfig(level="INFO", stream=sys.stdout, format="%(message)s")
    df = fetch_prices(force=False)
    print(df.tail())
    print(f"\nTickers: {df['Ticker'].nunique()},  Rows: {len(df)}")
