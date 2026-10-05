"use client";

import Link from "next/link";
import { useState } from "react";
import { ConsoleShell } from "../../features/shell/console-shell";
import styles from "../../features/agent-sessions/agent-session-workspace.module.css";

export default function AgentSessionsPage() {
  const [sessionId, setSessionId] = useState("");
  return <ConsoleShell><main className={styles.main}><header className={styles.heading}><div><p className={styles.eyebrow}>AGENT SESSIONS</p><h1>Open a research workspace</h1><p className={styles.subtitle}>Enter an exact session identity to inspect its redacted public evidence.</p></div></header><section className={styles.card}><label className={styles.label} htmlFor="agent-session-id">Session ID<input className={styles.input} id="agent-session-id" value={sessionId} onChange={(event) => setSessionId(event.target.value)} placeholder="session-id" /></label><div className={styles.controls}><Link className={styles.button} href={sessionId.trim() ? `/agents/${encodeURIComponent(sessionId.trim())}` : "/agents"}>Open workspace</Link></div></section></main></ConsoleShell>;
}
