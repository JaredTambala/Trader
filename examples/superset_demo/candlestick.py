"""Export a generic ECharts candlestick prototype from the demo read contract."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import psycopg

from .runtime import DemoStack

ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@6.0.0/dist/echarts.min.js"


def load_bars(stack: DemoStack, *, symbol: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
    """Read a bounded OHLCV window through the dedicated demo reader."""
    if not 1 <= limit <= 20_000:
        raise ValueError("limit must be between 1 and 20,000")
    if not symbol:
        raise ValueError("Select exactly one symbol for the candlestick prototype")
    with psycopg.connect(stack.dsn(reader=True)) as connection:
        rows = connection.execute(
            """SELECT symbol, ts, open, high, low, close, volume
            FROM console_read.stock_bars
            WHERE (%s::text IS NULL OR symbol = %s::text) ORDER BY ts LIMIT %s""",
            (symbol, symbol, limit),
        ).fetchall()
    return [{"symbol": r[0], "ts": r[1].isoformat(), "open": float(r[2]),
             "high": float(r[3]), "low": float(r[4]), "close": float(r[5]), "volume": float(r[6])}
            for r in rows]


def render_html(rows: list[dict[str, Any]], *, title: str = "Candlestick · OHLCV") -> str:
    """Render a generic, linked candlestick/volume view."""
    if len({r["symbol"] for r in rows}) > 1:
        raise ValueError("Candles must belong to a single symbol")
    if len({r["ts"] for r in rows}) != len(rows):
        raise ValueError("Duplicate timestamps: select one timeframe and source before charting")
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    heading = json.dumps(title).replace("<", "\\u003c")
    title = escape(title, quote=True)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>html,body,#chart{{margin:0;width:100%;height:100%;background:#11161c;color:#d9e2ec;font-family:system-ui,sans-serif}}</style>
</head><body><div id="chart" role="img" aria-label="{title}"></div>
<script src="{ECHARTS_CDN}"></script><script>
const rows={payload}; const chart=echarts.init(document.getElementById('chart'),null,{{renderer:'canvas'}});
const times=rows.map(r=>r.ts), candles=rows.map(r=>[r.open,r.close,r.low,r.high]), volumes=rows.map(r=>r.volume);
const option={{animation:false,backgroundColor:'#11161c',title:{{text:{heading},left:16,top:12,textStyle:{{color:'#d9e2ec',fontSize:15}}}},
grid:[{{left:64,right:24,top:52,height:'58%'}},{{left:64,right:24,top:'76%',height:'16%'}}],
xAxis:[{{type:'category',data:times,boundaryGap:false,axisLabel:{{color:'#9aa9b8'}},axisPointer:{{show:true}}}},{{type:'category',gridIndex:1,data:times,axisLabel:{{show:false}}}}],
yAxis:[{{scale:true,axisLabel:{{color:'#9aa9b8'}},splitLine:{{lineStyle:{{color:'#26313b'}}}}}},{{gridIndex:1,scale:true,axisLabel:{{color:'#9aa9b8'}},splitLine:{{show:false}}}}],
dataZoom:[{{type:'inside',xAxisIndex:[0,1],filterMode:'none'}},{{type:'slider',xAxisIndex:[0,1],bottom:12,height:18,textStyle:{{color:'#9aa9b8'}}}}],
axisPointer:{{link:[{{xAxisIndex:'all'}}],label:{{backgroundColor:'#52606d'}}}},tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},
series:[{{name:'OHLC',type:'candlestick',data:candles,itemStyle:{{color:'#3fb950',color0:'#f85149',borderColor:'#3fb950',borderColor0:'#f85149'}},markPoint:{{data:[]}},markLine:{{data:[]}}}},{{name:'Volume',type:'bar',xAxisIndex:1,yAxisIndex:1,data:volumes,itemStyle:{{color:p=>candles[p.dataIndex][1]>=candles[p.dataIndex][0]?'#3fb950':'#f85149'}}}}]}};
chart.setOption(option); window.addEventListener('resize',()=>chart.resize());
</script></body></html>'''


def export(stack: DemoStack, output: Path, *, symbol: str | None = None, limit: int = 2000) -> Path:
    """Write a bounded prototype and return its absolute path."""
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(load_bars(stack, symbol=symbol, limit=limit)), encoding="utf-8")
    return output
