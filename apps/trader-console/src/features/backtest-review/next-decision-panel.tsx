"use client";

import { useEffect, useState } from "react";
import {
  createNextResearchDecision, loadDecisionBasis, loadNextResearchDecisions,
  type DecisionBasisResponse, type NextResearchDecisionRecord,
  type NextResearchDecisionRequest, type RunDetail,
} from "./client";
import styles from "./backtest-review-workspace.module.css";

type Outcome = NextResearchDecisionRequest["outcome"];

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "The next decision could not be loaded.";
}

export function NextDecisionPanel({ detail }: { detail: RunDetail }) {
  return <DecisionPanel key={detail.run.run_id} runId={detail.run.run_id} />;
}

function DecisionPanel({ runId }: { runId: string }) {
  const [decisions, setDecisions] = useState<NextResearchDecisionRecord[]>([]);
  const [basis, setBasis] = useState<DecisionBasisResponse | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [outcome, setOutcome] = useState<Outcome>("reject");
  const [rationale, setRationale] = useState("");
  const [limitations, setLimitations] = useState("");
  const [nextQuestion, setNextQuestion] = useState("");
  const [nextStart, setNextStart] = useState("");
  const [nextEnd, setNextEnd] = useState("");
  const [nextRuns, setNextRuns] = useState("3");
  const [nextCriteria, setNextCriteria] = useState("");
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "error">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const evidence = basis?.run_id === runId && basis.status === "available" ? basis.evidence : null;
  const permitted = basis?.permitted_outcomes ?? [];
  const successorValid = outcome === "reject" || Boolean(nextQuestion.trim() && nextStart && nextEnd > nextStart
    && Number.isInteger(Number(nextRuns)) && Number(nextRuns) >= 1 && Number(nextRuns) <= 100 && nextCriteria.trim());
  const canRecord = Boolean(evidence && permitted.includes(outcome) && loadState === "ready" && successorValid
    && rationale.trim() && limitations.trim() && submitState !== "submitting");

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
      setLoadState("error");
      setLoadError("Decision evidence timed out. Refresh persisted evidence.");
    }, 10000);
    void Promise.all([
      loadDecisionBasis(controller.signal, runId),
      loadNextResearchDecisions(controller.signal, runId),
    ]).then(([loaded, history]) => {
      if (controller.signal.aborted) return;
      if (loaded.run_id !== runId) throw new Error("Evidence belongs to a different run. Refresh the evidence.");
      setBasis(loaded);
      setDecisions(history.items);
      setLoadState("ready");
      setLoadError(null);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setBasis(null);
      setLoadState("error");
      setLoadError(errorMessage(reason));
    }).finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [runId, refresh]);

  function refreshEvidence() {
    setBasis(null);
    setLoadState("loading");
    setOutcome("reject");
    setSubmitError(null);
    setRefresh((value) => value + 1);
  }

  async function submit() {
    if (!canRecord || !evidence) return;
    const request: NextResearchDecisionRequest = {
      ...evidence, decision_id: crypto.randomUUID(), revision: 1,
      outcome, rationale: rationale.trim(),
      limitations: limitations.split("\n").map((item) => item.trim()).filter(Boolean),
      next_experiment: outcome === "reject" ? null : {
        question: nextQuestion.trim(), data_ref: evidence.data_ref,
        implementation_refs: evidence.implementation_refs, assumptions: evidence.assumptions ?? {},
        evaluation_start: `${nextStart}T00:00:00Z`, evaluation_end: `${nextEnd}T00:00:00Z`,
        max_runs: Number(nextRuns),
        success_criteria: nextCriteria.split("\n").map((item) => item.trim()).filter(Boolean),
      },
    };
    setSubmitState("submitting");
    setSubmitError(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const created = await createNextResearchDecision(controller.signal, runId, request);
      setDecisions((current) => [created, ...current]);
      setRationale("");
      setLimitations("");
      setSubmitState("idle");
    } catch (reason: unknown) {
      setBasis(null);
      setSubmitState("error");
      setSubmitError(`${errorMessage(reason)} Refresh persisted evidence and review the decision history before submitting again.`);
    } finally { clearTimeout(timer); }
  }

  return <section className={styles.panel} aria-labelledby="next-decision-heading">
    <div className={styles.sectionHeading}>
      <div><p className={styles.eyebrow}>HUMAN DECISION</p><h2 id="next-decision-heading">Choose what happens next</h2></div>
      <span className={styles.resultCount}>{decisions.length} decision{decisions.length === 1 ? "" : "s"}</span>
    </div>
    <p className={styles.muted}>Record a human decision against the exact persisted run and evidence shown here. A decision never approves deployment.</p>
    {loadState === "loading" && <p role="status">Loading persisted decision evidence…</p>}
    {loadError && <p role="alert">Decision evidence unavailable: {loadError}</p>}
    {basis && <p role="status">{basis.reason}</p>}
    {evidence && <article className={styles.reviewEvidenceCard}>
      <dl className={styles.reviewEvidenceMeta}>
        <div><dt>Source run</dt><dd>{evidence.source_run_ref.artifact_id}</dd></div>
        <div><dt>Qualified Data evidence</dt><dd>{evidence.data_ref.artifact_id}</dd></div>
        <div><dt>Implementation evidence</dt><dd>{evidence.implementation_refs.map((item) => item.artifact_id).join(", ")}</dd></div>
        <div><dt>Session</dt><dd>{evidence.blocked_evidence?.session_ref?.artifact_id ?? evidence.session_review?.session_id ?? "Unavailable — no canonical session link"}</dd></div>
        <div><dt>Graph digest</dt><dd>{evidence.session_review?.graph_digest ?? "Unavailable — no retained graph link"}</dd></div>
      </dl>
      {evidence.blocked_evidence && <>
        <p><strong>Independent scientific review: Not assessed</strong></p>
        <p>Blocked outcome: {evidence.blocked_evidence.outcome_ref.artifact_id}</p>
        <ul>{evidence.blocked_evidence.blockers.map((item, index) => <li key={`${item.code}-${index}`}>{item.code}: {item.message}</li>)}</ul>
      </>}
      <details><summary>Exact artifact hashes and revisions</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details>
      {basis?.limitations?.map((item) => <p key={item}>{item}</p>)}
    </article>}
    <button className={styles.buttonSecondary} type="button" onClick={refreshEvidence} disabled={submitState === "submitting"}>Refresh persisted evidence</button>
    {decisions.length > 0 && <div className={styles.reviewEvidenceGrid}>
      {decisions.map((decision) => <article className={styles.reviewEvidenceCard} key={decision.artifact_id}>
        <div className={styles.reviewEvidenceHeader}><h3>{decision.outcome}</h3><span className={styles.status}>Revision {decision.revision}</span></div>
        <p className={styles.reviewEvidenceReason}>{decision.rationale}</p>
        <dl className={styles.reviewEvidenceMeta}>
          <div><dt>Persisted receipt</dt><dd>{decision.artifact_id}</dd></div>
          <div><dt>Operator / time</dt><dd>{decision.operator} · {decision.decided_at}</dd></div>
          <div><dt>Run / data</dt><dd>{decision.source_run_ref.artifact_id} · {decision.data_ref.artifact_id}</dd></div>
          <div><dt>Limitations</dt><dd>{decision.limitations.join("; ")}</dd></div>
        </dl>
      </article>)}
    </div>}
    <div className={styles.selectorGrid}>
      <label className={styles.field}><span>Decision</span><select aria-label="Next decision outcome" value={outcome} onChange={(event) => setOutcome(event.target.value as Outcome)} disabled={!evidence}>
        {permitted.map((item) => <option key={item} value={item}>{item.charAt(0).toUpperCase() + item.slice(1)}</option>)}
      </select></label>
      <label className={styles.field}><span>Rationale</span><textarea aria-label="Decision rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} rows={3} /></label>
      <label className={styles.field}><span>Limitations (one per line)</span><textarea aria-label="Decision limitations" value={limitations} onChange={(event) => setLimitations(event.target.value)} rows={3} /></label>
    </div>
    {outcome !== "reject" && <div className={styles.selectorGrid}>
      <label className={styles.field}><span>Next experiment question</span><input aria-label="Next experiment question" value={nextQuestion} onChange={(event) => setNextQuestion(event.target.value)} /></label>
      <label className={styles.field}><span>Maximum runs</span><input aria-label="Next experiment maximum runs" type="number" min={1} max={100} value={nextRuns} onChange={(event) => setNextRuns(event.target.value)} /></label>
      <label className={styles.field}><span>Evaluation start</span><input aria-label="Next experiment evaluation start" type="date" value={nextStart} onChange={(event) => setNextStart(event.target.value)} /></label>
      <label className={styles.field}><span>Evaluation end</span><input aria-label="Next experiment evaluation end" type="date" value={nextEnd} onChange={(event) => setNextEnd(event.target.value)} /></label>
      <label className={styles.field}><span>Success criteria (one per line)</span><textarea aria-label="Next experiment success criteria" value={nextCriteria} onChange={(event) => setNextCriteria(event.target.value)} rows={3} /></label>
    </div>}
    {submitError && <div className={styles.errorBox} role="alert"><p>{submitError}</p></div>}
    <button className={styles.button} type="button" onClick={() => void submit()} disabled={!canRecord}>{submitState === "submitting" ? "Recording…" : "Record decision"}</button>
  </section>;
}
