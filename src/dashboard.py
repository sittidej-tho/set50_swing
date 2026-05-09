"""Render a self-contained interactive HTML dashboard from a list of Signals."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Iterable

from .config import REPORTS_DIR
from .strategy import Signal


_ACTION_BADGE = {
    "BUY-STRONG":  ("Buy", "buy"),
    "BUY-DIP":     ("Buy the Dip", "buy"),
    "HOLD":        ("Hold", "hold"),
    "TRIM":        ("Trim", "trim"),
    "CUT":         ("Cut", "cut"),
    "SELL-STRONG": ("Sell", "sell"),
}


def _signal_to_dict(s: Signal) -> dict:
    label, css = _ACTION_BADGE.get(s.action, (s.action, "hold"))
    return {
        "ticker":   s.ticker,
        "action":   s.action,
        "label":    label,
        "css":      css,
        "score":    s.score,
        "price":    s.price,
        "stop":     s.stop,
        "target":   s.target,
        "factors":  s.factors,
        "snapshot": s.snapshot,
        "rationale": s.rationale,
        "history":  s.history.to_dict(orient="list"),
    }


def render(signals: Iterable[Signal], out_path: Path | None = None) -> Path:
    sigs = [_signal_to_dict(s) for s in signals]
    actions_summary: dict[str, int] = {}
    for s in sigs:
        actions_summary[s["action"]] = actions_summary.get(s["action"], 0) + 1

    payload = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "as_of":        dt.date.today().strftime("%Y-%m-%d"),
        "summary":      actions_summary,
        "signals":      sigs,
    }

    out_path = out_path or (REPORTS_DIR / "dashboard.html")
    html = _TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, default=str))
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# HTML template (self-contained, Chart.js from CDN)
# ---------------------------------------------------------------------------
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>SET50 Swing Trade — Weekly Signals</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0b1020; --panel:#121a33; --panel2:#0f1730; --txt:#e6ecff; --muted:#8aa0c8;
  --line:#1f2a4d; --accent:#7aa2ff;
  --buy:#22c55e; --hold:#94a3b8; --trim:#f59e0b; --cut:#ef4444; --sell:#dc2626;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--txt);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
header{padding:22px 28px;display:flex;justify-content:space-between;align-items:center;
  border-bottom:1px solid var(--line);background:linear-gradient(180deg,#101736,#0b1020)}
header h1{margin:0;font-size:20px;letter-spacing:.3px}
header .meta{color:var(--muted);font-size:13px}
.container{padding:24px 28px;max-width:1400px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:22px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px}
.kpi .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.kpi .val{font-size:22px;font-weight:600;margin-top:4px}
.kpi.buy   .val{color:var(--buy)}
.kpi.hold  .val{color:var(--hold)}
.kpi.trim  .val{color:var(--trim)}
.kpi.cut   .val{color:var(--cut)}
.kpi.sell  .val{color:var(--sell)}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 16px}
.toolbar button{background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  padding:7px 12px;border-radius:8px;cursor:pointer;font-size:13px}
.toolbar button.active{background:var(--accent);color:#0b1020;border-color:var(--accent);font-weight:600}
.toolbar input{background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  padding:7px 10px;border-radius:8px;flex:1;min-width:160px}
.toolbar select{background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  padding:7px 10px;border-radius:8px;font-size:13px;cursor:pointer}
.toolbar label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.card .row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.card .ticker{font-size:18px;font-weight:600}
.card .price{font-size:14px;color:var(--muted)}
.badge{padding:3px 9px;border-radius:999px;font-size:12px;font-weight:600;letter-spacing:.3px}
.badge.buy{background:rgba(34,197,94,.15);color:var(--buy);border:1px solid rgba(34,197,94,.4)}
.badge.hold{background:rgba(148,163,184,.15);color:var(--hold);border:1px solid rgba(148,163,184,.4)}
.badge.trim{background:rgba(245,158,11,.15);color:var(--trim);border:1px solid rgba(245,158,11,.4)}
.badge.cut{background:rgba(239,68,68,.15);color:var(--cut);border:1px solid rgba(239,68,68,.4)}
.badge.sell{background:rgba(220,38,38,.18);color:var(--sell);border:1px solid rgba(220,38,38,.45)}
.factors{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;font-size:11px}
.factor{padding:6px 4px;border-radius:6px;text-align:center;background:var(--panel2)}
.factor .name{color:var(--muted);text-transform:uppercase;letter-spacing:.4px;font-size:10px}
.factor .val{font-weight:600}
.snap{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;font-size:12px;color:var(--muted)}
.snap b{color:var(--txt)}
.spark-wrap{position:relative;height:64px;width:100%}
.spark-wrap canvas{display:block;width:100% !important;height:100% !important}
.rationale{font-size:12px;color:var(--muted);border-top:1px dashed var(--line);padding-top:8px}
.levels{font-size:12px;display:flex;justify-content:space-between;color:var(--muted)}
.levels b{color:var(--txt)}
.legend{font-size:11px;color:var(--muted);margin-top:6px}
details.guide{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:10px 16px;margin-bottom:18px}
details.guide summary{cursor:pointer;font-weight:600;font-size:14px;list-style:none;
  display:flex;justify-content:space-between;align-items:center}
details.guide summary::after{content:"▾";color:var(--muted);transition:transform .15s}
details.guide[open] summary::after{transform:rotate(180deg)}
.guide-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:12px;margin-top:12px}
.guide-card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px}
.guide-card .head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.guide-card .title{font-weight:600;font-size:13px}
.guide-card .body{font-size:12px;color:var(--muted);line-height:1.45}
.guide-card .trigger{font-size:11px;color:var(--muted);margin-top:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace}
@media (max-width:900px){.kpis{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>

<header>
  <div>
    <h1>📈 SET50 Swing Trade — Weekly Signals</h1>
    <div class="meta" id="meta"></div>
  </div>
  <div class="meta">Multi-factor model · trend · momentum · mean-reversion · RS · volume</div>
</header>

<div class="container">
  <div class="kpis" id="kpis"></div>

  <details class="guide">
    <summary>📖 ความหมายของสัญญาณแต่ละชนิด (What do these signals mean?)</summary>
    <div class="guide-grid">
      <div class="guide-card">
        <div class="head"><span class="badge buy">Buy</span>
          <span class="title">BUY-STRONG · เปิดสถานะใหม่เต็มขนาด</span></div>
        <div class="body">ปัจจัยทั้ง 5 ด้านชี้ขึ้นพร้อมกัน (คะแนนรวม ≥ +60)
          แนวโน้มเป็นขาขึ้น (ราคา &gt; EMA20 &gt; EMA50 &gt; EMA200) โมเมนตัม
          แข็งแรงแต่ยังไม่ overbought, Relative Strength เป็นบวกเทียบกับ
          SET และวอลุ่มยืนยันทิศทาง เป็นจุดเข้าที่ความเชื่อมั่นสูงสุด —
          เข้าด้วยขนาดเต็มตามความเสี่ยงต่อไม้ปกติ (ค่าเริ่มต้น 15% ของพอร์ต)
          ใช้ stop ที่ 2×ATR ใต้ราคาเข้า แล้วเลื่อน stop ตามราคาที่ขึ้นไป</div>
        <div class="trigger">trigger ▸ คะแนน ≥ +60</div>
      </div>
      <div class="guide-card">
        <div class="head"><span class="badge buy">Buy the Dip</span>
          <span class="title">BUY-DIP · ซื้อย่อในแนวโน้มขาขึ้น</span></div>
        <div class="body">คะแนนรวม ≥ +35, ราคายังอยู่เหนือ EMA200, และ
          RSI &lt; 65 (ไม่ไล่ราคา) หุ้นอยู่ในแนวโน้มขาขึ้นที่ยืนยันแล้ว
          แต่ย่อตัวลงมาบริเวณแนวรับ — โซน EMA50 หรือเส้น Bollinger ล่าง
          พร้อม RSI ในช่วง 30–45 ถือเป็น setup หลักของกลยุทธ์ swing
          เข้าด้วยขนาด starter ก่อน แล้วค่อยเพิ่มเมื่อราคายืนได้และโมเมนตัม
          กลับมา Stop = swing low ล่าสุด หรือ 2×ATR</div>
        <div class="trigger">trigger ▸ คะแนน ≥ +35, ราคา &gt; EMA200, RSI &lt; 65</div>
      </div>
      <div class="guide-card">
        <div class="head"><span class="badge hold">Hold</span>
          <span class="title">HOLD · ถือไว้ ไม่ทำอะไรเพิ่ม</span></div>
        <div class="body">คะแนนอยู่ในโซนกลาง (~ −10 ถึง +35) หรือปัจจัยขัดแย้งกัน
          (เช่น เทรนด์ขึ้นแต่ overbought หรือ RS อ่อน) ยังไม่มี edge ฝั่งใด
          ถ้ามีหุ้นอยู่แล้วถือต่อได้ ถ้ายังไม่มีก็ไม่ต้องไล่ราคา รอให้
          คะแนนหลุดออกจากกรอบนี้ในรอบสแกนสัปดาห์ถัดไป</div>
        <div class="trigger">trigger ▸ คะแนน ∈ (−10, +35)</div>
      </div>
      <div class="guide-card">
        <div class="head"><span class="badge trim">Trim</span>
          <span class="title">TRIM · ทำกำไรบางส่วน / ลดน้ำหนัก</span></div>
        <div class="body">คะแนนเริ่มลดลงมาที่ ≤ −10 setup ที่พาเข้ามาเริ่มอ่อน —
          โมเมนตัมพลิก, RS เริ่มล้าหลัง, หรือราคายืดออกจากแนวโน้มมากเกินไป
          ขาย ⅓ – ½ ของสถานะ เลื่อน stop ขึ้นมาที่จุดเสมอตัว (break-even)
          แล้วปล่อยส่วนที่เหลือวิ่งต่อ — เป็นสัญญาณลดความเสี่ยง ยังไม่ใช่การ
          พลิกเทรนด์</div>
        <div class="trigger">trigger ▸ คะแนน ≤ −10</div>
      </div>
      <div class="guide-card">
        <div class="head"><span class="badge cut">Cut</span>
          <span class="title">CUT · ลดเหลือ starter / watch-list</span></div>
        <div class="body">คะแนน ≤ −35 แนวโน้มเริ่มเสีย: EMA หักหัวลง,
          MACD histogram พลิกเป็นลบ, หรือ RS หลุดเทรนด์ ลดสถานะเหลือขนาดเล็ก
          (หรือออกทั้งหมดถ้าไม่ชอบถือหุ้นที่กำลังร่วง) ห้ามซื้อเพิ่ม
          รอให้กราฟกลับมาซ่อมตัวก่อน ค่อยพิจารณาเข้าใหม่</div>
        <div class="trigger">trigger ▸ คะแนน ≤ −35</div>
      </div>
      <div class="guide-card">
        <div class="head"><span class="badge sell">Sell</span>
          <span class="title">SELL-STRONG · ออกจากสถานะทั้งหมด</span></div>
        <div class="body">คะแนน ≤ −55 EMA เรียงตัวเป็นขาลง
          (ราคา &lt; EMA200), RS อ่อนเทียบกับตลาด, โมเมนตัมยืนยันการลง
          ปิดสถานะให้หมด และใส่หุ้นไว้ใน no-touch list จนกว่าอย่างน้อย
          1 ใน 3 ปัจจัยหลัก (เทรนด์ / RS / โมเมนตัม) จะพลิกกลับขึ้น</div>
        <div class="trigger">trigger ▸ คะแนน ≤ −55</div>
      </div>
    </div>
    <div class="legend" style="margin-top:10px">
      <b>Stop / Target:</b> สำหรับสัญญาณฝั่งซื้อ
      <code>stop = ราคา − 2·ATR</code>, <code>target = ราคา + 3.5·ATR</code>
      (อัตราส่วน reward / risk ≈ 1.75 R) สำหรับสัญญาณฝั่งขาย ระดับจะกลับด้าน
      และทำหน้าที่เป็น "reclaim level" — ถ้าราคากลับขึ้นมาเหนือจุดดังกล่าว
      พร้อมวอลุ่ม สถานการณ์ฝั่งหมีถือเป็นโมฆะ
    </div>
  </details>

  <div class="toolbar" id="toolbar">
    <button data-f="ALL" class="active">All</button>
    <button data-f="BUY-STRONG">Buy</button>
    <button data-f="BUY-DIP">Buy the Dip</button>
    <button data-f="HOLD">Hold</button>
    <button data-f="TRIM">Trim</button>
    <button data-f="CUT">Cut</button>
    <button data-f="SELL-STRONG">Sell</button>
    <input id="search" placeholder="Filter ticker… (e.g. PTT, CPALL)"/>
    <label>Sort
      <select id="sort">
        <option value="name_asc" selected>Name (A → Z)</option>
        <option value="name_desc">Name (Z → A)</option>
        <option value="score_desc">Score (high → low)</option>
        <option value="score_asc">Score (low → high)</option>
        <option value="action">Action</option>
      </select>
    </label>
  </div>

  <div class="cards" id="cards"></div>
  <div class="legend">
    Composite score ∈ [-100, +100]. Stop / Target are ATR-based reference levels
    (2× / 3.5× ATR). This is a research tool — not investment advice.
  </div>
</div>

<script>
const PAYLOAD = __PAYLOAD__;
const fmt = (x, d=2) => (x===null||x===undefined||isNaN(x))?"–":Number(x).toFixed(d);
const pct = (x, d=1) => (x===null||x===undefined||isNaN(x))?"–":Number(x).toFixed(d)+"%";

document.getElementById('meta').textContent =
  `As of ${PAYLOAD.as_of} · generated ${PAYLOAD.generated_at} · ${PAYLOAD.signals.length} names scored`;

// ---------- KPI cards ----------
const order = [["BUY-STRONG","Buy","buy"],["BUY-DIP","Buy the Dip","buy"],
               ["HOLD","Hold","hold"],["TRIM","Trim","trim"],
               ["CUT","Cut","cut"],["SELL-STRONG","Sell","sell"]];
const kpiHost = document.getElementById('kpis');
for(const [k,label,css] of order){
  const v = PAYLOAD.summary[k] || 0;
  const el = document.createElement('div');
  el.className = `kpi ${css}`;
  el.innerHTML = `<div class="label">${label}</div><div class="val">${v}</div>`;
  kpiHost.appendChild(el);
}

// ---------- Card rendering ----------
const host = document.getElementById('cards');
const charts = {};

function factorHTML(factors){
  const order = ["trend","momentum","mean_reversion","relative_str","volume"];
  return order.map(k=>{
    const v = factors[k] ?? 0;
    const color = v>20?"var(--buy)":v<-20?"var(--cut)":"var(--hold)";
    return `<div class="factor"><div class="name">${k.replace('_',' ')}</div>
            <div class="val" style="color:${color}">${v>=0?'+':''}${fmt(v,0)}</div></div>`;
  }).join('');
}

function snapHTML(s){
  const ss = s.snapshot || {};
  return `
    <div class="snap">
      <div>RSI: <b>${fmt(ss.RSI,0)}</b></div>
      <div>%B: <b>${fmt(ss['%B'],2)}</b></div>
      <div>ATR%: <b>${fmt(ss['ATR%'],1)}</b></div>
      <div>RS 60d: <b>${pct(ss.RS_60d,1)}</b></div>
      <div>Ret 5d: <b>${pct(ss.Ret_5d,1)}</b></div>
      <div>Ret 20d: <b>${pct(ss.Ret_20d,1)}</b></div>
      <div>DD 1y: <b>${pct(ss.DD_252,1)}</b></div>
      <div>Vol Z: <b>${fmt(ss.VolZ,1)}σ</b></div>
      <div>Score: <b>${s.score>=0?'+':''}${fmt(s.score,0)}</b></div>
    </div>`;
}

function cardHTML(s){
  return `
    <div class="card" data-action="${s.action}" data-ticker="${s.ticker}">
      <div class="row">
        <div>
          <div class="ticker">${s.ticker.replace('.BK','')}</div>
          <div class="price">${fmt(s.price)} THB</div>
        </div>
        <div class="badge ${s.css}">${s.label}</div>
      </div>
      <div class="factors">${factorHTML(s.factors)}</div>
      <div class="spark-wrap"><canvas id="spark-${s.ticker}"></canvas></div>
      ${snapHTML(s)}
      <div class="levels"><span>Stop: <b>${fmt(s.stop)}</b></span>
        <span>Target: <b>${fmt(s.target)}</b></span></div>
      <div class="rationale">${s.rationale}</div>
    </div>`;
}

const ACTION_ORDER = {"BUY-STRONG":0,"BUY-DIP":1,"HOLD":2,"TRIM":3,"CUT":4,"SELL-STRONG":5};

function sortSignals(arr, mode){
  const a = arr.slice();
  switch(mode){
    case "score_asc":  a.sort((x,y)=> x.score - y.score); break;
    case "name_asc":   a.sort((x,y)=> x.ticker.localeCompare(y.ticker)); break;
    case "name_desc":  a.sort((x,y)=> y.ticker.localeCompare(x.ticker)); break;
    case "action":     a.sort((x,y)=>
      (ACTION_ORDER[x.action]-ACTION_ORDER[y.action]) || (y.score - x.score)); break;
    case "score_desc":
    default:           a.sort((x,y)=> y.score - x.score);
  }
  return a;
}

function renderCards(filterAction, filterText, sortMode){
  host.innerHTML = "";
  const q = (filterText||"").trim().toUpperCase();
  const sorted = sortSignals(PAYLOAD.signals, sortMode);
  const visible = [];
  for(const s of sorted){
    if(filterAction && filterAction!=="ALL" && s.action!==filterAction) continue;
    if(q && !s.ticker.toUpperCase().includes(q)) continue;
    host.insertAdjacentHTML('beforeend', cardHTML(s));
    visible.push(s);
  }
  // Sparklines (only for the cards we actually rendered)
  for(const s of visible){
    const ctx = document.getElementById(`spark-${s.ticker}`);
    if(!ctx) continue;
    if(charts[s.ticker]) charts[s.ticker].destroy();
    const dates  = s.history.date;
    const closes = s.history.close;
    const color = s.css==='buy'?'#22c55e':s.css==='trim'?'#f59e0b':
                  s.css==='cut'?'#ef4444':s.css==='sell'?'#dc2626':'#7aa2ff';
    charts[s.ticker] = new Chart(ctx,{
      type:'line',
      data:{labels:dates,datasets:[{
        data:closes, borderColor:color, borderWidth:1.5, pointRadius:0,
        tension:0.25, fill:true,
        backgroundColor: color+'22'
      }]},
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false}, tooltip:{
          intersect:false, mode:'index',
          callbacks:{label: ctx => `${ctx.parsed.y.toFixed(2)}`}
        }},
        scales:{x:{display:false},
                y:{display:false, grace:'5%'}}
      }
    });
  }
}

// ---------- Toolbar wiring ----------
let curAction = "ALL";
let curSort   = "name_asc";
const $search = document.getElementById('search');
const $sort   = document.getElementById('sort');

function rerender(){ renderCards(curAction, $search.value, curSort); }

document.querySelectorAll('.toolbar button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.toolbar button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    curAction = btn.dataset.f;
    rerender();
  });
});
$search.addEventListener('input', rerender);
$sort.addEventListener('change', e=>{ curSort = e.target.value; rerender(); });

rerender();
</script>
</body>
</html>
"""
