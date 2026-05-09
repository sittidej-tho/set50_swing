"""Technical indicators – pure-pandas implementations (no TA-Lib dep).

All functions take a price DataFrame indexed by Date with Open/High/Low/Close/Volume
and return either a Series or a DataFrame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------
def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period).mean()


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    sig_line = ema(macd_line, signal)
    hist = macd_line - sig_line
    return pd.DataFrame({"macd": macd_line, "signal": sig_line, "hist": hist})


# ---------------------------------------------------------------------------
# Volatility / mean reversion
# ---------------------------------------------------------------------------
def bollinger(close: pd.Series, period: int = 20,
              std_mult: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    upper = mid + std_mult * sd
    lower = mid - std_mult * sd
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame({"bb_mid": mid, "bb_up": upper, "bb_lo": lower,
                         "bb_width": width, "bb_pct": pct_b})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def donchian(df: pd.DataFrame, period: int = 55) -> pd.DataFrame:
    upper = df["High"].rolling(period).max()
    lower = df["Low"].rolling(period).min()
    mid = (upper + lower) / 2
    return pd.DataFrame({"don_up": upper, "don_lo": lower, "don_mid": mid})


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------
def volume_zscore(volume: pd.Series, period: int = 20) -> pd.Series:
    mu = volume.rolling(period).mean()
    sd = volume.rolling(period).std(ddof=0)
    return ((volume - mu) / sd.replace(0, np.nan)).fillna(0.0)


# ---------------------------------------------------------------------------
# Relative strength vs benchmark
# ---------------------------------------------------------------------------
def relative_strength(price: pd.Series, bench: pd.Series,
                      period: int = 60) -> pd.Series:
    """Ratio change of (price/bench) over `period` days, in %."""
    bench = bench.reindex(price.index).ffill()
    ratio = price / bench
    return (ratio / ratio.shift(period) - 1) * 100


# ---------------------------------------------------------------------------
# Convenience: compute everything for one ticker
# ---------------------------------------------------------------------------
def enrich(df: pd.DataFrame, params, bench_close: pd.Series) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]
    out[f"ema{params.ema_fast}"] = ema(close, params.ema_fast)
    out[f"ema{params.ema_mid}"] = ema(close, params.ema_mid)
    out[f"ema{params.ema_slow}"] = ema(close, params.ema_slow)
    out["rsi"] = rsi(close, params.rsi_period)
    out = out.join(macd(close, params.macd_fast, params.macd_slow,
                        params.macd_signal))
    out = out.join(bollinger(close, params.bb_period, params.bb_std))
    out["atr"] = atr(out, params.atr_period)
    out = out.join(donchian(out, params.donchian_period))
    out["vol_z"] = volume_zscore(out["Volume"], params.vol_zscore_period)
    out["rs"] = relative_strength(close, bench_close, params.rs_period)
    out["ret_5d"] = close.pct_change(5) * 100
    out["ret_20d"] = close.pct_change(20) * 100
    out["ret_60d"] = close.pct_change(60) * 100
    out["dd_from_high_252"] = (close / close.rolling(252, min_periods=20).max() - 1) * 100
    return out
