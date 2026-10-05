"use client";

import { useCallback, useEffect, useState } from "react";
import { ConsoleShell } from "../shell/console-shell";
import {
  loadAgentSession,
  submitAgentSessionCommand,
  type AgentSessionCommand,
  type AgentSessionCommandRecord,
  type AgentSessionProjection,
} from "./client";
import styles from "./agent-session-workspace.module.css";

function format(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toISOString().replace("T", " ").replace(".000Z", " UTC");
}

export function AgentSessionWorkspace({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<AgentSessionProjection | null>(null);
  const [command, setCommand] = useState<AgentSessionCommandRecord | null>(null);
  const [reason, setReason] = useState("");
  const [answer, setAnswer] = useState("");
  const [approved, setApproved] = useState(true);
  const [loading, setLoading] = useState(true);
  const [commandLoading, setCommandLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void loadAgentSession(sessionId, controller.signal)
      .then(setSession)
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof Error ? cause.message : "Agent session evidence could not be loaded.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [sessionId]);

  const issue = useCallback((requestedCommand: AgentSessionCommand) => {
    const controller = new AbortController();
    setCommandLoading(true);
    setError(null);
    void submitAgentSessionCommand(sessionId, requestedCommand, reason.trim(), answer.trim(), approved, controller.signal)
      .then(setCommand)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Agent session command could not be queued."))
      .finally(() => setCommandLoading(false));
  }, [answer, approved, reason, sessionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  return (
    <ConsoleShell>
      <main className={styles.main}>
        <header className={styles.heading}>
          <div><p className={styles.eyebrow}>AGENT SESSION</p><h1>Research workspace</h1><p className={styles.subtitle}>Inspect the bounded public trajectory and send human-owned lifecycle intents. Model prompts, completions, hidden reasoning, and raw tool payloads are never shown.</p></div>
          <button className={styles.button} type="button" onClick={refresh} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
        </header>
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!session && loading && <p role="status">Loading agent session evidence…</p>}
        {session && <>
          <section className={styles.card}>
            <span className={`${styles.status} ${styles[session.status] ?? ""}`}>{session.status.replaceAll("_", " ")}</span>
            <dl className={styles.facts}>
              <dt>Session</dt><dd>{session.session_id}</dd>
              <dt>Objective</dt><dd>{session.objective}</dd>
              <dt>Success definition</dt><dd>{session.success_definition}</dd>
              <dt>Model / catalogue</dt><dd>{session.model_profile_id} · {session.tool_catalog_id}</dd>
              <dt>Checkpoint</dt><dd>{session.checkpoint_sequence ?? "—"}</dd>
            </dl>
          </section>
          {session.pending_interrupt && <p className={styles.notice} role="status">Operator input requested: {session.pending_interrupt.question}</p>}
          <div className={styles.grid}>
            <section className={styles.card}><h2>Scope and budget</h2><dl className={styles.facts}><dt>Scope</dt><dd><pre>{JSON.stringify(session.scope_summary, null, 2)}</pre></dd><dt>Model calls</dt><dd>{session.budget_used.model_calls} / {session.budget_limits.max_model_calls}</dd><dt>Tool calls</dt><dd>{session.budget_used.tool_calls} / {session.budget_limits.max_tool_calls}</dd><dt>Tokens</dt><dd>{session.budget_used.tokens} / {session.budget_limits.max_tokens}</dd></dl></section>
            <section className={styles.card}><h2>Specialist progress</h2><ul className={styles.list}>{session.delegations.length === 0 && <li className={styles.item}><small>No specialist progress has been published.</small></li>}{session.delegations.map((item) => <li className={styles.item} key={`${item.branch_id}-${item.sequence}`}><strong>{item.role} · {item.status}</strong><small>{item.summary}</small></li>)}</ul></section>
            <section className={`${styles.card} ${styles.wide}`}><h2>Public trajectory</h2><ul className={styles.list}>{session.events.length === 0 && <li className={styles.item}><small>No public transitions have been published.</small></li>}{session.events.map((item) => <li className={styles.item} key={item.event_id}><strong>{item.event_type} · {item.status} · {item.branch_id}:{item.sequence}</strong><small>{item.summary} · {format(item.recorded_at)}</small></li>)}</ul></section>
            <section className={`${styles.card} ${styles.wide}`}><h2>Human controls</h2><p>Commands are durable intents consumed by the agent runtime. They do not grant the Console model or MCP authority.</p><label className={styles.label} htmlFor="agent-command-reason">Reason (optional)<input className={styles.input} id="agent-command-reason" value={reason} onChange={(event) => setReason(event.target.value)} /></label><label className={styles.label} htmlFor="agent-command-answer">Answer to pending interrupt (required for resume)<input className={styles.input} id="agent-command-answer" value={answer} onChange={(event) => setAnswer(event.target.value)} /></label><label className={styles.label} htmlFor="agent-command-approved">Resume decision<select className={styles.input} id="agent-command-approved" aria-label="Resume decision" value={approved ? "true" : "false"} onChange={(event) => setApproved(event.target.value === "true")}><option value="true">Approve and continue</option><option value="false">Decline and continue</option></select></label><div className={styles.controls}>{(["inspect", "interrupt", "resume", "cancel"] as AgentSessionCommand[]).map((requestedCommand) => <button className={styles.button} type="button" key={requestedCommand} disabled={commandLoading || (requestedCommand === "resume" && !answer.trim())} onClick={() => issue(requestedCommand)}>{requestedCommand === "interrupt" ? "Pause" : requestedCommand}</button>)}</div>{command && <p role="status">Command {command.command} is <strong>{command.status}</strong>.</p>}</section>
          </div>
        </>}
      </main>
    </ConsoleShell>
  );
}
