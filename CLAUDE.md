# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Weekly signals (live yfinance data)
python3 run_weekly.py
python3 run_weekly.py --force          # force re-download, bypass cache
python3 run_weekly.py --top 15 -v      # verbose, top 15 only

# Backtest
python3 run_backtest.py
python3 run_backtest.py --demo         # offline synthetic prices
python3 run_backtest.py --start 2022-01-03 --capital 2000000

# Offline demo (no internet required)
python3 demo.py
```

There is no test suite or linter configured. The `data.py` module has a quick smoke-test runnable with `python3 -m src.data`.

## Architecture

The pipeline is linear: **data → indicators → strategy → dashboard/backtest report**.

### Core data flow

1. `src/data.py` — fetches daily OHLCV for all SET50 tickers + `^SET.BK` benchmark via yfinance. Results cached to `data/prices.parquet` (refreshed if >12h old). `fetch_prices()` returns a tidy long DataFrame (`Date, Ticker, Open, High, Low, Close, Volume`). `split_universe()` partitions it into `{ticker: DataFrame}` dict + a benchmark Series.

2. `src/indicators.py` — pure-pandas, no TA-Lib. `enrich(df, params, bench_close)` adds all indicator columns (EMAs, RSI, MACD, Bollinger, ATR, Donchian, volume Z-score, relative strength, return columns) in-place and returns the enriched DataFrame.

3. `src/strategy.py` — five factor scorers (`trend_score`, `momentum_score`, `mean_reversion_score`, `relative_strength_score`, `volume_score`) each return [-100, +100]. The composite is a weighted sum (weights in `StrategyParams`). `_decide()` maps the composite to one of `BUY-STRONG / BUY-DIP / HOLD / TRIM / CUT / SELL-STRONG`. `score_universe()` iterates all tickers and returns a list of `Signal` dataclasses.

4. `src/dashboard.py` / `src/backtest_report.py` — Jinja2-based HTML renderers. Output goes to `reports/`.

### Configuration

All strategy parameters live in `src/config.py` as the frozen `StrategyParams` dataclass (singleton `PARAMS`). This includes indicator periods, factor weights, score thresholds, ATR multipliers, and the SET50 ticker list. To tune the strategy, edit `StrategyParams` defaults — no other files need changing.

### Backtest engine (`src/backtest.py`)

`BTConfig` controls the simulation (dates, capital, position limits, costs). `run_backtest()` pre-enriches all tickers once, then walks forward weekly (Friday close → Monday open execution). Positions are tracked in a dict; ATR stops checked daily on Low. Returns a `BTResult` with equity curve, trade log, and stats.

### Database connector (`src/db.py`)

PostgreSQL via psycopg2. Credentials loaded from `.env` (gitignored). Use the context managers:
```python
from src.db import get_connection, get_cursor

with get_cursor(dict_cursor=True) as cur:
    cur.execute("SELECT ...")
    rows = cur.fetchall()
```

### Outputs

All generated files land in `reports/` (gitignored by convention — not listed in `.gitignore` but auto-created at runtime):
- `signals.csv` / `dashboard.html` — weekly signals
- `trades.csv` / `backtest.html` — backtest results

Price cache lives in `data/prices.parquet`.

## Git Workflow

- When the user says "commit" or "git commit", stage and commit the changes immediately.
- Always print the commit message to the user after committing.
- Always let the user review the commit message and diff before pushing.
- Only push when the user explicitly says "push".
