import { describe, expect, it } from "vitest";
import { buildComparisonChart } from "../src/features/comparisons/chart";

const detail = (runId: string) => ({
  run: { run_id: runId },
  scope: { scope_fingerprint: "scope-1" },
  comparison_curves: [
    { run_id: runId, scope_fingerprint: "scope-1", ts: "2026-09-01T00:00:00Z", strategy_normalized: 1, benchmark_normalized: 1, strategy_drawdown: 0, benchmark_drawdown: 0 },
    { run_id: runId, scope_fingerprint: "scope-1", ts: "2026-09-01T00:01:00Z", strategy_normalized: 1.01, benchmark_normalized: 1.005, strategy_drawdown: -0.01, benchmark_drawdown: -0.005 },
  ],
} as never);

describe("comparison chart adapter", () => {
  it("uses a shared UTC time axis and keeps growth and drawdown panes separate", () => {
    const option = buildComparisonChart([detail("run-a"), detail("run-b")], ["strategy_normalized", "benchmark_normalized", "strategy_drawdown"]);
    const series = option.series as Record<string, unknown>[];
    expect(option.xAxis).toHaveLength(2);
    expect(option.yAxis).toHaveLength(2);
    expect(option.series).toHaveLength(6);
    expect(option.dataZoom).toHaveLength(2);
    expect(series[0]).toMatchObject({ name: "run-a · Strategy growth", xAxisIndex: 0, yAxisIndex: 0 });
    expect(series[2]).toMatchObject({ name: "run-a · Strategy drawdown", xAxisIndex: 1, yAxisIndex: 1 });
  });

  it("preserves missing observations as null gaps", () => {
    const missing = Object.assign(detail("run-a"), { comparison_curves: [{ run_id: "run-a", scope_fingerprint: "scope-1", ts: "2026-09-01T00:00:00Z", strategy_normalized: 1 }] }) as never;
    const option = buildComparisonChart([missing], ["strategy_normalized", "benchmark_normalized"]);
    const series = option.series as { data: unknown[] }[];
    expect(series[1]?.data).toEqual([[Date.parse("2026-09-01T00:00:00Z"), null]]);
  });
});
