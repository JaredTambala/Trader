"use client";

import { useEffect, useRef } from "react";
import type { BarPoint, IndicatorSeriesPoint, SignalMarker } from "./client";
import styles from "./market-data-workspace.module.css";

type ChartProps = {
  bars: readonly BarPoint[];
  indicatorSeries?: readonly IndicatorSeriesPoint[];
  signalMarkers?: readonly SignalMarker[];
};

export function buildChartOption(
  bars: readonly BarPoint[],
  indicatorSeries: readonly IndicatorSeriesPoint[] = [],
  signalMarkers: readonly SignalMarker[] = [],
) {
  const candleData = bars.map((bar) => [
    Date.parse(bar.ts),
    bar.open ?? null,
    bar.close ?? null,
    bar.low ?? null,
    bar.high ?? null,
  ]);
  const volumeData = bars.map((bar) => [Date.parse(bar.ts), bar.volume ?? null]);
  const secondaryGroups = [...new Map(
    indicatorSeries
      .filter((point) => point.pane !== "price" && point.pane !== "unknown")
      .map((point) => [`${point.pane}:${point.scale_group}`, point] as const),
  ).values()];
  const secondaryCount = secondaryGroups.length;
  const priceHeight = secondaryCount ? 44 : 57;
  const secondaryHeight = secondaryCount ? Math.max(10, Math.floor((100 - priceHeight - 17) / secondaryCount) - 2) : 0;
  const grids = [
    { left: 64, right: 24, top: 24, height: `${priceHeight}%` },
    ...secondaryGroups.map((_, index) => ({
      left: 64,
      right: 24,
      top: `${priceHeight + index * (secondaryHeight + 2) + 3}%`,
      height: `${secondaryHeight}%`,
    })),
    { left: 64, right: 24, top: secondaryCount ? "83%" : "70%", height: "14%" },
  ];
  const volumeGridIndex = grids.length - 1;
  const seriesGroups = [...new Map(
    indicatorSeries.map((point) => [`${point.pane}:${point.scale_group}:${point.series_id}`, [] as IndicatorSeriesPoint[]]),
  ).entries()];
  for (const point of indicatorSeries) {
    seriesGroups.find(([key]) => key === `${point.pane}:${point.scale_group}:${point.series_id}`)?.[1].push(point);
  }
  const priceSeries = seriesGroups
    .filter(([, points]) => points[0]?.pane === "price" && points[0]?.series_kind !== "unknown")
    .map(([, points]) => ({
      name: points[0]!.series_label,
      type: points[0]!.series_kind === "bar" ? "bar" : "line",
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: points.map((point) => [Date.parse(point.bar_ts), point.value]),
      showSymbol: false,
      lineStyle: { width: 1.5 },
    }));
  const secondarySeries = secondaryGroups.flatMap((group, index) => {
    const groupKey = `${group.pane}:${group.scale_group}`;
    return seriesGroups
      .filter(([, points]) => points[0]?.pane !== "price" && points[0]?.pane !== "unknown" && points[0]?.series_kind !== "unknown" && `${points[0]!.pane}:${points[0]!.scale_group}` === groupKey)
      .map(([, points]) => ({
        name: points[0]!.series_label,
        type: points[0]!.series_kind === "bar" ? "bar" : "line",
        xAxisIndex: index + 1,
        yAxisIndex: index + 1,
        data: points.map((point) => [Date.parse(point.bar_ts), point.value]),
        showSymbol: false,
      }));
  });
  const markerData = signalMarkers.flatMap((marker) => {
    const bar = bars.find((candidate) => candidate.symbol === marker.symbol && candidate.ts === marker.event_ts);
    return bar?.close == null || marker.event_ts == null
      ? []
      : [{ value: [Date.parse(marker.event_ts), bar.close], name: marker.signal_name, signalEventId: marker.signal_event_id }];
  });
  return {
    animation: false,
    backgroundColor: "transparent",
    grid: grids,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", link: [{ xAxisIndex: "all" }] },
      valueFormatter: (value: unknown) => typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 6 }) : "—",
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: [
      { type: "time", gridIndex: 0, axisLabel: { hideOverlap: true } },
      ...secondaryGroups.map((_, index) => ({ type: "time", gridIndex: index + 1, axisLabel: { show: false }, axisPointer: { show: true } })),
      { type: "time", gridIndex: volumeGridIndex, axisLabel: { show: false }, axisPointer: { show: true } },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "#2b3644" } } },
      ...secondaryGroups.map((group, index) => ({ name: group.scale_group, scale: true, gridIndex: index + 1, splitLine: { lineStyle: { color: "#202a35" } } })),
      { scale: true, gridIndex: volumeGridIndex, splitLine: { lineStyle: { color: "#202a35" } }, axisLabel: { formatter: "{value}" } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: grids.map((_, index) => index), filterMode: "filter" },
      { type: "slider", xAxisIndex: grids.map((_, index) => index), filterMode: "filter", height: 22, bottom: 2 },
    ],
    series: [
      {
        name: "OHLC",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: candleData,
        itemStyle: {
          color: "#78d6b1",
          color0: "#f28b82",
          borderColor: "#78d6b1",
          borderColor0: "#f28b82",
        },
      },
      {
        name: "Volume",
        type: "bar",
        xAxisIndex: volumeGridIndex,
        yAxisIndex: volumeGridIndex,
        data: volumeData,
        itemStyle: { color: "#7799d6", opacity: 0.7 },
      },
      ...priceSeries,
      ...secondarySeries,
      {
        name: "Signals",
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: markerData,
        symbolSize: 9,
        itemStyle: { color: "#f7c66b" },
        label: { show: false },
      },
    ],
  };
}

export function MarketChart({ bars, indicatorSeries = [], signalMarkers = [] }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let chart: { setOption: (option: ReturnType<typeof buildChartOption>) => void; resize: () => void; dispose: () => void } | undefined;
    let observer: ResizeObserver | undefined;
    const resizeListener = () => chart?.resize();

    async function mount() {
      const echarts = await import("echarts");
      if (disposed || !containerRef.current) return;
      chart = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
      chart.setOption(buildChartOption(bars, indicatorSeries, signalMarkers));
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => chart?.resize());
        observer.observe(containerRef.current);
      } else {
        window.addEventListener("resize", resizeListener);
      }
    }

    void mount();
    return () => {
      disposed = true;
      observer?.disconnect();
      window.removeEventListener("resize", resizeListener);
      chart?.dispose();
    };
  }, [bars, indicatorSeries, signalMarkers]);

  return <div ref={containerRef} className={styles.marketChart} role="img" aria-label="OHLC candlestick and volume chart" />;
}
