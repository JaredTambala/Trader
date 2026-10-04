import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({ baseUrl: typeof window === "undefined" ? "" : window.location.origin, cache: "no-store" });
export type Definition = components["schemas"]["ComparisonViewDefinition"];
export type SavedView = components["schemas"]["SavedComparisonView"];
export type Evaluation = components["schemas"]["ComparisonEvaluation"];
export type Run = components["schemas"]["ExperimentRunSummary"];
export type RunDetail = components["schemas"]["RunDetail"];
export type RecordValue = components["schemas"]["ResourceRecord"];
export type PageInfo = components["schemas"]["PageInfo"];
export const PAGE_SIZE = 50;
export const CURVE_LIMIT = 1000;

export class ComparisonRequestError extends Error {
  constructor(message: string, readonly status?: number) { super(message); }
}

async function request<T>(signal: AbortSignal, call: (bounded: AbortSignal) => Promise<{ response: Response; data?: T; error?: unknown }>): Promise<T> {
  const deadline = new AbortController();
  const timer = setTimeout(() => deadline.abort(), 10_000);
  try {
    const result = await call(AbortSignal.any([signal, deadline.signal]));
    if (result.response.ok && result.data !== undefined) return result.data;
    const error = result.error as { message?: unknown } | undefined;
    throw new ComparisonRequestError(typeof error?.message === "string" ? error.message : `Request failed (${result.response.status}).`, result.response.status);
  } catch (error) {
    if (signal.aborted) throw error;
    if (deadline.signal.aborted) throw new ComparisonRequestError("Request timed out. Try again.");
    throw error;
  } finally { clearTimeout(timer); }
}

export const loadContext = (signal: AbortSignal) => request(signal, (signal) => client.GET("/api/context", { signal }));
export const loadExperiments = (signal: AbortSignal, offset = 0) => request(signal, (signal) => client.GET("/api/experiments", { signal, params: { query: { limit: PAGE_SIZE, offset } } }));
export const loadRuns = (signal: AbortSignal, experimentId: string, offset = 0) => request(signal, (signal) => client.GET("/api/experiments/{experiment_id}/runs", { signal, params: { path: { experiment_id: experimentId }, query: { limit: PAGE_SIZE, offset } } }));
export const loadViews = (signal: AbortSignal, experimentId: string, offset = 0) => request(signal, (signal) => client.GET("/api/experiments/{experiment_id}/comparison-views", { signal, params: { path: { experiment_id: experimentId }, query: { limit: PAGE_SIZE, offset } } }));
export const loadView = (signal: AbortSignal, experimentId: string, viewId: string) => request(signal, (signal) => client.GET("/api/experiments/{experiment_id}/comparison-views/{view_id}", { signal, params: { path: { experiment_id: experimentId, view_id: viewId } } }));
export const previewView = (signal: AbortSignal, experimentId: string, definition: Definition) => request(signal, (signal) => client.POST("/api/experiments/{experiment_id}/comparison-views/preview", { signal, params: { path: { experiment_id: experimentId } }, body: definition }));
export const saveView = (signal: AbortSignal, experimentId: string, definition: Definition, saved: SavedView | null) => request(signal, (signal) => saved
  ? client.PUT("/api/experiments/{experiment_id}/comparison-views/{view_id}", { signal, params: { path: { experiment_id: experimentId, view_id: saved.view_id } }, body: { ...definition, expected_revision: saved.revision } })
  : client.POST("/api/experiments/{experiment_id}/comparison-views", { signal, params: { path: { experiment_id: experimentId } }, body: definition }));
export const loadRun = (signal: AbortSignal, runId: string) => request(signal, (signal) => client.GET("/api/runs/{run_id}", { signal, params: { path: { run_id: runId }, query: { section_limit: CURVE_LIMIT } } }));

/** Fetch at most two expensive run projections concurrently. */
export async function loadEvidence(signal: AbortSignal, runIds: string[]) {
  const results: { runId: string; detail?: RunDetail; error?: string }[] = [];
  for (let offset = 0; offset < runIds.length; offset += 2) {
    signal.throwIfAborted();
    results.push(...await Promise.all(runIds.slice(offset, offset + 2).map(async (runId) => {
      try { return { runId, detail: await loadRun(signal, runId) }; }
      catch (error) { signal.throwIfAborted(); return { runId, error: error instanceof Error ? error.message : "Evidence could not be loaded." }; }
    })));
  }
  return results;
}
