"use client";

import { useCallback, useEffect, useState } from "react";
import { loadPaperRuntime, type PaperRuntimeOperations } from "./client";
import { ConsoleShell } from "../shell/console-shell";
import styles from "./paper-operations-workspace.module.css";

function format(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function Evidence({ status, reason }: { status: string; reason?: string | null }) {
  return <span className={`${styles.badge} ${styles[status] ?? ""}`} title={reason ?? undefined}>{status.replaceAll("_", " ")}</span>;
}

export function PaperOperationsWorkspace() {
  const [runtime, setRuntime] = useState<PaperRuntimeOperations | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void loadPaperRuntime(controller.signal).then(setRuntime).catch((cause: unknown) => {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof Error ? cause.message : "Paper runtime evidence could not be loaded.");
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  return (
    <ConsoleShell>
      <main className={styles.main}>
        <header className={styles.heading}>
          <div><p className={styles.eyebrow}>PAPER OPERATIONS</p><h1>Runtime evidence</h1><p className={styles.subtitle}>Read-only operational state with source timestamps and explicit evidence limits.</p></div>
          <button className={styles.button} type="button" onClick={refresh} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
        </header>
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!runtime && loading && <p role="status">Loading paper runtime evidence…</p>}
        {runtime && <>
          <section className={styles.banner} aria-label="Runtime health"><div><span className={styles.eyebrow}>HEALTH</span><strong>{runtime.health.status}</strong><p>{runtime.health.reasons.join(" · ") || "No active health warnings."}</p></div><Evidence status={runtime.health.evidence.status} reason={runtime.health.evidence.reason} /></section>
          <div className={styles.grid}>
            <section className={styles.card}><h2>Session</h2><Evidence status={runtime.session.evidence.status} reason={runtime.session.evidence.reason} /><dl><dt>Session</dt><dd>{runtime.session.session_id ?? "No session"}</dd><dt>Status</dt><dd>{runtime.session.status ?? "—"}</dd><dt>Strategy</dt><dd>{runtime.session.strategy_id ?? "—"}</dd><dt>Started</dt><dd>{format(runtime.session.started_at)}</dd></dl></section>
            <section className={styles.card}><h2>Account</h2><Evidence status={runtime.broker_account_binding} /><dl><dt>Configured label</dt><dd>{runtime.broker_account_display_label ?? "—"}</dd><dt>Broker identity</dt><dd>{runtime.broker_identity_verified ? "Verified" : "Not verified"}</dd><dt>Generated</dt><dd>{format(runtime.generated_at)}</dd></dl></section>
            <section className={styles.card}><h2>Data freshness</h2><Evidence status={runtime.data_freshness.evidence.status} reason={runtime.data_freshness.evidence.reason} /><p>{runtime.data_freshness.items.length} streams · {runtime.data_freshness.stale_count} stale · {runtime.data_freshness.missing_count} missing</p>{runtime.data_freshness.items.slice(0, 8).map((item) => <p key={`${item.asset_class}-${item.symbol}-${item.timeframe}`}>{item.symbol} · {item.timeframe} <Evidence status={item.stale ? "stale" : "available"} /> <small>{format(item.latest_ts)}</small></p>)}</section>
            <section className={styles.card}><h2>Portfolio</h2><Evidence status={runtime.portfolio.evidence.status} reason={runtime.portfolio.evidence.reason} /><p>Cash: {runtime.portfolio.cash ?? "—"}</p><p>{runtime.portfolio.positions.length} positions · as of {format(runtime.portfolio.asof_ts)}</p></section>
            <section className={styles.card}><h2>Orders & fills</h2><Evidence status={runtime.open_orders.evidence.status} reason={runtime.open_orders.evidence.reason} /><p>{runtime.open_orders.items.length} open orders · {runtime.open_orders.stale_count} stale</p><p>{runtime.fills.items.length} recent fills</p><Evidence status={runtime.fills.evidence.status} reason={runtime.fills.evidence.reason} /></section>
            <section className={styles.card}><h2>Risk outcomes</h2><Evidence status={runtime.risk.evidence.status} reason={runtime.risk.evidence.reason} /><p>{runtime.risk.evaluated_count} evaluated · {runtime.risk.approved_count} approved · {runtime.risk.rejected_count} rejected · {runtime.risk.blocked_count} blocked</p></section>
            <section className={styles.card}><h2>Reconciliation & halt</h2><Evidence status={runtime.reconciliation.evidence.status} reason={runtime.reconciliation.evidence.reason} /><p>{runtime.reconciliation.message}</p><Evidence status={runtime.halt.evidence.status} reason={runtime.halt.evidence.reason} /></section>
          </div>
          {runtime.incidents.length > 0 && <section className={styles.incidents}><h2>Incidents</h2>{runtime.incidents.map((incident) => <p key={`${incident.code}-${incident.observed_at}`}><strong>{incident.severity}</strong> {incident.message}</p>)}</section>}
        </>}
      </main>
    </ConsoleShell>
  );
}
