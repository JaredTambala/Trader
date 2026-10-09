"use client";

import { useEffect, useMemo, useState } from "react";
import {
  createNextResearchDecision,
  loadNextResearchDecisions,
  type NextResearchDecisionRecord,
  type NextResearchDecisionRequest,
  type RunDetail,
} from "./client";
import styles from "./backtest-review-workspace.module.css";

type Outcome = NextResearchDecisionRequest["outcome"];

function ref(artifactId: string, artifactType: string, domainOwner: string, metadata: Record<string, unknown> = {}) {
  return {
    artifact_id: artifactId,
    artifact_type: artifactType,
    domain_owner: domainOwner,
    uri: `research://postgres/${artifactType}/${artifactId}`,
    metadata,
  };
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "The next decision could not be loaded.";
}

export function NextDecisionPanel({ detail }: { detail: RunDetail }) {
  const runId = detail.run.run_id;
  const [decisions, setDecisions] = useState<NextResearchDecisionRecord[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>("reject");
  const [rationale, setRationale] = useState("");
  const [limitations, setLimitations] = useState("");
  const [dataArtifactId, setDataArtifactId] = useState("");
  const [implementationArtifactId, setImplementationArtifactId] = useState("");
  const [nextQuestion, setNextQuestion] = useState("");
  const [nextStart, setNextStart] = useState("");
  const [nextEnd, setNextEnd] = useState("");
  const [nextRuns, setNextRuns] = useState("3");
  const [nextCriteria, setNextCriteria] = useState("");
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "error">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const availableReview = useMemo(
    () => detail.review_evidence.find((item) => item.status === "complete" && item.artifact_id),
    [detail.review_evidence],
  );
  const exactReview = availableReview?.session_id && availableReview.session_digest && availableReview.graph_digest
    && availableReview.revision && availableReview.node_key ? availableReview : undefined;
  const exactScope = typeof detail.scope?.scope_fingerprint === "string" ? detail.scope.scope_fingerprint : undefined;
  const canRecord = Boolean(exactScope && exactReview && dataArtifactId.trim() && implementationArtifactId.trim());

  useEffect(() => {
    const controller = new AbortController();
    void loadNextResearchDecisions(controller.signal, runId).then((response) => {
      setDecisions(response.items);
      setLoadState("ready");
      setLoadError(null);
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setLoadState("error");
      setLoadError(errorMessage(reason));
    });
    return () => controller.abort();
  }, [runId]);

  async function submit() {
    if (!canRecord || !rationale.trim() || !limitations.trim()) return;
    const dataRef = ref(dataArtifactId.trim(), "dataset_manifest", "Data", { scope_fingerprint: exactScope });
    const implementationRef = ref(implementationArtifactId.trim(), "implementation_version", "Experiments");
    const reviewRef = ref(availableReview?.artifact_id ?? "", availableReview?.artifact_type ?? "evaluation_report", "Review", {
      run_id: runId,
      scope_fingerprint: exactScope,
      session_id: exactReview?.session_id,
      session_digest: exactReview?.session_digest,
      graph_digest: exactReview?.graph_digest,
      revision: exactReview?.revision,
      node_key: exactReview?.node_key,
      source_hash: exactReview?.source_hash,
    });
    const sessionReview = exactReview ? {
      session_id: exactReview.session_id ?? "",
      session_digest: exactReview.session_digest ?? "",
      graph_digest: exactReview.graph_digest ?? "",
      review_node_keys: [exactReview.node_key ?? ""],
    } : null;
    const request: NextResearchDecisionRequest = {
      decision_id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `decision-${Date.now()}`,
      revision: 1,
      outcome,
      rationale: rationale.trim(),
      source_run_ref: ref(runId, "backtest_run", "Experiments", { run_id: runId, scope_fingerprint: exactScope }),
      data_ref: dataRef,
      implementation_refs: [implementationRef],
      assumptions: detail.assumptions ?? {},
      review_refs: [reviewRef],
      session_review: sessionReview,
      limitations: limitations.split("\n").map((item) => item.trim()).filter(Boolean),
      next_experiment: outcome === "reject" ? null : {
        question: nextQuestion.trim(),
        data_ref: dataRef,
        implementation_refs: [implementationRef],
        assumptions: detail.assumptions ?? {},
        evaluation_start: `${nextStart}T00:00:00Z`,
        evaluation_end: `${nextEnd}T00:00:00Z`,
        max_runs: Number(nextRuns),
        success_criteria: nextCriteria.split("\n").map((item) => item.trim()).filter(Boolean),
      },
    };
    setSubmitState("submitting");
    setSubmitError(null);
    try {
      const controller = new AbortController();
      const created = await createNextResearchDecision(controller.signal, runId, request);
      setDecisions((current) => [created, ...current]);
      setRationale("");
      setLimitations("");
      setSubmitState("idle");
    } catch (reason: unknown) {
      setSubmitState("error");
      setSubmitError(errorMessage(reason));
    }
  }

  return <section className={styles.panel} aria-labelledby="next-decision-heading">
    <div className={styles.sectionHeading}>
      <div><p className={styles.eyebrow}>HUMAN DECISION</p><h2 id="next-decision-heading">Choose what happens next</h2></div>
      <span className={styles.resultCount}>{decisions.length} decision{decisions.length === 1 ? "" : "s"}</span>
    </div>
    <p className={styles.muted}>Record a human reject, refine, or continue decision against this exact run and its qualified evidence. A decision never approves deployment.</p>
    {loadState === "loading" && <p className={styles.loading} role="status">Loading previous decisions…</p>}
    {loadState === "error" && <div className={styles.scopeNotice} role="status"><strong>Decision history unavailable.</strong> {loadError}</div>}
    {decisions.length > 0 && <div className={styles.reviewEvidenceGrid}>
      {decisions.map((decision) => <article className={styles.reviewEvidenceCard} key={decision.artifact_id}>
        <div className={styles.reviewEvidenceHeader}><h3>{decision.outcome}</h3><span className={styles.status}>Revision {decision.revision}</span></div>
        <p className={styles.reviewEvidenceReason}>{decision.rationale}</p>
        <dl className={styles.reviewEvidenceMeta}><div><dt>Operator / time</dt><dd>{decision.operator} · {formatDecisionDate(decision.decided_at)}</dd></div><div><dt>Run / data</dt><dd>{decision.source_run_ref.artifact_id} · {decision.data_ref.artifact_id}</dd></div><div><dt>Limitations</dt><dd>{decision.limitations.join("; ")}</dd></div></dl>
      </article>)}
    </div>}
    <div className={styles.selectorGrid}>
      <label className={styles.field}><span>Decision</span><select aria-label="Next decision outcome" value={outcome} onChange={(event) => setOutcome(event.target.value as Outcome)}><option value="reject">Reject</option><option value="refine">Refine</option><option value="continue">Continue</option></select></label>
      <label className={styles.field}><span>Qualified data artifact ID</span><input aria-label="Qualified data artifact ID" value={dataArtifactId} onChange={(event) => setDataArtifactId(event.target.value)} placeholder="dataset_manifest_…" /></label>
      <label className={styles.field}><span>Implementation artifact ID</span><input aria-label="Implementation artifact ID" value={implementationArtifactId} onChange={(event) => setImplementationArtifactId(event.target.value)} placeholder="implementation_version_…" /></label>
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
    {!exactScope && <div className={styles.scopeNotice}><strong>Recording blocked.</strong> This run has no qualified scope fingerprint.</div>}
    {exactScope && !availableReview && <div className={styles.scopeNotice}><strong>Recording blocked.</strong> Complete review evidence is required.</div>}
    {exactScope && availableReview && !exactReview && <div className={styles.scopeNotice}><strong>Recording blocked.</strong> The review artifact has no current retained session graph identity and revision.</div>}
    {submitState === "error" && <div className={styles.errorBox} role="alert"><p>{submitError}</p></div>}
    <button className={styles.button} type="button" onClick={() => void submit()} disabled={!canRecord || !rationale.trim() || !limitations.trim() || submitState === "submitting"}>{submitState === "submitting" ? "Recording…" : "Record decision"}</button>
  </section>;
}

function formatDecisionDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}
