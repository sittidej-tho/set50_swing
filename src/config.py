"""Configuration for the SET50 Swing Trade engine.

Edit `SET50_TICKERS` if the SET Index reshuffles. The list below is the
SET50 constituent set as of H1 2026; yfinance uses the ".BK" suffix.

If a ticker is missing data on yfinance (some Thai tickers occasionally
return empty frames), it will be skipped automatically with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
# SET50 constituents -- edit when SET reshuffles the index.
SET50_TICKERS: list[str] = [
    "ADVANC.BK", "AOT.BK", "AWC.BK", "BANPU.BK", "BBL.BK",
    "BDMS.BK", "BEM.BK", "BGRIM.BK", "BH.BK", "BJC.BK",
    "BTS.BK", "CBG.BK", "CENTEL.BK", "COM7.BK", "CPALL.BK",
    "CPF.BK", "CPN.BK", "CRC.BK", "DELTA.BK", "EA.BK",
    "EGCO.BK", "GLOBAL.BK", "GPSC.BK", "GULF.BK", "HMPRO.BK",
    "IVL.BK", "KBANK.BK", "KKP.BK", "KTB.BK",
    "KTC.BK", "LH.BK", "MINT.BK", "MTC.BK", "OR.BK",
    "OSP.BK", "PTT.BK", "PTTEP.BK", "PTTGC.BK", "RATCH.BK",
    "SAWAD.BK", "SCB.BK", "SCC.BK", "SCGP.BK", "TIDLOR.BK",
    "TISCO.BK", "TLI.BK", "TOP.BK", "TRUE.BK", "TTB.BK",
]

# Benchmark used for relative strength scoring.
BENCHMARK_TICKER = "^SET.BK"   # SET Index on yfinance.
# Fallback if ^SET.BK fails -- the SETI ETF is a reasonable proxy.
BENCHMARK_FALLBACK = "TDEX.BK"


# ---------------------------------------------------------------------------
# Strategy parameters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyParams:
    # Lookback for daily history download (calendar days).
    lookback_days: int = 540

    # Indicator periods.
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    donchian_period: int = 55
    rs_period: int = 60       # ~3 trading months
    vol_zscore_period: int = 20

    # Decision thresholds (composite score is in [-100, +100]).
    score_buy_dip: float = 35.0
    score_trim: float = -10.0
    score_cut: float = -35.0
    score_sell_strong: float = -55.0
    score_buy_strong: float = 60.0

    # Risk controls.
    atr_stop_mult: float = 2.0
    atr_target_mult: float = 3.5
    max_positions: int = 8
    max_position_pct: float = 0.15   # 15% of book per name

    # Factor weights (must sum to ~1.0).
    weights: dict[str, float] = field(default_factory=lambda: {
        "trend":          0.30,
        "momentum":       0.25,
        "mean_reversion": 0.20,
        "relative_str":   0.15,
        "volume":         0.10,
    })


PARAMS = StrategyParams()
