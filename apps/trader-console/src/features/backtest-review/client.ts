import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  cache: "no-store",
});

export type ExperimentSummary = components["schemas"]["ExperimentSummary"];
export type ExperimentRunSummary = components["schemas"]["ExperimentRunSummary"];
export type RunDetail = components["schemas"]["RunDetail"];
export type ResourceRecord = components["schemas"]["ResourceRecord"];
export type RiskDecisionsResponse = components["schemas"]["RiskDecisionsResponse"];
export type RiskDecisionOutcome = components["schemas"]["RiskDecision"]["outcome"];
export type NextResearchDecisionRecord = components["schemas"]["NextResearchDecisionRecord"];
export type NextResearchDecisionRequest = components["schemas"]["NextResearchDecisionRequest"];

export class BacktestReviewRequestError extends Error {
  readonly status?: number;
  readonly code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "BacktestReviewRequestError";
    this.status = status;
    this.code = code;
  }
}

function errorFrom(result: { response: Response; error?: unknown }, resource: string): BacktestReviewRequestError {
  const detail = result.error && typeof result.error === "object"
    ? result.error as { code?: unknown; message?: unknown }
    : undefined;
  const message = typeof detail?.message === "string" ? detail.message : `${resource} could not be loaded.`;
  const code = typeof detail?.code === "string" ? detail.code : undefined;
  return new BacktestReviewRequestError(message, result.response.status, code);
}

export async function loadExperiments(signal: AbortSignal) {
  const result = await client.GET("/api/experiments", {
    params: { query: { limit: 100, offset: 0 } },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Experiments");
  return result.data;
}

export async function loadExperimentRuns(signal: AbortSignal, experimentId: string) {
  const result = await client.GET("/api/experiments/{experiment_id}/runs", {
    params: { path: { experiment_id: experimentId }, query: { limit: 100, offset: 0 } },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Experiment runs");
  return result.data;
}

export async function loadRunDetail(signal: AbortSignal, runId: string) {
  const result = await client.GET("/api/runs/{run_id}", {
    params: { path: { run_id: runId }, query: { section_limit: 1000 } },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Backtest run");
  return result.data;
}

export async function loadRiskDecisions(
  signal: AbortSignal,
  runId: string,
  filters: {
    manager_id?: string;
    outcome?: RiskDecisionOutcome;
    cycle_id?: string;
    client_order_id?: string;
    limit?: number;
    offset?: number;
  } = {},
) {
  const result = await client.GET("/api/runs/{run_id}/risk-decisions", {
    params: {
      path: { run_id: runId },
      query: { limit: 100, offset: 0, ...filters },
    },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Risk decisions");
  return result.data;
}

export async function loadNextResearchDecisions(signal: AbortSignal, runId: string) {
  const result = await client.GET("/api/runs/{run_id}/next-decisions", {
    params: { path: { run_id: runId }, query: { limit: 20, offset: 0 } },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Research decisions");
  return result.data;
}

export async function createNextResearchDecision(
  signal: AbortSignal,
  runId: string,
  request: NextResearchDecisionRequest,
) {
  const result = await client.POST("/api/runs/{run_id}/next-decisions", {
    params: { path: { run_id: runId } },
    body: request,
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Research decision");
  return result.data;
}

export async function loadNextResearchDecision(
  signal: AbortSignal,
  runId: string,
  decisionId: string,
) {
  const result = await client.GET("/api/runs/{run_id}/next-decisions/{decision_id}", {
    params: { path: { run_id: runId, decision_id: decisionId } },
    signal,
  });
  if (!result.response.ok || !result.data) throw errorFrom(result, "Research decision");
  return result.data;
}
