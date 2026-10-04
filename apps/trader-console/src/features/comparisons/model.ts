import type { Definition, Evaluation, RunDetail, RecordValue } from "./client";

export type MetricKey = Definition["metric_keys"][number];
export type SeriesKey = Definition["series_keys"][number];
export const METRICS: Record<MetricKey, string> = {
  strategy_total_return: "Strategy return", benchmark_total_return: "Benchmark return",
  strategy_max_drawdown: "Strategy max drawdown", benchmark_max_drawdown: "Benchmark max drawdown",
  strategy_sharpe: "Sharpe", strategy_trade_count: "Trade count", warnings_count: "Warning count",
};
export const SERIES: Record<SeriesKey, string> = {
  strategy_normalized: "Strategy growth", benchmark_normalized: "Benchmark growth",
  strategy_drawdown: "Strategy drawdown", benchmark_drawdown: "Benchmark drawdown",
};
const REASONS: Record<string, string> = {
  missing_scope_fingerprint: "Scope fingerprint unavailable",
  no_comparison_projection: "Comparison evidence unavailable",
  target_run_not_found: "Reference run is unavailable",
  target_missing_scope_fingerprint: "Reference scope fingerprint unavailable",
  scope_mismatch: "Scope differs from the reference run",
  run_not_in_experiment: "Run is no longer in this experiment",
};
export const exclusionLabel = (reason?: string | null) => reason ? REASONS[reason] ?? reason : "Eligible";
export const newDefinition = (): Definition => ({ name: "Untitled comparison", run_ids: [], reference_run_id: null, metric_keys: ["strategy_total_return", "strategy_max_drawdown", "strategy_sharpe"], series_keys: ["strategy_normalized", "strategy_drawdown"] });
export const numberValue = (row: RecordValue | null | undefined, key: string) => typeof row?.[key] === "number" && Number.isFinite(row[key]) ? row[key] as number : null;
export function formatMetric(row: RecordValue | null | undefined, key: MetricKey) {
  const value = numberValue(row, key);
  if (value === null) return "Unavailable";
  return key.includes("return") || key.includes("drawdown") ? `${(value * 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%` : value.toLocaleString("en-US", { maximumFractionDigits: 3 });
}
export const textValue = (value: unknown) => typeof value === "string" && value ? value : "Unavailable";

/** A later detail response must still agree with the evaluated experiment/scope. */
export function evidenceMatches(detail: RunDetail, experimentId: string, evaluation: Evaluation, runId: string) {
  const admission = evaluation.runs.find((row) => row.run_id === runId);
  return admission?.eligible && admission.scope_fingerprint && detail.run.run_id === runId && detail.run.experiment_id === experimentId
    && detail.scope?.scope_fingerprint === admission.scope_fingerprint
    && detail.comparison_summary?.scope_fingerprint === admission.scope_fingerprint
    && detail.comparison_summary?.run_id === runId;
}
