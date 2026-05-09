# SET50 Swing Trade Engine

A weekly, multi-factor swing-trading research tool for the **Thai SET50** universe.
Pulls prices from yfinance, scores every name on five factors, and produces:

- An **interactive HTML dashboard** with KPI cards, filterable signal cards, factor scores, and price sparklines.
- A **`signals.csv`** for spreadsheets / further analysis.
- A printable **terminal report** with the full ranking table.

> ⚠️ Research tool, not investment advice. Always do your own due diligence.

---

## Quick start

```bash
cd set50_swing
pip install -r requirements.txt

# First run — downloads ~2 years of daily data for SET50 + the SET index,
# scores everything, and writes reports/dashboard.html + signals.csv
python run_weekly.py

# Force re-download (ignore cache):
python run_weekly.py --force

# Verbose logs + only show the top 15 by score:
python run_weekly.py -v --top 15
```

Open `reports/dashboard.html` in your browser. Use the toolbar to filter by
action (Buy / Buy-the-Dip / Hold / Trim / Cut / Sell) or search a ticker.

---

## Strategy overview

Every Friday afternoon (or whenever you run it), each SET50 name gets a
**composite score in [-100, +100]** computed from five factor scores:

| Factor          | Weight | What it measures                                         |
|-----------------|:-----:|----------------------------------------------------------|
| Trend           | 0.30  | EMA20/50/200 stack alignment + price vs slow EMAs        |
| Momentum        | 0.25  | RSI(14) sweet-spot + MACD histogram                      |
| Mean-reversion  | 0.20  | Bollinger %B, pullback to EMA50 in an uptrend           |
| Relative Strength | 0.15 | 60-day RS line vs the SET index                          |
| Volume          | 0.10  | Volume Z-score + accumulation/distribution sniff         |

The score is then translated into an **action**:

| Action       | Trigger                                                |
|--------------|--------------------------------------------------------|
| `BUY-STRONG` | score ≥ +60                                            |
| `BUY-DIP`    | score ≥ +35, price > 200-EMA, RSI < 65                 |
| `HOLD`       | otherwise                                              |
| `TRIM`       | score ≤ −10                                            |
| `CUT`        | score ≤ −35                                            |
| `SELL-STRONG`| score ≤ −55                                            |

Each signal also returns an **ATR-based stop and target** (2× / 3.5× ATR).

You can adjust factor weights, thresholds, and indicator periods in
`src/config.py` — the `StrategyParams` dataclass.

---

## What each action means · ความหมายของสัญญาณแต่ละชนิด

สัญญาณเหล่านี้คือ **คำสั่งจัดการพอร์ต** ไม่ใช่แค่ความเห็น — อ่านได้ว่า
*"ถ้าวันนี้คุณดูแลพอร์ต swing trade อยู่ ควรทำอะไรกับหุ้นตัวนี้"*

### 🟢 `BUY-STRONG` — *เปิดสถานะใหม่เต็มขนาด*
ปัจจัยทั้ง 5 ด้านชี้ขึ้นพร้อมกัน (คะแนนรวม ≥ +60) แนวโน้มเป็นขาขึ้น
(ราคา > EMA20 > EMA50 > EMA200) โมเมนตัมแข็งแรงแต่ยังไม่ overbought,
Relative Strength เป็นบวกเทียบกับ SET และวอลุ่มยืนยันทิศทาง
**เป็นจุดเข้าที่ความเชื่อมั่นสูงสุด** — เข้าด้วยขนาดเต็มตามความเสี่ยง
ต่อไม้ปกติ (ค่าเริ่มต้น `max_position_pct = 15%` ของพอร์ต) ใช้ stop
ที่ 2× ATR ใต้ราคาเข้า แล้วเลื่อน stop ตามขึ้นไปเมื่อราคาขึ้น

### 🟢 `BUY-DIP` — *ซื้อย่อในแนวโน้มขาขึ้น*
คะแนนรวม ≥ +35 ราคายังอยู่เหนือ EMA200 และ RSI < 65 (ไม่ไล่ราคา)
หุ้นอยู่ในแนวโน้มขาขึ้นที่ยืนยันแล้ว แต่ย่อตัวลงมาบริเวณแนวรับ —
มักจะเป็นโซน EMA50 หรือเส้น Bollinger ล่าง พร้อม RSI ในช่วง 30–45
**ถือเป็น setup หลักของกลยุทธ์ swing** เข้าด้วยขนาด starter
(เล็กกว่า BUY-STRONG) แล้วค่อยเพิ่มเมื่อราคายืนได้และโมเมนตัม
กลับมา Stop = swing low ล่าสุด หรือ 2× ATR

### ⚪ `HOLD` — *ถือไว้ ไม่ทำอะไรเพิ่ม*
คะแนนอยู่ในโซนกลาง (~ −10 ถึง +35) หรือปัจจัยขัดแย้งกัน เช่น
เทรนด์ขึ้นแต่ overbought หรือ RS อ่อน ยังไม่มี edge ฝั่งใด
**ถ้ามีหุ้นอยู่แล้วก็ถือต่อได้ ถ้ายังไม่มีก็ไม่ต้องไล่ราคา**
รอให้คะแนนหลุดออกจากกรอบนี้ในรอบสแกนสัปดาห์ถัดไป

### 🟡 `TRIM` — *ทำกำไรบางส่วน / ลดน้ำหนัก*
คะแนนเริ่มลดลงมาที่ ≤ −10 setup ที่พาเข้ามาเริ่มอ่อน —
โมเมนตัมพลิก, RS เริ่มล้าหลัง, หรือราคายืดออกจากแนวโน้มมากเกินไป
ขาย ⅓ ถึง ½ ของสถานะ เลื่อน stop ขึ้นมาที่จุดเสมอตัว (break-even)
แล้วปล่อยส่วนที่เหลือวิ่งต่อ **TRIM เป็นสัญญาณลดความเสี่ยง
ยังไม่ใช่การพลิกเทรนด์** — แนวโน้มอาจยังคงอยู่

### 🟠 `CUT` — *ลดเหลือ starter / watch-list*
คะแนน ≤ −35 แนวโน้มเริ่มเสีย: EMA หักหัวลง, MACD histogram
พลิกเป็นลบ, หรือ RS หลุดเทรนด์ ลดสถานะเหลือขนาดเล็ก
(หรือออกทั้งหมดถ้าไม่ชอบถือหุ้นที่กำลังร่วง) **ห้ามซื้อเพิ่ม**
รอให้กราฟกลับมาซ่อมตัวก่อน ค่อยพิจารณาเข้าใหม่

### 🔴 `SELL-STRONG` — *ออกจากสถานะทั้งหมด*
คะแนน ≤ −55 EMA เรียงตัวเป็นขาลง (ราคา < EMA200, EMAs เรียงลง)
RS อ่อนเทียบกับตลาด และโมเมนตัมยืนยันการลง **ปิดสถานะให้หมด**
และใส่หุ้นไว้ใน no-touch list จนกว่าอย่างน้อย 1 ใน 3 ปัจจัยหลัก
(เทรนด์ / RS / โมเมนตัม) จะพลิกกลับขึ้น ถ้าต้องการ short
นี่คือสัญญาณ — แต่กลยุทธ์ตั้งต้นออกแบบสำหรับ long-only

### Stop & Target
ทุกแถวจะมีระดับ **Stop** และ **Target** ที่คำนวณจาก ATR 14 วัน:

- ฝั่งซื้อ (`BUY-*`): `stop = ราคา − 2·ATR`, `target = ราคา + 3.5·ATR`
  → อัตราส่วน reward / risk ≈ 1.75 R
- ฝั่งขาย (`TRIM` / `CUT` / `SELL-STRONG`): ระดับจะกลับด้าน ทำหน้าที่เป็น
  *"reclaim level"* — ถ้าราคากลับขึ้นมาเหนือจุดดังกล่าวพร้อมวอลุ่ม
  สถานการณ์ฝั่งหมีถือเป็นโมฆะ และค่อยกลับมาพิจารณาใหม่

### Quick decision cheat-sheet · ตารางสรุปการตัดสินใจ

```
       ช่วงคะแนน           ตัวกรองเทรนด์          สัญญาณ              คำแปล
     ─────────────────  ──────────────────  ────────────────  ─────────────────────────
      +60  → +100         (any)              BUY-STRONG       เปิดสถานะใหม่เต็มขนาด
      +35  → +60          price > 200-EMA,   BUY-DIP          ซื้อย่อในแนวโน้มขาขึ้น
                          RSI < 65
      −10  → +35          (any)              HOLD             ถือไว้ ไม่ทำอะไรเพิ่ม
      −35  → −10          (any)              TRIM             ทำกำไรบางส่วน / ลดน้ำหนัก
      −55  → −35          (any)              CUT              ลดเหลือ starter / watch-list
     −100  → −55          (any)              SELL-STRONG      ออกจากสถานะทั้งหมด
```

---

## Project layout

```
set50_swing/
├── run_weekly.py           # CLI entry-point — generates weekly signals
├── run_backtest.py         # CLI entry-point — walk-forward backtest
├── demo.py                 # offline preview using synthetic prices
├── requirements.txt
├── README.md
├── src/
│   ├── config.py           # SET50 list, parameters, paths
│   ├── data.py             # yfinance fetcher + parquet/csv cache
│   ├── indicators.py       # EMA / RSI / MACD / Bollinger / ATR / Donchian / RS
│   ├── strategy.py         # factor scoring + decision rules
│   ├── dashboard.py        # weekly-signals HTML dashboard renderer
│   ├── backtest.py         # walk-forward simulation engine
│   └── backtest_report.py  # backtest HTML report renderer
├── data/                   # price cache (auto-created)
└── reports/                # dashboard.html + signals.csv +
                              backtest.html + trades.csv (auto-created)
```

---

## Backtest harness

Walk-forward simulation of the same multi-factor strategy. Every Friday close
the engine scores the universe using **only data available up to that day**
(no look-ahead) and trades at next Monday's open.

```bash
python run_backtest.py                                 # live yfinance
python run_backtest.py --demo                          # offline synthetic prices
python run_backtest.py --start 2022-01-03 --capital 2000000
python run_backtest.py --no-stops                      # disable intraday ATR stops
```

Outputs land in `reports/`:

- **`backtest.html`** — interactive report with:
  - KPI cards: total return, CAGR, max drawdown, Sharpe, win rate, alpha vs SET
  - Equity curve overlaid on SET buy-and-hold
  - Drawdown chart
  - Monthly returns bar
  - Per-signal stats — separate cards for `BUY-STRONG` / `BUY-DIP` entries and
    `TRIM` / `CUT` / `SELL-STRONG` / `STOP` / `EOH` exits
  - Full trade log
- **`trades.csv`** — machine-readable trade log (one row per fill).

### Portfolio rules

| | |
|---|---|
| Cadence              | Weekly (signals computed Friday close, executed Monday open) |
| Sizing               | Equal-weight up to `max_positions` (default 8), capped at `max_position_pct` (default 15%) per name |
| Entries              | `BUY-STRONG` and `BUY-DIP`, ranked by composite score |
| Trims                | `TRIM` → sell `trim_fraction` (default 50%) at next open |
| Cuts                 | `CUT` → sell `cut_fraction` (default 70%), keep a 30% starter |
| Full exits           | `SELL-STRONG` → close the rest                                 |
| Stop loss            | Daily Low ≤ `entry − 2·ATR` → exit at the stop price (intra-week) |
| Costs                | 15 bps round-trip + 5 bps one-way slippage (configurable)      |
| Benchmark            | SET index buy-and-hold over the same window                    |

### Reading the metrics

| Metric | Meaning |
|---|---|
| **Total Return**  | Final equity ÷ starting capital − 1                      |
| **CAGR**          | Annualised compound growth                              |
| **Max Drawdown**  | Worst peak-to-trough on the equity curve                |
| **Sharpe**        | Daily-return Sharpe, annualised (×√252), rf assumed 0    |
| **Win Rate**      | Share of trades closed with `pnl_pct > 0`                |
| **Alpha vs SET**  | Total Return − SET buy-and-hold over the same window     |

Tweak any of `BTConfig`'s defaults via CLI flags or by importing the engine
in a notebook for grid searches and parameter sweeps.

---

## Customising the universe

`src/config.py` → `SET50_TICKERS`.  yfinance uses the `.BK` suffix.
If SET reshuffles the index, just edit the list and re-run.

---

## Roadmap ideas

- Backtest harness on the same factor scores → walk-forward equity curve.
- Sector / market-regime filter (de-risk when SET < 200-EMA).
- Position sizing by ATR-risk targeting (volatility parity).
- Email / LINE notify on weekly signal change.
- Multi-timeframe confluence (weekly trend + daily entry).
