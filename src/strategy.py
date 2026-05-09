"""Multi-factor swing strategy engine for SET50.

Five factor scores in [-100, +100] are combined into a composite that maps
to one of: BUY-DIP, BUY-STRONG, HOLD, TRIM, CUT, SELL-STRONG.

Factors
-------
trend         : alignment + slope of EMA20/50/200 stack vs price.
momentum      : RSI(14) and MACD histogram, with overbought penalties.
mean_reversion: %B (Bollinger), distance below EMA50, RSI dip-but-not-broken.
relative_str  : 60d return of price/bench ratio (RS line).
volume        : confirmation – up-day on volume Z>+1, capitulation Z>+2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import PARAMS, StrategyParams
from .indicators import enrich


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clip(x: float, lo: float = -100, hi: float = 100) -> float:
    return float(max(lo, min(hi, x)))


def _safe(x, default: float = 0.0) -> float:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return default
    return float(x)


# ---------------------------------------------------------------------------
# Factor scorers (operate on the most-recent row)
# ---------------------------------------------------------------------------
def trend_score(row: pd.Series, p: StrategyParams) -> float:
    close = row["Close"]
    e_f, e_m, e_s = row[f"ema{p.ema_fast}"], row[f"ema{p.ema_mid}"], row[f"ema{p.ema_slow}"]
    score = 0.0
    # Stack alignment.
    if e_f > e_m > e_s:                      score += 50
    elif e_f > e_m and e_m > e_s * 0.99:     score += 25
    elif e_f < e_m < e_s:                    score -= 60
    # Price vs EMAs.
    if close > e_s:                          score += 20
    else:                                    score -= 30
    if close > e_m:                          score += 15
    else:                                    score -= 10
    # Slope (using ret_20d as a slope proxy on the EMAs is overkill;
    # use 20d return as a regime sniff).
    score += _clip(_safe(row["ret_20d"]) * 2, -25, 25)
    return _clip(score)


def momentum_score(row: pd.Series, p: StrategyParams) -> float:
    rsi = _safe(row["rsi"], 50)
    hist = _safe(row["hist"])
    score = 0.0
    # RSI band: reward 45-65, punish overbought >75 and washed <25.
    if 45 <= rsi <= 65:        score += 30
    elif 35 <= rsi < 45:       score += 5     # neutral-ish
    elif 25 <= rsi < 35:       score -= 20
    elif rsi < 25:             score -= 35    # falling knife
    elif 65 < rsi <= 75:       score += 10
    else:                      score -= 25    # > 75 overbought
    # MACD hist.
    score += _clip(hist * 200, -40, 40)
    return _clip(score)


def mean_reversion_score(row: pd.Series, p: StrategyParams) -> float:
    """Reward 'healthy dip' — pullback to support inside an uptrend."""
    bb_pct = _safe(row["bb_pct"], 0.5)
    close = row["Close"]
    e_m = _safe(row[f"ema{p.ema_mid}"], close)
    e_s = _safe(row[f"ema{p.ema_slow}"], close)
    rsi = _safe(row["rsi"], 50)

    score = 0.0
    # Bollinger %B sweet spot for dip-buying = 0.05 .. 0.30 (lower band area)
    if 0.0 <= bb_pct <= 0.20:        score += 35
    elif 0.20 < bb_pct <= 0.40:      score += 15
    elif 0.40 < bb_pct <= 0.70:      score += 0
    elif 0.70 < bb_pct <= 0.90:      score -= 10
    else:                            score -= 25       # extended top
    # Pullback to EMA50 in an uptrend (price above EMA200) is gold.
    pull_to_ema50 = (e_m - close) / e_m * 100
    if close > e_s:                                    # uptrend
        if 0.5 <= pull_to_ema50 <= 5:    score += 30   # healthy dip
        elif pull_to_ema50 > 5:          score += 10
        elif pull_to_ema50 < -3:         score -= 5    # extended above
    else:                                              # downtrend, dips are dangerous
        score -= 15
    # RSI 30-45 in uptrend = buyable; <25 + downtrend = avoid
    if close > e_s and 30 <= rsi <= 45:    score += 15
    if close < e_s and rsi < 30:           score -= 15
    return _clip(score)


def relative_strength_score(row: pd.Series, p: StrategyParams) -> float:
    rs = _safe(row["rs"])
    return _clip(rs * 4)              # +/- 25% RS → +/- 100


def volume_score(row: pd.Series, p: StrategyParams) -> float:
    z = _safe(row["vol_z"])
    ret1 = _safe(row.get("ret_1d", 0.0))
    if ret1 == 0.0 and "Close" in row and "Open" in row:
        ret1 = (row["Close"] / row["Open"] - 1) * 100
    if z > 1 and ret1 > 0:        return _clip(40 + min(z * 10, 30))
    if z > 1 and ret1 < 0:        return _clip(-40 - min(z * 10, 30))   # distribution
    if z > 2 and ret1 < -2:       return -80                            # capitulation
    return _clip(z * 10)


# ---------------------------------------------------------------------------
# Decision mapping
# ---------------------------------------------------------------------------
@dataclass
class Signal:
    ticker: str
    action: str            # BUY-DIP / BUY-STRONG / HOLD / TRIM / CUT / SELL-STRONG
    score: float
    factors: dict[str, float]
    price: float
    stop: float
    target: float
    rationale: str
    snapshot: dict[str, float]
    history: pd.DataFrame    # last ~120 daily closes, for sparklines


def _decide(score: float, row: pd.Series, p: StrategyParams) -> str:
    rsi = _safe(row["rsi"], 50)
    close = row["Close"]
    e_s = _safe(row[f"ema{p.ema_slow}"], close)
    if score >= p.score_buy_strong:                                return "BUY-STRONG"
    if score >= p.score_buy_dip and close > e_s and rsi < 65:      return "BUY-DIP"
    if score <= p.score_sell_strong:                               return "SELL-STRONG"
    if score <= p.score_cut:                                       return "CUT"
    if score <= p.score_trim:                                      return "TRIM"
    return "HOLD"


def _rationale(action: str, factors: dict[str, float], row: pd.Series,
               p: StrategyParams) -> str:
    rsi = _safe(row["rsi"], 50)
    bb_pct = _safe(row["bb_pct"], 0.5)
    e_s = _safe(row[f"ema{p.ema_slow}"])
    bits: list[str] = []
    if action == "BUY-DIP":
        bits.append(f"Pullback in uptrend (price > 200-EMA), RSI {rsi:.0f}, %B {bb_pct:.2f}.")
    elif action == "BUY-STRONG":
        bits.append("All five factors aligned to the upside.")
    elif action == "HOLD":
        bits.append("No edge: indicators mixed or middle of the range.")
    elif action == "TRIM":
        bits.append(f"Momentum cooling (RSI {rsi:.0f}); take partial profit / size down.")
    elif action == "CUT":
        bits.append("Trend deteriorating – reduce risk to small / starter size.")
    elif action == "SELL-STRONG":
        bits.append(f"Bearish stack, weak RS, price < 200-EMA ({e_s:.2f}). Exit.")
    # Factor highlights
    top = sorted(factors.items(), key=lambda kv: kv[1], reverse=action.startswith("BUY"))[:2]
    bits.append("Drivers: " + ", ".join(f"{k}={v:+.0f}" for k, v in top))
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Top-level scoring
# ---------------------------------------------------------------------------
def score_ticker(ticker: str, prices: pd.DataFrame, bench_close: pd.Series,
                 p: StrategyParams = PARAMS) -> Optional[Signal]:
    if len(prices) < max(p.ema_slow, 60):
        return None
    df = enrich(prices, p, bench_close)
    df["ret_1d"] = df["Close"].pct_change() * 100
    last = df.iloc[-1]
    factors = {
        "trend":          trend_score(last, p),
        "momentum":       momentum_score(last, p),
        "mean_reversion": mean_reversion_score(last, p),
        "relative_str":   relative_strength_score(last, p),
        "volume":         volume_score(last, p),
    }
    composite = sum(p.weights[k] * v for k, v in factors.items())
    action = _decide(composite, last, p)

    atr_v = _safe(last["atr"], last["Close"] * 0.02)
    price = float(last["Close"])
    stop = price - p.atr_stop_mult * atr_v
    target = price + p.atr_target_mult * atr_v
    if action.startswith("SELL") or action == "CUT":
        # For exit signals, the "stop" is more like a "no-touch" reclaim level.
        stop = price + p.atr_stop_mult * atr_v
        target = price - p.atr_target_mult * atr_v

    snapshot = {
        "Close":   price,
        "RSI":     _safe(last["rsi"]),
        "%B":      _safe(last["bb_pct"]),
        "ATR%":    atr_v / price * 100,
        "RS_60d":  _safe(last["rs"]),
        "Ret_5d":  _safe(last["ret_5d"]),
        "Ret_20d": _safe(last["ret_20d"]),
        "DD_252":  _safe(last["dd_from_high_252"]),
        "VolZ":    _safe(last["vol_z"]),
    }
    history = df[["Close"]].tail(120).reset_index().rename(
        columns={"Date": "date", "Close": "close"})
    history["date"] = history["date"].dt.strftime("%Y-%m-%d")

    return Signal(
        ticker=ticker, action=action, score=round(composite, 1),
        factors={k: round(v, 1) for k, v in factors.items()},
        price=round(price, 2),
        stop=round(stop, 2), target=round(target, 2),
        rationale=_rationale(action, factors, last, p),
        snapshot={k: round(v, 2) for k, v in snapshot.items()},
        history=history,
    )


def score_universe(by_ticker: dict[str, pd.DataFrame],
                   bench: pd.DataFrame,
                   p: StrategyParams = PARAMS) -> list[Signal]:
    bench_close = (bench["Close"] if not bench.empty
                   else pd.Series(1.0, index=next(iter(by_ticker.values())).index))
    out: list[Signal] = []
    for tkr, df in by_ticker.items():
        try:
            sig = score_ticker(tkr, df, bench_close, p)
            if sig is not None:
                out.append(sig)
        except Exception as exc:                            # pragma: no cover
            print(f"[warn] {tkr} skipped: {exc}")
    out.sort(key=lambda s: s.score, reverse=True)
    return out
