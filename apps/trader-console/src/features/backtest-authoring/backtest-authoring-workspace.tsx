"use client";

import { useEffect, useMemo, useState } from "react";
import type { components } from "../../generated/api";
import { ConsoleShell } from "../shell/console-shell";
import {
  createDefinition,
  loadCatalogue,
  loadExecution,
  preflight,
  submitExecution,
  type Catalogue,
  type CatalogueProfile,
  type DefinitionRevision,
  type ExecutionRecord,
  type PreflightRequest,
  type PreflightResponse,
} from "./client";
import styles from "./backtest-authoring-workspace.module.css";

type PageState = "loading" | "ready" | "error";
type Assumptions = components["schemas"]["BacktestAssumptions"];
type ResourceLimits = components["schemas"]["BacktestResourceLimits"];

type Draft = {
  display_name: string;
  strategy_profile_id: string;
  strategy_catalogue_version: string;
  strategy_parameters: Record<string, unknown>;
  risk_profile_id: string;
  risk_catalogue_version: string;
  risk_parameters: Record<string, unknown>;
  asset_class: "stock" | "crypto";
  symbols: string;
  timeframe: string;
  start: string;
  end: string;
  initial_cash: number;
  initial_positions_json: string;
  assumptions: Assumptions;
  resource_limits: ResourceLimits;
  benchmark_id: "buy_hold" | "none";
};

const TERMINAL_STATUSES = new Set<ExecutionRecord["status"]>(["completed", "partial", "failed", "reconciliation_required"]);

function parameterDefaults(profile: CatalogueProfile): Record<string, unknown> {
  return Object.fromEntries(profile.parameters.flatMap((parameter) => parameter.default === undefined || parameter.default === null ? [] : [[parameter.name, parameter.default]]));
}

function initialDraft(catalogue: Catalogue): Draft {
  const strategy = catalogue.strategy_profiles[0];
  const risk = catalogue.risk_profiles[0];
  return {
    display_name: "Local backtest",
    strategy_profile_id: strategy?.profile_id ?? "",
    strategy_catalogue_version: strategy?.version ?? catalogue.catalogue_version,
    strategy_parameters: strategy ? parameterDefaults(strategy) : {},
    risk_profile_id: risk?.profile_id ?? "",
    risk_catalogue_version: risk?.version ?? catalogue.catalogue_version,
    risk_parameters: risk ? parameterDefaults(risk) : {},
    asset_class: "crypto",
    symbols: "BTC/USD",
    timeframe: "1Min",
    start: "2026-06-21T00:00",
    end: "2026-06-21T00:30",
    initial_cash: 100_000,
    initial_positions_json: "[]",
    assumptions: {
      fill_model: "full_fill",
      latency_ms: 0,
      fee_fixed_per_order: 0,
      fee_bps: 0,
      fee_minimum: 0,
      slippage_bps: 0,
      allow_latest_prior_bar: true,
      allow_price_carry_forward: true,
    },
    resource_limits: { max_cycles: 1_000_000, max_bars: 5_000_000, timeout_seconds: 3_600 },
    benchmark_id: "buy_hold",
  };
}

function asUtc(value: string): string {
  if (!value) return "";
  const parsed = new Date(value.endsWith("Z") ? value : `${value}Z`);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString();
}

function buildRequest(draft: Draft): PreflightRequest {
  let initialPositions: unknown;
  try {
    initialPositions = JSON.parse(draft.initial_positions_json || "[]");
  } catch {
    throw new Error("Initial positions must be valid JSON.");
  }
  if (!Array.isArray(initialPositions)) throw new Error("Initial positions must be a JSON array.");
  return {
    display_name: draft.display_name,
    strategy_profile_id: draft.strategy_profile_id,
    strategy_catalogue_version: draft.strategy_catalogue_version,
    strategy_parameters: draft.strategy_parameters,
    risk_profile_id: draft.risk_profile_id,
    risk_catalogue_version: draft.risk_catalogue_version,
    risk_parameters: draft.risk_parameters,
    asset_class: draft.asset_class,
    symbols: draft.symbols.split(",").map((symbol) => symbol.trim()).filter(Boolean),
    timeframe: draft.timeframe,
    start: asUtc(draft.start),
    end: asUtc(draft.end),
    initial_cash: draft.initial_cash,
    initial_positions: initialPositions as PreflightRequest["initial_positions"],
    assumptions: draft.assumptions,
    resource_limits: draft.resource_limits,
    benchmark_id: draft.benchmark_id,
  };
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value) ?? "Not recorded";
  } catch {
    return String(value);
  }
}

function statusLabel(status: ExecutionRecord["status"]): string {
  return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ParameterEditor({ profile, values, onChange }: { profile: CatalogueProfile | undefined; values: Record<string, unknown>; onChange: (name: string, value: unknown) => void }) {
  if (!profile || profile.parameters.length === 0) return <p className={styles.muted}>This profile has no configurable parameters.</p>;
  return <div className={styles.parameterGrid}>{profile.parameters.map((parameter) => {
    const value = values[parameter.name] ?? parameter.default ?? (parameter.type === "boolean" ? false : "");
    const id = `${profile.kind}-${parameter.name}`;
    return <label className={styles.parameter} key={parameter.name} htmlFor={id}>
      <span className={styles.parameterLabel}>{parameter.name}</span>
      {parameter.type === "boolean"
        ? <input id={id} type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(parameter.name, event.target.checked)} />
        : <input id={id} aria-label={parameter.name} type={parameter.type === "string" ? "text" : "number"} value={String(value)} min={parameter.minimum ?? undefined} max={parameter.maximum ?? undefined} step={parameter.type === "integer" ? 1 : "any"} onChange={(event) => onChange(parameter.name, event.target.value === "" ? "" : parameter.type === "integer" ? Number.parseInt(event.target.value, 10) : parameter.type === "number" ? Number.parseFloat(event.target.value) : event.target.value)} />}
      {parameter.description && <small>{parameter.description}</small>}
      <small>{parameter.required ? "Required" : "Optional"}{parameter.minimum !== null && parameter.minimum !== undefined ? ` · min ${parameter.minimum}` : ""}{parameter.maximum !== null && parameter.maximum !== undefined ? ` · max ${parameter.maximum}` : ""}</small>
    </label>;
  })}</div>;
}

function ProfileSummary({ profile }: { profile: CatalogueProfile | undefined }) {
  if (!profile) return null;
  return <div className={styles.profileSummary}><strong>{profile.name}</strong><span>{profile.description}</span><small>Version {profile.version} · lookback {profile.lookback_bars} bars</small>{profile.manager_ids.length > 0 && <small>Managers: {profile.manager_ids.join(", ")}</small>}</div>;
}

function IssueList({ response }: { response: PreflightResponse }) {
  if (response.issues.length === 0) return <p className={styles.success} role="status">Preflight passed. The definition is ready to save.</p>;
  return <div className={styles.issueList} role="status">{response.issues.map((issue, index) => <div className={issue.severity === "error" ? styles.issueError : styles.issueWarning} key={`${issue.path}-${index}`}><strong>{issue.severity === "error" ? "Error" : "Warning"}: {issue.path}</strong><span>{issue.message}</span></div>)}</div>;
}

function ExecutionStatus({ execution, polling, onRefresh, onStop, onResume }: { execution: ExecutionRecord; polling: boolean; onRefresh: () => void; onStop: () => void; onResume: () => void }) {
  const [observedAt] = useState(() => Date.now());
  const progress = execution.total_cycles === null || execution.total_cycles === undefined ? `${execution.processed_cycles} cycles processed` : `${execution.processed_cycles.toLocaleString()} / ${execution.total_cycles.toLocaleString()} cycles`;
  const heartbeatAge = execution.heartbeat_at ? `${Math.max(0, Math.round((observedAt - new Date(execution.heartbeat_at).valueOf()) / 1000))}s ago` : "Not recorded";
  const reviewHref = execution.run_id ? `/backtests?run_id=${encodeURIComponent(execution.run_id)}` : null;
  return <section className={styles.panel} aria-labelledby="execution-heading">
    <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>EXECUTION</p><h2 id="execution-heading">{statusLabel(execution.status)}</h2></div><span className={styles.statusBadge}>{execution.execution_id}</span></div>
    <dl className={styles.metricGrid}><div><dt>Progress</dt><dd>{progress}</dd></div><div><dt>Heartbeat</dt><dd>{heartbeatAge}</dd></div><div><dt>Last decision</dt><dd>{formatTimestamp(execution.last_decision_at)}</dd></div><div><dt>Attempt</dt><dd>{execution.attempt}</dd></div></dl>
    <div className={styles.contextLine}><span>Definition {execution.definition_fingerprint}</span><span>Created {formatTimestamp(execution.created_at)}</span><span>Worker {execution.worker_id ?? "Not claimed"}</span></div>
    {execution.warning_summary.length > 0 && <div className={styles.issueWarning}><strong>Warnings</strong><ul>{execution.warning_summary.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
    {execution.terminal_error_message && <div className={styles.issueError} role="alert"><strong>{execution.terminal_error_code ?? "Execution error"}</strong><span>{execution.terminal_error_message}</span></div>}
    <div className={styles.actions}><button className={styles.secondaryButton} type="button" onClick={onRefresh}>Refresh status</button>{!TERMINAL_STATUSES.has(execution.status) && (polling ? <button className={styles.secondaryButton} type="button" onClick={onStop}>Stop polling</button> : <button className={styles.secondaryButton} type="button" onClick={onResume}>Resume polling</button>)}{reviewHref && <a className={styles.button} href={reviewHref}>Open run review</a>}</div>
    {!TERMINAL_STATUSES.has(execution.status) && <p className={styles.muted} role="status">{polling ? "Polling every 2 seconds. No ETA is inferred." : "Polling is paused. Refresh manually or resume polling."}</p>}
  </section>;
}

export function BacktestAuthoringWorkspace() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [catalogueAttempt, setCatalogueAttempt] = useState(0);
  const [state, setState] = useState<PageState>("loading");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null);
  const [definition, setDefinition] = useState<DefinitionRevision | null>(null);
  const [execution, setExecution] = useState<ExecutionRecord | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(() => typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("execution_id"));
  const [polling, setPolling] = useState(() => typeof window !== "undefined" && Boolean(new URLSearchParams(window.location.search).get("execution_id")));

  const strategy = useMemo(() => catalogue?.strategy_profiles.find((profile) => profile.profile_id === draft?.strategy_profile_id), [catalogue, draft?.strategy_profile_id]);
  const risk = useMemo(() => catalogue?.risk_profiles.find((profile) => profile.profile_id === draft?.risk_profile_id), [catalogue, draft?.risk_profile_id]);

  useEffect(() => {
    const controller = new AbortController();
    void loadCatalogue(controller.signal).then((response) => {
      setCatalogue(response);
      setDraft(initialDraft(response));
      setState("ready");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) { setState("error"); setError(reason instanceof Error ? reason.message : "Backtest catalogue could not be loaded."); }
    });
    return () => controller.abort();
  }, [catalogueAttempt]);

  useEffect(() => {
    if (!executionId || !polling) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await loadExecution(controller.signal, executionId);
        setExecution(response);
        if (!TERMINAL_STATUSES.has(response.status) && !controller.signal.aborted) timer = window.setTimeout(() => { void poll(); }, 2_000);
        else if (TERMINAL_STATUSES.has(response.status)) setPolling(false);
      } catch (reason: unknown) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Execution status could not be loaded.");
      }
    };
    void poll();
    return () => { controller.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [executionId, polling]);

  const updateDraft = (update: Partial<Draft>) => { setDraft((current) => current ? { ...current, ...update } : current); setPreflightResult(null); setDefinition(null); setMessage(""); };
  const changeProfile = (kind: "strategy" | "risk", profileId: string) => {
    const profile = (kind === "strategy" ? catalogue?.strategy_profiles : catalogue?.risk_profiles)?.find((item) => item.profile_id === profileId);
    if (!profile) return;
    updateDraft(kind === "strategy" ? { strategy_profile_id: profile.profile_id, strategy_catalogue_version: profile.version, strategy_parameters: parameterDefaults(profile) } : { risk_profile_id: profile.profile_id, risk_catalogue_version: profile.version, risk_parameters: parameterDefaults(profile) });
  };
  const runPreflight = async () => {
    if (!draft) return;
    setBusy("Running preflight…"); setError(""); setMessage("");
    try { const response = await preflight(new AbortController().signal, buildRequest(draft)); setPreflightResult(response); setMessage(response.valid ? "Preflight passed. Save the immutable definition to submit it." : "Preflight found issues. Fix them before saving."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Preflight could not be completed."); }
    finally { setBusy(""); }
  };
  const save = async () => {
    if (!draft || !preflightResult?.valid) return;
    setBusy("Saving immutable definition…"); setError("");
    try { const response = await createDefinition(new AbortController().signal, buildRequest(draft)); setDefinition(response); setMessage(`Saved revision ${response.revision} with fingerprint ${response.fingerprint}.`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Definition could not be saved."); }
    finally { setBusy(""); }
  };
  const submit = async () => {
    if (!definition) return;
    setBusy("Submitting execution…"); setError("");
    try {
      const idempotencyKey = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const response = await submitExecution(new AbortController().signal, definition.definition_id, idempotencyKey);
      setExecution(response); setExecutionId(response.execution_id); setPolling(true); setMessage(`Execution ${response.execution_id} queued.`);
      if (typeof window !== "undefined") window.history.replaceState(null, "", `/backtests/new?execution_id=${encodeURIComponent(response.execution_id)}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Execution could not be submitted."); }
    finally { setBusy(""); }
  };
  const refreshExecution = async () => {
    if (!executionId) return;
    setBusy("Refreshing execution status…"); setError("");
    try { setExecution(await loadExecution(new AbortController().signal, executionId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Execution status could not be loaded."); }
    finally { setBusy(""); }
  };

  if (state === "loading") return <ConsoleShell><main className={styles.main}><p className={styles.loading} role="status">Loading backtest catalogue…</p></main></ConsoleShell>;
  if (state === "error" || !catalogue || !draft) return <ConsoleShell><main className={styles.main}><div className={styles.issueError} role="alert"><strong>Authoring unavailable</strong><span>{error || "Backtest catalogue could not be loaded."}</span><button className={styles.secondaryButton} type="button" onClick={() => { setError(""); setState("loading"); setCatalogueAttempt((attempt) => attempt + 1); }}>Retry</button></div></main></ConsoleShell>;

  return <ConsoleShell><div className={styles.shell}><main className={styles.main}>
    <div className={styles.heading}><div><p className={styles.eyebrow}>BACKTEST AUTHORING</p><h1>Define and run a local backtest</h1><p className={styles.subtitle}>Choose maintained strategy and risk profiles, validate the full replay scope, save an immutable definition, and observe its durable execution state.</p></div><a className={styles.secondaryButton} href="/backtests">Review published runs</a></div>
    {error && <div className={styles.issueError} role="alert"><strong>Request failed</strong><span>{error}</span></div>}
    <section className={styles.panel} aria-labelledby="definition-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>DEFINITION</p><h2 id="definition-heading">Replay scope</h2></div><span className={styles.statusBadge}>Catalogue {catalogue.catalogue_version}</span></div>
      <div className={styles.formGrid}><label>Display name<input aria-label="Display name" value={draft.display_name} onChange={(event) => updateDraft({ display_name: event.target.value })} /></label><label>Symbols<input aria-label="Symbols" value={draft.symbols} onChange={(event) => updateDraft({ symbols: event.target.value })} /><small>Comma-separated symbols, normalized by preflight.</small></label><label>Asset class<select aria-label="Asset class" value={draft.asset_class} onChange={(event) => updateDraft({ asset_class: event.target.value as Draft["asset_class"] })}><option value="crypto">Crypto</option><option value="stock">Stock</option></select></label><label>Timeframe<select aria-label="Timeframe" value={draft.timeframe} onChange={(event) => updateDraft({ timeframe: event.target.value })}><option value="1Min">1Min</option><option value="1Hour">1Hour</option><option value="1Day">1Day</option></select></label><label>Start (UTC)<input aria-label="Start UTC" type="datetime-local" value={draft.start} onChange={(event) => updateDraft({ start: event.target.value })} /></label><label>End (UTC)<input aria-label="End UTC" type="datetime-local" value={draft.end} onChange={(event) => updateDraft({ end: event.target.value })} /></label><label>Initial cash<input aria-label="Initial cash" type="number" min="0" step="any" value={draft.initial_cash} onChange={(event) => updateDraft({ initial_cash: Number(event.target.value) })} /></label><label>Benchmark<select aria-label="Benchmark" value={draft.benchmark_id} onChange={(event) => updateDraft({ benchmark_id: event.target.value as Draft["benchmark_id"] })}><option value="buy_hold">Buy and hold</option><option value="none">None</option></select></label></div>
      <label className={styles.fullField}>Initial positions (JSON)<textarea aria-label="Initial positions JSON" rows={2} value={draft.initial_positions_json} onChange={(event) => updateDraft({ initial_positions_json: event.target.value })} /><small>Use an array of symbol, qty and optional avg_price objects.</small></label>
    </section>
    <section className={styles.panel} aria-labelledby="profiles-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>ALLOWLISTED PROFILES</p><h2 id="profiles-heading">Strategy and risk composition</h2></div></div>
      <div className={styles.profileGrid}><fieldset><legend>Strategy</legend><select aria-label="Strategy profile" value={draft.strategy_profile_id} onChange={(event) => changeProfile("strategy", event.target.value)}>{catalogue.strategy_profiles.map((profile) => <option value={profile.profile_id} key={profile.profile_id}>{profile.name} · {profile.version}</option>)}</select><ProfileSummary profile={strategy} /><ParameterEditor profile={strategy} values={draft.strategy_parameters} onChange={(name, value) => updateDraft({ strategy_parameters: { ...draft.strategy_parameters, [name]: value } })} /></fieldset><fieldset><legend>Risk manager</legend><select aria-label="Risk profile" value={draft.risk_profile_id} onChange={(event) => changeProfile("risk", event.target.value)}>{catalogue.risk_profiles.map((profile) => <option value={profile.profile_id} key={profile.profile_id}>{profile.name} · {profile.version}</option>)}</select><ProfileSummary profile={risk} /><ParameterEditor profile={risk} values={draft.risk_parameters} onChange={(name, value) => updateDraft({ risk_parameters: { ...draft.risk_parameters, [name]: value } })} /></fieldset></div>
    </section>
    <section className={styles.panel} aria-labelledby="assumptions-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>EXECUTION BOUNDS</p><h2 id="assumptions-heading">Assumptions and resource limits</h2></div></div>
      <div className={styles.formGrid}><label>Fill model<select aria-label="Fill model" value={draft.assumptions.fill_model} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, fill_model: event.target.value as Assumptions["fill_model"] } })}><option value="full_fill">Full fill</option><option value="next_bar">Next bar</option></select></label><label>Latency (ms)<input aria-label="Latency milliseconds" type="number" min="0" value={draft.assumptions.latency_ms} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, latency_ms: Number(event.target.value) } })} /></label><label>Fee (bps)<input aria-label="Fee basis points" type="number" min="0" step="any" value={draft.assumptions.fee_bps} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, fee_bps: Number(event.target.value) } })} /></label><label>Slippage (bps)<input aria-label="Slippage basis points" type="number" min="0" step="any" value={draft.assumptions.slippage_bps} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, slippage_bps: Number(event.target.value) } })} /></label><label>Max cycles<input aria-label="Maximum cycles" type="number" min="1" value={draft.resource_limits.max_cycles} onChange={(event) => updateDraft({ resource_limits: { ...draft.resource_limits, max_cycles: Number(event.target.value) } })} /></label><label>Max bars<input aria-label="Maximum bars" type="number" min="1" value={draft.resource_limits.max_bars} onChange={(event) => updateDraft({ resource_limits: { ...draft.resource_limits, max_bars: Number(event.target.value) } })} /></label><label>Timeout (seconds)<input aria-label="Timeout seconds" type="number" min="1" value={draft.resource_limits.timeout_seconds} onChange={(event) => updateDraft({ resource_limits: { ...draft.resource_limits, timeout_seconds: Number(event.target.value) } })} /></label></div><label className={styles.checkbox}><input type="checkbox" checked={draft.assumptions.allow_latest_prior_bar} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, allow_latest_prior_bar: event.target.checked } })} /> Allow latest prior bar</label><label className={styles.checkbox}><input type="checkbox" checked={draft.assumptions.allow_price_carry_forward} onChange={(event) => updateDraft({ assumptions: { ...draft.assumptions, allow_price_carry_forward: event.target.checked } })} /> Allow price carry-forward</label>
    </section>
    <section className={styles.panel} aria-labelledby="preflight-heading"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>VALIDATE</p><h2 id="preflight-heading">Preflight and immutable save</h2></div><span className={styles.statusBadge}>{preflightResult?.definition_fingerprint ?? "No fingerprint yet"}</span></div><p className={styles.muted}>Preflight checks catalogue versions, normalized inputs, coverage, warmup and bounded resources before any definition or command write.</p><div className={styles.actions}><button className={styles.secondaryButton} type="button" onClick={() => void runPreflight()} disabled={Boolean(busy)}>{busy === "Running preflight…" ? busy : "Run preflight"}</button><button className={styles.button} type="button" onClick={() => void save()} disabled={Boolean(busy) || !preflightResult?.valid}>{definition ? `Saved revision ${definition.revision}` : "Save immutable definition"}</button><button className={styles.button} type="button" onClick={() => void submit()} disabled={Boolean(busy) || !definition || Boolean(execution)}>{busy === "Submitting execution…" ? busy : execution ? "Execution submitted" : "Submit execution"}</button></div>{preflightResult && <div className={styles.preflightResult}><IssueList response={preflightResult}/>{preflightResult.normalized_definition && <div className={styles.normalized}><h3>Normalized definition</h3><dl className={styles.normalizedGrid}><div><dt>Symbols</dt><dd>{preflightResult.normalized_definition.symbols.join(", ")}</dd></div><div><dt>Replay window</dt><dd>{formatTimestamp(preflightResult.normalized_definition.start)} → {formatTimestamp(preflightResult.normalized_definition.end)}</dd></div><div><dt>Strategy composition</dt><dd>{preflightResult.normalized_definition.strategy_profile_id} · {preflightResult.normalized_definition.strategy_catalogue_version}</dd></div><div><dt>Strategy parameters</dt><dd>{formatJson(preflightResult.normalized_definition.strategy_parameters)}</dd></div><div><dt>Risk composition</dt><dd>{preflightResult.normalized_definition.risk_profile_id} · {preflightResult.normalized_definition.risk_catalogue_version}</dd></div><div><dt>Risk parameters</dt><dd>{formatJson(preflightResult.normalized_definition.risk_parameters)}</dd></div></dl></div>}{preflightResult.coverage.length > 0 && <div className={styles.coverage}><h3>Coverage</h3>{preflightResult.coverage.map((item) => <div className={styles.coverageRow} key={`${item.symbol}-${item.timeframe}`}><span>{item.symbol} · {item.timeframe}</span><span>{item.available && item.warmup_satisfied ? "Ready" : "Insufficient"}</span><small>{item.bar_count.toLocaleString()} bars · required from {formatTimestamp(item.required_start)} to {formatTimestamp(item.requested_end)}</small></div>)}</div>}</div>}{message && <p className={styles.success} role="status">{message}</p>}</section>
    {execution && <ExecutionStatus execution={execution} polling={polling} onRefresh={() => void refreshExecution()} onStop={() => setPolling(false)} onResume={() => setPolling(true)} />}
  </main><footer className={styles.footer}><span>Console / local backtest scope</span><span>Durable command state</span></footer></div></ConsoleShell>;
}
