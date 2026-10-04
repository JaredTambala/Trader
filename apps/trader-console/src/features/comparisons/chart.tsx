"use client";
import { useEffect, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import type { RunDetail } from "./client";
import { numberValue, SERIES, type SeriesKey } from "./model";
import styles from "./workspace.module.css";

export function buildComparisonChart(details: RunDetail[], keys: SeriesKey[], start = 0, end = 100): EChartsOption {
  const timestamps = [...new Set(details.flatMap((detail) => detail.comparison_curves.map((row) => typeof row.ts === "string" ? Date.parse(row.ts) : NaN)))].filter(Number.isFinite).sort((a, b) => a - b);
  const min = timestamps[0];
  const max = timestamps.at(-1);
  const panes = ["growth", "drawdown"].filter((pane) => keys.some((key) => key.endsWith("drawdown") === (pane === "drawdown")));
  return {
    animation: false, useUTC: true, backgroundColor: "transparent", textStyle: { color: "#a8b5c5" },
    legend: { type: "scroll", top: 0, textStyle: { color: "#a8b5c5" } },
    tooltip: { trigger: "axis", renderMode: "richText", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: panes.map((_, index) => ({ left: 70, right: 25, top: panes.length === 1 ? 60 : index ? "58%" : 60, height: panes.length === 1 ? "66%" : "30%" })),
    xAxis: panes.map((_, gridIndex) => ({ type: "time", gridIndex, min, max, axisLabel: { hideOverlap: true } })),
    yAxis: panes.map((pane, gridIndex) => ({ type: "value", gridIndex, name: pane === "growth" ? "Growth (×)" : "Drawdown (%)", scale: true, splitLine: { lineStyle: { color: "#303b49" } }, axisLabel: pane === "drawdown" ? { formatter: (value: number) => `${(value * 100).toFixed(1)}%` } : {} })),
    dataZoom: [{ type: "inside", xAxisIndex: panes.map((_, i) => i), filterMode: "filter", start, end }, { type: "slider", xAxisIndex: panes.map((_, i) => i), filterMode: "filter", start, end, height: 22, bottom: 5 }],
    series: details.flatMap((detail, runIndex) => {
      const rows = new Map(detail.comparison_curves.filter((row) => row.run_id === detail.run.run_id && row.scope_fingerprint === detail.scope?.scope_fingerprint).map((row) => [typeof row.ts === "string" ? Date.parse(row.ts) : NaN, row]));
      return keys.map((key) => ({
        name: `${detail.run.run_id} · ${SERIES[key]}`, type: "line" as const,
        xAxisIndex: panes.indexOf(key.endsWith("drawdown") ? "drawdown" : "growth"), yAxisIndex: panes.indexOf(key.endsWith("drawdown") ? "drawdown" : "growth"),
        data: timestamps.map((ts) => [ts, numberValue(rows.get(ts), key)]),
        connectNulls: false, showSymbol: true, symbolSize: 4,
        itemStyle: { color: ["#9bbaff", "#8cdbb3", "#f2c980", "#ffb1ab", "#c7a4f4"][runIndex % 5] },
        lineStyle: { width: 2, type: key.startsWith("benchmark") ? "dashed" as const : "solid" as const },
      }));
    }),
  };
}

export function ComparisonChart({ details, keys }: { details: RunDetail[]; keys: SeriesKey[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState([0, 100]);
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    let chart: import("echarts").ECharts | undefined;
    let observer: ResizeObserver | undefined;
    void import("echarts").then((echarts) => {
      if (disposed || !container.current) return;
      chart = echarts.init(container.current, undefined, { renderer: "svg" });
      chart.setOption(buildComparisonChart(details, keys, range[0], range[1]));
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(container.current);
    }).catch(() => { if (!disposed) setError("Chart could not be loaded. Reload this page to try again."); });
    return () => { disposed = true; observer?.disconnect(); chart?.dispose(); };
  }, [details, keys, range]);
  const hasValues = details.some((detail) => detail.comparison_curves.some((row) => row.run_id === detail.run.run_id && row.scope_fingerprint === detail.scope?.scope_fingerprint && typeof row.ts === "string" && Number.isFinite(Date.parse(row.ts)) && keys.some((key) => numberValue(row, key) !== null)));
  const [rangeStart, rangeEnd] = range;
  return <>
    {error && <p role="alert">{error}</p>}
    {!hasValues && <p>No observations are available for the selected series.</p>}
    <div ref={container} className={styles.chart} role="img" aria-label="Comparison performance curves on a shared UTC timeline" />
    <div className={styles.controls}>
      <label>Zoom start<input aria-label="Zoom start" type="range" min="0" max="99" value={rangeStart ?? 0} onChange={(event) => setRange([Math.min(Number(event.target.value), (rangeEnd ?? 100) - 1), rangeEnd ?? 100])} /></label>
      <label>Zoom end<input aria-label="Zoom end" type="range" min="1" max="100" value={rangeEnd ?? 100} onChange={(event) => setRange([rangeStart ?? 0, Math.max(Number(event.target.value), (rangeStart ?? 0) + 1)])} /></label>
      <button type="button" onClick={() => setRange([0, 100])}>Reset zoom</button>
    </div>
  </>;
}
