import { describe, expect, it } from "vitest";
import { buildChartOption } from "../src/features/market-data/chart";

describe("OHLCV chart adapter", () => {
  it("maps producer OHLCV fields to linked candlestick and volume panes", () => {
    const option = buildChartOption([
      { symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:30:00Z", open: 100, high: 105, low: 99, close: 104, volume: 1234 },
    ]);
    expect(option.series[0]).toMatchObject({ type: "candlestick", data: [[Date.parse("2026-09-10T09:30:00Z"), 100, 104, 99, 105]] });
    expect(option.series[1]).toMatchObject({ type: "bar", data: [[Date.parse("2026-09-10T09:30:00Z"), 1234]] });
    expect(option.dataZoom).toHaveLength(2);
    expect(option.dataZoom).toEqual([
      expect.objectContaining({ type: "inside", filterMode: "filter" }),
      expect.objectContaining({ type: "slider", filterMode: "filter" }),
    ]);
    expect(option.axisPointer).toMatchObject({ link: [{ xAxisIndex: "all" }] });
  });

  it("renders producer-declared overlays, secondary panes, and timestamp-bound signals", () => {
    const ts = "2026-09-10T09:30:00Z";
    const option = buildChartOption(
      [{ symbol: "AAPL", timeframe: "1Min", ts, open: 100, high: 105, low: 99, close: 104, volume: 1234 }],
      [
        {
          run_id: "run-1", session_id: "session-1", cycle_id: "cycle-1", symbol: "AAPL",
          indicator_name: "sma_short_5", series_id: "sma_short_5", series_label: "SMA 5",
          pane: "price", scale_group: "price", unit: "price", series_kind: "line", value: 102,
          bar_ts: ts, signal_name: "sma_crossover", signal_event_id: "signal-1",
          strategy_id: "strategy-1", strategy_version: "1", variant_fingerprint: null, parameters_fingerprint: null, data_scope_id: null,
        },
        {
          run_id: "run-1", session_id: "session-1", cycle_id: "cycle-1", symbol: "AAPL",
          indicator_name: "rsi_14", series_id: "rsi_14", series_label: "RSI 14",
          pane: "secondary", scale_group: "momentum", unit: "index", series_kind: "line", value: 58,
          bar_ts: ts, signal_name: "rsi_threshold", signal_event_id: "signal-1",
          strategy_id: "strategy-1", strategy_version: "1", variant_fingerprint: null, parameters_fingerprint: null, data_scope_id: null,
        },
      ],
      [{
        signal_event_id: "signal-1", run_id: "run-1", session_id: "session-1", cycle_id: "cycle-1",
        symbol: "AAPL", signal_name: "sma_crossover", signal_value: 1, target_qty: 1,
        event_ts: ts, generated_at: ts, mapper_id: "mapper",
      }],
    );
    expect(option.grid).toHaveLength(3);
    expect(option.series).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: "SMA 5", xAxisIndex: 0, yAxisIndex: 0 }),
      expect.objectContaining({ name: "RSI 14", xAxisIndex: 1, yAxisIndex: 1 }),
      expect.objectContaining({ name: "Signals", data: [{ value: [Date.parse(ts), 104], name: "sma_crossover", signalEventId: "signal-1" }] }),
    ]));
  });
});
