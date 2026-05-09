"""HTML report for a BTResult — equity curve, drawdown, monthly returns,
by-action stats, and a trade log."""

from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path

import pandas as pd

from .backtest import BTResult
from .config import REPORTS_DIR


def render(result: BTResult, out_path: Path | None = None) -> Path:
    eq = result.equity_curve.reset_index().rename(columns={"date": "d"})
    eq["d"] = pd.to_datetime(eq["d"]).dt.strftime("%Y-%m-%d")
    eq_data = eq[["d", "equity", "dd"]].to_dict(orient="list")

    if len(result.benchmark_curve):
        bc = result.benchmark_curve.reindex(result.equity_curve.index, method="ffill").dropna()
        bench_data = {
            "d":     bc.index.strftime("%Y-%m-%d").tolist(),
            "value": bc.values.tolist(),
        }
    else:
        bench_data = {"d": [], "value": []}

    monthly = result.monthly_returns
    monthly_data = {
        "label": [d.strftime("%b %Y") for d in monthly.index],
        "ret":   monthly.round(2).tolist(),
    }

    trades = result.trades.copy() if len(result.trades) else pd.DataFrame()
    trades_data = trades.to_dict(orient="records") if len(trades) else []

    payload = {
        "stats":     result.stats,
        "by_action": result.by_action,
        "equity":    eq_data,
        "benchmark": bench_data,
        "monthly":   monthly_data,
        "trades":    trades_data,
        "config":    dc.asdict(result.config),
    }

    out = out_path or (REPORTS_DIR / "backtest.html")
    html = _TPL.replace("__PAYLOAD__", json.dumps(payload, default=str))
    out.write_text(html, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
_TPL = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>SET50 Swing Trade — Backtest Report</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0b1020;--panel:#121a33;--panel2:#0f1730;--txt:#e6ecff;--muted:#8aa0c8;
  --line:#1f2a4d;--accent:#7aa2ff;--green:#22c55e;--amber:#f59e0b;--red:#ef4444}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,Inter,sans-serif}
header{padding:22px 28px;display:flex;justify-content:space-between;
  border-bottom:1px solid var(--line);background:linear-gradient(180deg,#101736,#0b1020)}
header h1{margin:0;font-size:20px}
.meta{color:var(--muted);font-size:13px}
.container{padding:24px 28px;max-width:1400px;margin:0 auto}
h2{font-size:15px;margin:24px 0 10px;letter-spacing:.4px;color:var(--muted);
  text-transform:uppercase}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:14px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.kpi .val{font-size:22px;font-weight:600;margin-top:4px}
.kpi.pos .val{color:var(--green)} .kpi.neg .val{color:var(--red)}
.charts{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.panel h3{margin:0 0 10px;font-size:14px;color:var(--muted);font-weight:600;
  text-transform:uppercase;letter-spacing:.4px}
.cwrap{position:relative;height:280px;width:100%}
.cwrap.short{height:160px}
.bigwrap{position:relative;height:320px;width:100%}
.actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.action{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.action h4{margin:0 0 6px;font-size:13px;font-weight:600;color:var(--accent)}
.action .grid{display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px;color:var(--muted)}
.action .grid b{color:var(--txt)}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.3px;font-size:11px}
tr:hover td{background:rgba(255,255,255,.02)}
.tbl-wrap{max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.win{color:var(--green)} .loss{color:var(--red)}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}.charts{grid-template-columns:1fr}}
</style>
</head><body>

<header>
  <div>
    <h1>📊 SET50 Swing Trade — Backtest Report</h1>
    <div class="meta" id="meta"></div>
  </div>
  <div class="meta">Walk-forward · weekly rebalance · long-only</div>
</header>

<div class="container">
  <div class="kpis" id="kpis"></div>

  <h2>Performance vs SET buy-and-hold</h2>
  <div class="panel"><div class="bigwrap"><canvas id="eq"></canvas></div></div>

  <h2>Drawdown</h2>
  <div class="panel"><div class="cwrap short"><canvas id="dd"></canvas></div></div>

  <h2>Monthly returns</h2>
  <div class="panel"><div class="cwrap short"><canvas id="mo"></canvas></div></div>

  <h2>Per-signal performance</h2>
  <div class="panel actions" id="actions"></div>

  <h2>Trade log <span class="meta" id="ntrades"></span></h2>
  <div class="panel" style="padding:0">
    <div class="tbl-wrap"><table id="trades">
      <thead><tr>
        <th>Ticker</th><th>Entry</th><th>Open</th><th>Open ฿</th>
        <th>Close</th><th>Close ฿</th><th>Reason</th>
        <th>Size ฿</th><th>P&amp;L ฿</th><th>P&amp;L %</th>
      </tr></thead><tbody></tbody>
    </table></div>
  </div>
</div>

<script>
const D = __PAYLOAD__;
const fmt = (x,d=2) => (x===null||x===undefined||isNaN(x))?"–":Number(x).toFixed(d);
const fmt0 = x => fmt(x,0);
const pct = (x,d=1) => (x===null||x===undefined||isNaN(x))?"–":(x>=0?"+":"")+Number(x).toFixed(d)+"%";
const thb = x => "฿" + Math.round(x).toLocaleString();

document.getElementById('meta').textContent =
  `${D.equity.d[0]} → ${D.equity.d[D.equity.d.length-1]}  ·  capital ${thb(D.config.starting_capital)}  ·  ${D.trades.length} trades`;

// KPIs
const cards = [
  ["Total Return", pct(D.stats.total_return_pct), D.stats.total_return_pct>=0?"pos":"neg"],
  ["CAGR",         pct(D.stats.cagr_pct),         D.stats.cagr_pct>=0?"pos":"neg"],
  ["Max Drawdown", pct(D.stats.max_drawdown_pct), "neg"],
  ["Sharpe",       fmt(D.stats.sharpe,2),         D.stats.sharpe>=1?"pos":""],
  ["Win Rate",     fmt(D.stats.win_rate_pct,1)+"%", D.stats.win_rate_pct>=50?"pos":""],
  ["Alpha vs SET", pct(D.stats.alpha_vs_set_pct), D.stats.alpha_vs_set_pct>=0?"pos":"neg"],
];
const kpiHost = document.getElementById('kpis');
for(const [l,v,c] of cards){
  const el=document.createElement('div'); el.className=`kpi ${c||""}`;
  el.innerHTML=`<div class="label">${l}</div><div class="val">${v}</div>`;
  kpiHost.appendChild(el);
}

// Equity curve
new Chart(document.getElementById('eq'), {
  type:'line',
  data:{labels:D.equity.d,datasets:[
    {label:'Strategy', data:D.equity.equity, borderColor:'#7aa2ff',
     backgroundColor:'#7aa2ff22', borderWidth:1.7, pointRadius:0, fill:true, tension:0.2},
    {label:'SET buy-hold', data:D.benchmark.value, borderColor:'#94a3b8',
     borderDash:[4,3], borderWidth:1.3, pointRadius:0, tension:0.2, fill:false}
  ]},
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{labels:{color:'#cbd5e1'}}, tooltip:{intersect:false,mode:'index'}},
    scales:{
      x:{ticks:{color:'#8aa0c8',maxTicksLimit:8},grid:{color:'#1f2a4d'}},
      y:{ticks:{color:'#8aa0c8',callback:v=>thb(v)},grid:{color:'#1f2a4d'}}
    }
  }
});

// Drawdown
new Chart(document.getElementById('dd'), {
  type:'line',
  data:{labels:D.equity.d,datasets:[{
    data:D.equity.dd, borderColor:'#ef4444', backgroundColor:'#ef444422',
    borderWidth:1.3, pointRadius:0, fill:true, tension:0.2}]},
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{display:false}, tooltip:{intersect:false,mode:'index',
      callbacks:{label: c=> c.parsed.y.toFixed(2)+"%"}}},
    scales:{
      x:{ticks:{color:'#8aa0c8',maxTicksLimit:8},grid:{color:'#1f2a4d'}},
      y:{ticks:{color:'#8aa0c8',callback:v=>v+"%"},grid:{color:'#1f2a4d'}}
    }
  }
});

// Monthly
new Chart(document.getElementById('mo'),{
  type:'bar',
  data:{labels:D.monthly.label, datasets:[{
    data:D.monthly.ret,
    backgroundColor:D.monthly.ret.map(v=>v>=0?'#22c55e99':'#ef444499'),
    borderColor:D.monthly.ret.map(v=>v>=0?'#22c55e':'#ef4444'),
    borderWidth:1
  }]},
  options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(2)+"%"}}},
    scales:{x:{ticks:{color:'#8aa0c8',maxTicksLimit:12},grid:{color:'#1f2a4d'}},
            y:{ticks:{color:'#8aa0c8',callback:v=>v+"%"},grid:{color:'#1f2a4d'}}}
  }
});

// By-action panels
const aHost = document.getElementById('actions');
const order = ["BUY-STRONG","BUY-DIP","exit:TRIM","exit:CUT","exit:SELL-STRONG","exit:STOP","exit:EOH"];
for(const k of order){
  const v = D.by_action[k]; if(!v) continue;
  const isExit = k.startsWith("exit:");
  const el = document.createElement('div'); el.className='action';
  el.innerHTML = `<h4>${k}</h4>
    <div class="grid">
      <div># trades</div><b>${v.n}</b>
      <div>Win rate</div><b>${fmt(v.win_rate,1)}%</b>
      <div>Avg P&amp;L</div><b class="${v.avg_pnl_pct>=0?'win':'loss'}">${pct(v.avg_pnl_pct)}</b>
      ${!isExit?`<div>Best</div><b class="win">${pct(v.best_pct)}</b>
                 <div>Worst</div><b class="loss">${pct(v.worst_pct)}</b>`:''}
    </div>`;
  aHost.appendChild(el);
}

// Trades table
document.getElementById('ntrades').textContent = `(${D.trades.length} trades)`;
const tb = document.querySelector('#trades tbody');
const sorted = D.trades.slice().sort((a,b)=> a.close_date.localeCompare(b.close_date));
for(const t of sorted){
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${t.ticker.replace('.BK','')}</td>
    <td>${t.entry_action}</td>
    <td>${t.open_date}</td>
    <td>${fmt(t.open_price)}</td>
    <td>${t.close_date}</td>
    <td>${fmt(t.close_price)}</td>
    <td>${t.reason}</td>
    <td>${thb(t.size_thb)}</td>
    <td class="${t.pnl_thb>=0?'win':'loss'}">${thb(t.pnl_thb)}</td>
    <td class="${t.pnl_pct>=0?'win':'loss'}">${pct(t.pnl_pct)}</td>`;
  tb.appendChild(tr);
}
</script>
</body></html>
"""
