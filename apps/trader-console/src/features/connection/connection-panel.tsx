"use client";

import { useEffect, useRef, useState } from "react";
import { loadContext, loadLiveness, loadReadiness } from "./client";
import styles from "./connection-panel.module.css";
import { ConsoleShell } from "../shell/console-shell";

type Check<T> = { value?: T; pending: boolean; failed: boolean };
type Result<F extends (...args: never[]) => unknown> = Awaited<ReturnType<F>>;
const initial = { pending: true, failed: false };

const explanations: Record<string, string> = {
  database_unavailable: "The API cannot reach the database. Check that PostgreSQL is running, then retry.",
  schema_metadata_missing: "The database is missing its Console schema metadata. Run the demo bootstrap or restore step.",
  schema_metadata_invalid: "The database schema metadata is invalid. Restore the supported Console schema.",
  database_schema_too_old: "The database schema needs to be updated before Console can use it.",
  consumer_schema_too_old: "This API does not support the installed database schema.",
};

function explainIssue(issue: string) {
  if (Object.hasOwn(explanations, issue)) return explanations[issue];
  if (issue.startsWith("schema_catalog_mismatch:")) {
    return `The database relation does not match the supported schema: ${issue.slice("schema_catalog_mismatch:".length)}`;
  }
  return `Schema check reported: ${issue}`;
}

function useConnection() {
  const [context, setContext] = useState<Check<Result<typeof loadContext>>>(initial);
  const [live, setLive] = useState<Check<Result<typeof loadLiveness>>>(initial);
  const [ready, setReady] = useState<Check<Result<typeof loadReadiness>>>(initial);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 10_000);
    async function check<T>(loader: (signal: AbortSignal) => Promise<T>, update: React.Dispatch<React.SetStateAction<Check<T>>>) {
      update(previous => ({ ...previous, pending: true, failed: false }));
      try {
        const value = await loader(controller.signal);
        if (active && generation.current === current) update({ value, pending: false, failed: false });
      } catch {
        if (active && generation.current === current) update(previous => ({ ...previous, pending: false, failed: true }));
      }
    }
    void Promise.all([check(loadContext, setContext), check(loadLiveness, setLive), check(loadReadiness, setReady)])
      .finally(() => clearTimeout(timer));
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [revision]);

  return { context, live, ready, refresh: () => setRevision(value => value + 1) };
}

function Badge({ state, children }: { state: "good" | "bad" | "waiting"; children: React.ReactNode }) {
  return <span className={`${styles.badge} ${styles[state]}`}><span aria-hidden="true">{state === "good" ? "✓" : state === "bad" ? "!" : "·"}</span><span>{children}</span></span>;
}

export function ConnectionPanel() {
  const { context, live, ready, refresh } = useConnection();
  const scope = context.value;
  const pending = context.pending || live.pending || ready.pending;
  const databaseFailed = ready.failed || ready.value?.status === "unavailable";
  const failed = context.failed || live.failed || databaseFailed;
  const environment = scope?.environment === "synthetic_demo" ? "Synthetic demo" : scope?.environment === "paper" ? "Paper" : scope?.environment === "backtest" ? "Backtest" : "Unknown environment";
  const account = !scope ? "Unavailable" : scope.broker_account_binding === "not_applicable" ? "Not applicable" : scope.broker_account_display_label || "Not specified";

  return <ConsoleShell><div className={styles.shell}>
    <main className={styles.main}>
      <div className={styles.heading}><div><p className={styles.eyebrow}>WORKSPACE OVERVIEW</p><h1>Connection</h1><p className={styles.subtitle}>Know which environment you’re looking at.</p></div>
        <button className={styles.button} onClick={refresh} disabled={pending}>{pending ? "Checking…" : failed ? "Retry" : "Refresh"}<span aria-hidden="true">↻</span></button>
      </div>
      <section className={styles.context} aria-label="Configured context">
        <div className={styles.contextTitle}><h2>{scope?.display_name ?? (context.pending ? "Loading context…" : "Context unavailable")}</h2><span className={styles.environment}>{environment}</span></div>
        {scope?.environment === "synthetic_demo" && <p className={styles.demoNote}>Synthetic environment · no brokerage account or trading activity.</p>}
        <dl className={styles.details}><div><dt>Scope</dt><dd>{scope?.scope_id ?? "Unavailable"}</dd></div><div><dt>Brokerage account</dt><dd>{account}</dd></div><div><dt>Source</dt><dd>{scope ? "PostgreSQL" : "Unavailable"}</dd></div></dl>
        {context.failed && <p className={styles.warning}>{scope ? "Showing last known configured context. It could not be refreshed." : "Configured context could not be loaded. Check the API and retry."}</p>}
      </section>
      <section className={styles.panel} aria-labelledby="status-heading">
        <div className={styles.panelHeading}><h2 id="status-heading">Connection status</h2><span className={styles.manual}>Checked on request</span></div>
        <div className={styles.statusRow}><div><h3>Console API</h3><p>Availability of the application endpoint.</p></div><Badge state={live.pending ? "waiting" : live.failed ? "bad" : "good"}>{live.pending ? "Checking" : live.failed ? "Unavailable" : "Available"}</Badge></div>
        <div className={styles.statusRow}><div><h3>Database schema</h3><p>PostgreSQL connectivity and compatibility with this API.</p></div><Badge state={ready.pending ? "waiting" : databaseFailed ? "bad" : "good"}>{ready.pending ? "Checking" : databaseFailed ? "Unavailable" : "Compatible"}</Badge></div>
        {!ready.pending && ready.value?.status === "unavailable" && !ready.failed && <ul className={styles.issues}>{ready.value.issues?.map(issue => <li key={issue}>{explainIssue(issue)}</li>)}</ul>}
        {ready.failed && <p className={styles.issueMessage}>Database status could not be checked. Check the API and retry.</p>}
        {live.failed && <p className={styles.issueMessage}>The API is unavailable or did not return a valid response. Check that it has started successfully.</p>}
        <p className={styles.disclaimer}>Connection checks do not verify broker connectivity, account identity or trading health.</p>
      </section>
      <p role="status" aria-live="polite" className={styles.summary}>{pending ? "Checking connections…" : failed ? "Some checks need attention. Retry when the connection is restored." : "Connection checks complete."}</p>
    </main>
    <footer className={styles.footer}>Trader Console<span>Environment & connection</span></footer>
  </div></ConsoleShell>;
}
