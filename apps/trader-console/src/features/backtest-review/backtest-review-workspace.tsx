"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  loadExperimentRuns,
  loadExperiments,
  loadRunDetail,
  loadRiskDecisions,
  type RiskDecisionOutcome,
  type ResourceRecord,
  type RunDetail,
} from "./client";
import styles from "./backtest-review-workspace.module.css";
import { ConsoleShell } from "../shell/console-shell";

type RequestState = "loading" | "ready" | "error";
type Section = "trades" | "positions" | "lifecycle" | "evidence";

type ReviewLink = {
  experimentId?: string;
  runId?: string;
  cycleId?: string;
  clientOrderId?: string;
};

function readReviewLink(): ReviewLink {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  return {
    experimentId: params.get("experiment_id") || undefined,
    runId: params.get("run_id") || undefined,
    cycleId: params.get("cycle_id") || undefined,
    clientOrderId: params.get("client_order_id") || undefined,
  };
}

function formatDate(value: unknown) {
  if (typeof value !== "string") return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function experimentLabel(experimentId: string) {
  return experimentId === "standalone_backtests" ? "All backtests" : experimentId;
}

function formatValue(value: unknown, digits = 6) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: digits });
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function numberValue(record: ResourceRecord | undefined, key: string) {
  const value = record?.[key];
  return typeof value === "number" ? value : null;
}

function percentage(value: number | null) {
  return value === null ? "—" : `${(value * 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
}

function runState(status: string) {
  const normalized = status.toLowerCase().replace(/[ -]/g, "_");
  if (["failed", "error"].includes(normalized)) return { label: "Failed", className: styles.statusFailed };
  if (["partial", "incomplete", "zero_trade", "zero_trades", "no_trades"].includes(normalized)) return { label: normalized === "partial" ? "Partial" : "Zero trades", className: styles.statusWarning };
  if (["completed", "complete", "success", "succeeded"].includes(normalized)) return { label: "Completed", className: styles.statusCompleted };
  return { label: status || "Unknown", className: styles.status };
}

function recordTitle(record: ResourceRecord | undefined, keys: string[]) {
  if (!record) return "—";
  const key = keys.find((candidate) => record[candidate] !== undefined && record[candidate] !== null);
  return key ? formatValue(record[key]) : "—";
}

function LineChart({ points, drawdown = false }: { points: ResourceRecord[]; drawdown?: boolean }) {
  const series = points.map((point) => {
    const key = drawdown ? "strategy_drawdown" : "strategy_equity";
    const benchmarkKey = drawdown ? "benchmark_drawdown" : "benchmark_equity";
    return {
      ts: point.ts,
      strategy: typeof point[key] === "number" ? point[key] as number : null,
      benchmark: typeof point[benchmarkKey] === "number" ? point[benchmarkKey] as number : null,
    };
  }).filter((point) => point.strategy !== null || point.benchmark !== null);
  const values = series.flatMap((point) => [point.strategy, point.benchmark]).filter((value): value is number => value !== null);
  if (!values.length) return <p className={styles.empty}>{drawdown ? "No comparison curve is available for this run." : "No equity curve is available for this run."}</p>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const path = (key: "strategy" | "benchmark") => series.map((point, index) => {
    const value = point[key];
    if (value === null) return "";
    const x = series.length === 1 ? 0 : (index / (series.length - 1)) * 100;
    const y = 92 - ((value - min) / spread) * 84;
    return `${index === 0 || !series[index - 1]?.[key] ? "M" : "L"}${x.toFixed(3)} ${y.toFixed(3)}`;
  }).filter(Boolean).join(" ");
  return <>
    <svg className={styles.chart} viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={drawdown ? "Strategy and benchmark drawdown chart" : "Strategy and benchmark equity chart"}>
      <line x1="0" y1="92" x2="100" y2="92" stroke="#303b49" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
      <path d={path("strategy")} fill="none" stroke={drawdown ? "#ffb1ab" : "#9bbaff"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <path d={path("benchmark")} fill="none" stroke="#f2c980" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
    <div className={styles.legend}><span className={drawdown ? styles.drawdown : ""}>Strategy</span><span className={styles.benchmark}>Benchmark</span><span>{formatValue(series[0]?.ts)} → {formatValue(series.at(-1)?.ts)}</span></div>
  </>;
}

function EvidenceTable({ detail, section }: { detail: RunDetail; section: Section }) {
  if (section === "trades") {
    return <DataTable caption="Executed trades" rows={detail.trades} columns={[["fill_ts", "Fill time"], ["symbol", "Symbol"], ["side", "Side"], ["fill_qty", "Quantity"], ["fill_price", "Price"], ["realized_pnl", "Realized P&L"]]} />;
  }
  if (section === "positions") {
    return <DataTable caption="Position snapshots" rows={detail.positions} columns={[["last_ts", "Mark time"], ["symbol", "Symbol"], ["qty", "Quantity"], ["avg_price", "Average price"], ["last_price", "Last price"], ["unrealized_pnl", "Unrealized P&L"]]} />;
  }
  if (section === "lifecycle") {
    return <div>
      <DataTable caption="Signal lifecycle" rows={detail.signals} columns={[["generated_at", "Generated"], ["symbol", "Symbol"], ["signal_name", "Signal"], ["signal_value", "Value"], ["target_qty", "Target quantity"]]} />
      <div style={{ marginTop: "18px" }}><DataTable caption="Order lifecycle" rows={detail.orders} columns={[["created_at", "Created"], ["symbol", "Symbol"], ["side", "Side"], ["qty", "Quantity"], ["status", "Status"]]} /></div>
      <div style={{ marginTop: "18px" }}><DataTable caption="Fill lifecycle" rows={detail.fills} columns={[["fill_ts", "Filled"], ["symbol", "Symbol"], ["fill_qty", "Quantity"], ["fill_price", "Price"], ["fee_amount", "Fee"]]} /></div>
    </div>;
  }
  return <div className={styles.definitionGrid}>
    <div><dt>Signal events</dt><dd>{detail.signals.length || recordTitle(detail.evidence_coverage ?? undefined, ["signal_events_status"])}</dd></div>
    <div><dt>Orders</dt><dd>{detail.orders.length || recordTitle(detail.evidence_coverage ?? undefined, ["order_events_status"])}</dd></div>
    <div><dt>Fills</dt><dd>{detail.fills.length || recordTitle(detail.evidence_coverage ?? undefined, ["fill_events_status"])}</dd></div>
    <div><dt>Indicators</dt><dd>{detail.indicator_series.length}</dd></div>
    <div><dt>Warnings</dt><dd>{detail.warnings.length || "None recorded"}</dd></div>
    <div><dt>Provenance entries</dt><dd>{detail.provenance.length}</dd></div>
  </div>;
}

function RiskControls({ detail }: { detail: RunDetail }) {
  const summary = detail.risk_summary;
  const [reviewLink] = useState(readReviewLink);
  const [managerFilter, setManagerFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState<RiskDecisionOutcome | "">("");
  const [cycleFilter, setCycleFilter] = useState(() => reviewLink.runId === detail.run.run_id ? reviewLink.cycleId ?? "" : "");
  const [orderFilter, setOrderFilter] = useState(() => reviewLink.runId === detail.run.run_id ? reviewLink.clientOrderId ?? "" : "");
  const [offset, setOffset] = useState(0);
  const [traceState, setTraceState] = useState<RequestState>("loading");
  const [traceError, setTraceError] = useState<string | null>(null);
  const [tracePage, setTracePage] = useState<Awaited<ReturnType<typeof loadRiskDecisions>> | null>(null);
  const [tracePageKey, setTracePageKey] = useState("");
  const traceLimit = 25;
  const traceRequestKey = [detail.run.run_id, managerFilter, outcomeFilter, cycleFilter, orderFilter, offset].join("|");

  useEffect(() => {
    if (!summary || summary.risk_evidence_status === "unavailable") {
      return;
    }
    const controller = new AbortController();
    void loadRiskDecisions(controller.signal, detail.run.run_id, {
      manager_id: managerFilter || undefined,
      outcome: outcomeFilter || undefined,
      cycle_id: cycleFilter || undefined,
      client_order_id: orderFilter || undefined,
      limit: traceLimit,
      offset,
    }).then((response) => {
      setTracePage(response);
      setTracePageKey(traceRequestKey);
      setTraceState("ready");
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setTracePageKey(traceRequestKey);
      setTraceState("error");
      setTraceError(reason instanceof Error ? reason.message : "Risk decisions could not be loaded.");
    });
    return () => controller.abort();
  }, [detail.run.run_id, summary, managerFilter, outcomeFilter, cycleFilter, orderFilter, offset, traceRequestKey]);

  if (!summary || summary.risk_evidence_status === "unavailable") {
    return <section className={styles.panel} aria-labelledby="risk-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>RISK CONTROLS</p><h2 id="risk-heading">Risk evidence unavailable</h2></div></div><p className={styles.scopeNotice}>This run does not publish a risk composition or per-manager decision trace. The absence of a fill is not treated as a risk block.</p></section>;
  }
  const visibleTracePage = tracePageKey === traceRequestKey ? tracePage : null;
  const visibleTraceState = tracePageKey === traceRequestKey ? traceState : "loading";
  const decisions = visibleTracePage?.items ?? [];
  const rejectedRiskOrderIds = new Set(
    detail.risk_decisions
      .filter((decision) => decision.outcome === "rejected" && decision.client_order_id)
      .map((decision) => decision.client_order_id),
  );
  const hasBrokerRejection = detail.orders.some((order) => {
    const status = String(order.status ?? "").toLowerCase();
    const orderId = order.client_order_id;
    return ["rejected", "broker_rejected", "failed"].includes(status)
      && (orderId === undefined || orderId === null || !rejectedRiskOrderIds.has(String(orderId)));
  });
  const interpretations: string[] = [];
  if (summary.blocked_count > 0) interpretations.push("Risk block recorded");
  if (hasBrokerRejection) interpretations.push("Broker rejection recorded");
  if (!detail.signals.length && !detail.signal_markers.length && !detail.orders.length && summary.evaluated_count === 0) {
    interpretations.push("No signal observed");
  }
  if (detail.orders.length > 0 && !detail.fills.length && summary.blocked_count === 0 && !hasBrokerRejection) {
    interpretations.push("Order evidence has no fills");
  }
  const managerIds = [...new Set(detail.risk_composition.map((manager) => manager.manager_id))];
  return <section className={styles.panel} aria-labelledby="risk-heading">
    <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>RISK CONTROLS</p><h2 id="risk-heading">Composition and decisions</h2></div><span className={styles.resultCount}>{summary.composition_fingerprint ?? "No composition fingerprint"}</span></div>
    <dl className={styles.metricGrid}>
      <div className={styles.metric}><dt>Evaluated</dt><dd>{formatValue(summary.evaluated_count)}</dd></div>
      <div className={styles.metric}><dt>Approved</dt><dd>{formatValue(summary.approved_count)}</dd></div>
      <div className={styles.metric}><dt>Transformed</dt><dd>{formatValue(summary.transformed_count)}</dd></div>
      <div className={styles.metric}><dt>Rejected</dt><dd>{formatValue(summary.rejected_count)}</dd></div>
      <div className={styles.metric}><dt>Risk blocks</dt><dd>{formatValue(summary.blocked_count)}</dd></div>
    </dl>
    {interpretations.length > 0 && <div className={styles.scopeNotice}><strong>Outcome interpretation</strong><ul className={styles.statusList}>{interpretations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    <div style={{ marginTop: "20px" }}><DataTable caption="Risk manager composition" rows={detail.risk_composition} columns={[["manager_position", "Order"], ["manager_id", "Manager"], ["manager_type", "Implementation"], ["catalogue_version", "Catalogue"], ["parameters", "Parameters"]]} /></div>
    <div style={{ marginTop: "20px" }}>
      <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>TRACE FILTERS</p><h3>Manager decisions</h3></div><span className={styles.resultCount}>{visibleTracePage ? `${visibleTracePage.page.total} matching decisions` : ""}</span></div>
      <div className={styles.selectorGrid}>
        <label className={styles.field}><span>Manager</span><select aria-label="Risk manager filter" value={managerFilter} onChange={(event) => { setOffset(0); setManagerFilter(event.target.value); }}><option value="">All managers</option>{managerIds.map((managerId) => <option value={managerId} key={managerId}>{managerId}</option>)}</select></label>
        <label className={styles.field}><span>Outcome</span><select aria-label="Risk outcome filter" value={outcomeFilter} onChange={(event) => { setOffset(0); setOutcomeFilter(event.target.value as RiskDecisionOutcome | ""); }}><option value="">All outcomes</option><option value="approved">Approved</option><option value="transformed">Transformed</option><option value="rejected">Rejected</option></select></label>
        <label className={styles.field}><span>Cycle ID</span><input aria-label="Risk cycle filter" value={cycleFilter} onChange={(event) => { setOffset(0); setCycleFilter(event.target.value); }} /></label>
        <label className={styles.field}><span>Order ID</span><input aria-label="Risk order filter" value={orderFilter} onChange={(event) => { setOffset(0); setOrderFilter(event.target.value); }} /></label>
      </div>
      {visibleTraceState === "loading" && <p className={styles.loading} role="status">Loading risk decision trace…</p>}
      {visibleTraceState === "error" && <div className={styles.errorBox} role="alert"><p>{traceError ?? "Risk decisions could not be loaded."}</p></div>}
      {visibleTraceState === "ready" && <>
        <DataTable caption="Risk decision trace" rows={decisions} columns={[["decision_ts", "Decision"], ["cycle_id", "Cycle"], ["client_order_id", "Order"], ["manager_id", "Manager"], ["manager_position", "Position"], ["outcome", "Outcome"], ["reason_code", "Reason"], ["before_qty", "Before qty"], ["after_qty", "After qty"]]} renderCell={(row, key) => {
          const value = row[key];
          if ((key === "cycle_id" || key === "client_order_id") && value !== null && value !== undefined && value !== "") {
            const params = new URLSearchParams({ experiment_id: detail.run.experiment_id, run_id: detail.run.run_id });
            if (row.cycle_id) params.set("cycle_id", String(row.cycle_id));
            if (row.client_order_id) params.set("client_order_id", String(row.client_order_id));
            const label = key === "cycle_id" ? `Open risk decision for cycle ${String(value)}` : `Open risk decision for order ${String(value)}`;
            return <a className={styles.evidenceLink} href={`/backtests?${params.toString()}`} aria-label={label}>{formatValue(value)}</a>;
          }
          return undefined;
        }} />
        {visibleTracePage && <div className={styles.contextLine}><span>Showing {visibleTracePage.items.length ? offset + 1 : 0}–{offset + visibleTracePage.items.length} of {visibleTracePage.page.total}</span><button className={styles.secondaryButton} type="button" onClick={() => setOffset(Math.max(0, offset - traceLimit))} disabled={offset === 0}>Previous</button><button className={styles.secondaryButton} type="button" onClick={() => setOffset(offset + traceLimit)} disabled={!visibleTracePage.page.has_more}>Next</button></div>}
      </>}
    </div>
  </section>;
}

function DataTable({ caption, rows, columns, renderCell }: { caption: string; rows: readonly Record<string, unknown>[]; columns: [string, string][]; renderCell?: (row: Record<string, unknown>, key: string) => ReactNode }) {
  if (!rows.length) return <p className={styles.empty}>No {caption.toLowerCase()} were published for this run.</p>;
  return <div className={styles.tableWrap}><table><caption className={styles.srOnly}>{caption}</caption><thead><tr>{columns.map(([, label]) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${String(row.run_id ?? "row")}-${index}`}>{columns.map(([key]) => <td key={key}>{renderCell?.(row, key) ?? (key.endsWith("_ts") || key === "fill_ts" || key === "created_at" ? formatDate(row[key]) : formatValue(row[key]))}</td>)}</tr>)}</tbody></table></div>;
}

export function BacktestReviewWorkspace() {
  const [reviewLink] = useState(readReviewLink);
  const [experiments, setExperiments] = useState<Awaited<ReturnType<typeof loadExperiments>>["items"]>([]);
  const [experimentId, setExperimentId] = useState(reviewLink.experimentId ?? "");
  const [runs, setRuns] = useState<Awaited<ReturnType<typeof loadExperimentRuns>>["items"]>([]);
  const [runId, setRunId] = useState(reviewLink.runId ?? "");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [state, setState] = useState<RequestState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [section, setSection] = useState<Section>("trades");

  useEffect(() => {
    const controller = new AbortController();
    void loadExperiments(controller.signal).then((response) => {
      setExperiments(response.items);
      setExperimentId((current) => current && response.items.some((item) => item.experiment_id === current) ? current : response.items[0]?.experiment_id ?? "");
      if (!response.items.length) setState("ready");
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setState("error");
      setError(reason instanceof Error ? reason.message : "Experiments could not be loaded.");
    });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (!experimentId) return;
    const controller = new AbortController();
    void loadExperimentRuns(controller.signal, experimentId).then((response) => {
      setRuns(response.items);
      setRunId((current) => current && (current === reviewLink.runId || response.items.some((item) => item.run_id === current)) ? current : response.items[0]?.run_id ?? "");
      if (!response.items.length) setState("ready");
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setState("error");
      setError(reason instanceof Error ? reason.message : "Experiment runs could not be loaded.");
    });
    return () => controller.abort();
  }, [experimentId, reviewLink.runId]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    void loadRunDetail(controller.signal, runId).then((response) => { setDetail(response); setState("ready"); }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setState("error");
      setError(reason instanceof Error ? reason.message : "Backtest run could not be loaded.");
    });
    return () => controller.abort();
  }, [runId]);

  const selectedRun = useMemo(() => runs.find((run) => run.run_id === runId), [runId, runs]);
  const status = detail ? runState(detail.run.status) : selectedRun ? runState(selectedRun.status) : null;
  const scope = detail?.scope ?? undefined;
  const performance = detail?.performance ?? undefined;

  return <ConsoleShell><div className={styles.shell}>
    <main className={styles.main}>
      <div className={styles.heading}><div><p className={styles.eyebrow}>BACKTEST REVIEW</p><h1>Understand one run</h1><p className={styles.subtitle}>Inspect published results, assumptions, curves, execution evidence and warnings with their experiment and scope context.</p></div><button className={styles.button} type="button" onClick={() => setRevision((value) => value + 1)} disabled={state === "loading"}>{state === "loading" ? "Loading…" : "Refresh"}<span aria-hidden="true">↻</span></button></div>
      <section className={styles.panel} aria-labelledby="selection-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>SELECT</p><h2 id="selection-heading">Experiment and run</h2></div><span className={styles.resultCount}>{experiments.length} experiment{experiments.length === 1 ? "" : "s"} · {runs.length} run{runs.length === 1 ? "" : "s"}</span></div>{state === "error" && <div className={styles.errorBox} role="alert"><p>{error}</p><button className={styles.secondaryButton} type="button" onClick={() => { setState("loading"); setError(null); setRevision((value) => value + 1); }}>Retry</button></div>}{state !== "error" && experiments.length === 0 && <p className={styles.empty}>No published experiments are available.</p>}{experiments.length > 0 && <div className={styles.selectorGrid}><label className={styles.field}><span>Experiment</span><select aria-label="Experiment" value={experimentId} onChange={(event) => { setState("loading"); setError(null); setDetail(null); setRuns([]); setRunId(""); setExperimentId(event.target.value); }}>{experiments.map((experiment) => <option value={experiment.experiment_id} key={experiment.experiment_id}>{experimentLabel(experiment.experiment_id)} · {experiment.run_count} runs</option>)}</select></label><label className={styles.field}><span>Run</span><select aria-label="Backtest run" value={runId} onChange={(event) => { setState("loading"); setError(null); setDetail(null); setRunId(event.target.value); }} disabled={!runs.length}>{runs.length ? runs.map((run) => <option value={run.run_id} key={run.run_id}>{run.strategy_name ?? run.strategy_id ?? "Unnamed strategy"} · {run.status} · {run.run_id}</option>) : <option value="">No runs published</option>}</select></label></div>}{selectedRun && <p className={styles.contextLine}><span>Scope: {selectedRun.scope_fingerprint ?? "not published"}</span><span>Window: {formatDate(selectedRun.start_ts)} → {formatDate(selectedRun.end_ts)}</span><span>Symbols: {selectedRun.symbols.join(", ") || "—"}</span></p>}</section>
      {detail && status && <><section className={styles.panel} aria-labelledby="run-heading"><div className={styles.runHeader}><div><p className={styles.eyebrow}>RUN IDENTITY</p><h2 className={styles.runTitle} id="run-heading">{detail.run.strategy_name ?? detail.run.strategy_id ?? "Unnamed strategy"}</h2><p className={styles.runId}>{detail.run.run_id}</p></div><span className={`${styles.status} ${status.className}`}>{status.label}</span></div><p className={styles.contextLine}><span>Experiment {detail.run.experiment_id}</span><span>{detail.run.asset_class ?? "Unknown asset"} · {detail.run.timeframe ?? "Unknown timeframe"}</span><span>{detail.run.symbols.join(", ") || "No symbols"}</span><span>Created {formatDate(detail.run.created_at)}</span></p>{!scope && <p className={styles.scopeNotice}><strong>Scope evidence unavailable.</strong> Performance metrics are withheld until the producer publishes the run scope.</p>}{scope && <dl className={styles.definitionGrid}><div><dt>Scope fingerprint</dt><dd>{formatValue(scope.scope_fingerprint)}</dd></div><div><dt>Data scope</dt><dd>{formatValue(scope.data_scope_id)}</dd></div><div><dt>Benchmark</dt><dd>{formatValue(scope.benchmark_id)}</dd></div><div><dt>Replay window</dt><dd>{formatDate(scope.replay_start)} → {formatDate(scope.replay_end)}</dd></div><div><dt>Initial cash</dt><dd>{formatValue(scope.initial_cash)}</dd></div><div><dt>Variant</dt><dd>{formatValue(scope.variant_strategy_id ?? scope.variant_fingerprint)}</dd></div></dl>}</section>{scope && performance && <section className={styles.panel} aria-labelledby="performance-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>PERFORMANCE</p><h2 id="performance-heading">Scoped result summary</h2></div><span className={styles.resultCount}>Observed {formatDate(performance.observed_at)}</span></div><dl className={styles.metricGrid}><div className={styles.metric}><dt>Strategy return</dt><dd>{percentage(numberValue(performance, "strategy_total_return"))}</dd></div><div className={styles.metric}><dt>Benchmark return</dt><dd>{percentage(numberValue(performance, "benchmark_total_return"))}</dd></div><div className={styles.metric}><dt>Realized P&amp;L</dt><dd>{formatValue(performance.realized_pnl)}</dd></div><div className={styles.metric}><dt>Max drawdown</dt><dd>{percentage(numberValue(performance, "strategy_max_drawdown"))}</dd></div><div className={styles.metric}><dt>Sharpe</dt><dd>{formatValue(performance.strategy_sharpe)}</dd></div><div className={styles.metric}><dt>Trade count</dt><dd>{formatValue(performance.strategy_trade_count)}</dd></div><div className={styles.metric}><dt>Hit rate</dt><dd>{percentage(numberValue(performance, "strategy_hit_rate"))}</dd></div><div className={styles.metric}><dt>Total fees</dt><dd>{formatValue(performance.total_fees)}</dd></div></dl></section>}{(detail.assumptions || detail.exposure) && <section className={styles.panel} aria-labelledby="context-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>EXECUTION CONTEXT</p><h2 id="context-heading">Assumptions and exposure</h2></div></div><dl className={styles.definitionGrid}>{detail.assumptions && <><div><dt>Fill model</dt><dd>{formatValue(detail.assumptions.fill_model)}</dd></div><div><dt>Latency</dt><dd>{formatValue(detail.assumptions.latency_ms)}</dd></div><div><dt>Fee model</dt><dd>{formatValue(detail.assumptions.fee_bps)} bps + {formatValue(detail.assumptions.fee_fixed_per_order)}</dd></div><div><dt>Slippage</dt><dd>{formatValue(detail.assumptions.slippage_bps)} bps</dd></div></>}{detail.exposure && <><div><dt>Average net exposure</dt><dd>{formatValue(detail.exposure.avg_net_exposure)}</dd></div><div><dt>Average invested</dt><dd>{percentage(numberValue(detail.exposure, "avg_invested_pct"))}</dd></div><div><dt>Final gross notional</dt><dd>{formatValue(detail.exposure.final_gross_notional)}</dd></div><div><dt>Position count</dt><dd>{formatValue(detail.exposure.position_count)}</dd></div></>}</dl></section>}<RiskControls detail={detail} />{scope && performance && <section className={styles.panel} aria-labelledby="curves-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>CURVES</p><h2 id="curves-heading">Strategy and benchmark</h2></div><span className={styles.resultCount}>{detail.equity_curve.length} points</span></div><LineChart points={detail.equity_curve} /><div style={{ marginTop: "22px" }}><p className={styles.eyebrow}>DRAWDOWN</p><LineChart points={detail.comparison_curves} drawdown /></div></section>}{detail && <section className={styles.panel} aria-labelledby="evidence-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>EVIDENCE</p><h2 id="evidence-heading">Execution and publication state</h2></div><span className={styles.resultCount}>{detail.signal_markers.length} signal markers · {detail.indicator_series.length} indicator points</span></div><div className={styles.tabs}>{(["trades", "positions", "lifecycle", "evidence"] as Section[]).map((item) => <button className={`${styles.tab} ${section === item ? styles.tabActive : ""}`} type="button" onClick={() => setSection(item)} aria-pressed={section === item} key={item}>{item === "trades" ? `Trades (${detail.trades.length})` : item === "positions" ? `Positions (${detail.positions.length})` : item === "lifecycle" ? "Lifecycle events" : "Coverage and lineage"}</button>)}</div><EvidenceTable detail={detail} section={section} />{detail.provenance.length > 0 && <div style={{ marginTop: "18px" }}><p className={styles.eyebrow}>PROVENANCE</p><DataTable caption="Run provenance" rows={detail.provenance} columns={[["provenance_key", "Key"], ["provenance_value", "Value"], ["observed_at", "Observed"]]} /></div>}</section>}</>}{state === "loading" && !detail && <div className={styles.loading} role="status">Loading published run evidence…</div>}{state === "ready" && !detail && <div className={styles.empty}>Select a published run to review.</div>}
      <p className={styles.statusLine} role="status" aria-live="polite">{state === "loading" ? "Loading backtest evidence…" : state === "error" ? "Backtest review needs attention. Retry the failed request." : detail ? `Showing the available evidence for ${detail.run.run_id}.` : "Choose an experiment and run to begin."}</p>
    </main><footer className={styles.footer}>Trader Console<span>Single-backtest review</span></footer>
  </div></ConsoleShell>;
}
