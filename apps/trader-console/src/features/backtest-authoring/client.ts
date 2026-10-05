import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  cache: "no-store",
});

export type Catalogue = components["schemas"]["BacktestCatalogueResponse"];
export type CatalogueProfile = components["schemas"]["CatalogueProfile"];
export type CatalogueParameter = components["schemas"]["CatalogueParameter"];
export type PreflightRequest = components["schemas"]["BacktestPreflightRequest"];
export type PreflightResponse = components["schemas"]["BacktestPreflightResponse"];
export type DefinitionRevision = components["schemas"]["BacktestDefinitionRevision"];
export type ExecutionRecord = components["schemas"]["BacktestExecutionRecord"];
export type SavedDataScope = components["schemas"]["SavedDataScope"];

export class BacktestAuthoringRequestError extends Error {
  readonly status?: number;
  readonly code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "BacktestAuthoringRequestError";
    this.status = status;
    this.code = code;
  }
}

function requestError(result: { response: Response; error?: unknown }, resource: string) {
  const detail = result.error && typeof result.error === "object"
    ? result.error as { code?: unknown; message?: unknown }
    : undefined;
  const message = typeof detail?.message === "string" ? detail.message : `${resource} could not be loaded.`;
  const code = typeof detail?.code === "string" ? detail.code : undefined;
  return new BacktestAuthoringRequestError(message, result.response.status, code);
}

export async function loadCatalogue(signal: AbortSignal): Promise<Catalogue> {
  const result = await client.GET("/api/backtests/catalogue", { signal });
  if (!result.response.ok || !result.data) throw requestError(result, "Backtest catalogue");
  return result.data;
}

export async function loadSavedDataScope(signal: AbortSignal, savedScopeId: string): Promise<SavedDataScope> {
  const result = await client.GET("/api/data-scopes/{saved_scope_id}", {
    signal,
    params: { path: { saved_scope_id: savedScopeId } },
  });
  if (!result.response.ok || !result.data) throw requestError(result, "Saved data scope");
  return result.data;
}

export async function preflight(signal: AbortSignal, body: PreflightRequest): Promise<PreflightResponse> {
  const result = await client.POST("/api/backtests/preflight", { signal, body });
  if (!result.response.ok || !result.data) throw requestError(result, "Backtest preflight");
  return result.data;
}

export async function createDefinition(signal: AbortSignal, body: PreflightRequest): Promise<DefinitionRevision> {
  const result = await client.POST("/api/backtests/definitions", { signal, body });
  if (!result.response.ok || !result.data) throw requestError(result, "Backtest definition");
  return result.data;
}

export async function submitExecution(signal: AbortSignal, definitionId: string, idempotencyKey: string): Promise<ExecutionRecord> {
  const result = await client.POST("/api/backtests/executions", {
    signal,
    body: { definition_id: definitionId, idempotency_key: idempotencyKey },
  });
  if (!result.response.ok || !result.data) throw requestError(result, "Backtest execution");
  return result.data;
}

export async function loadExecution(signal: AbortSignal, executionId: string): Promise<ExecutionRecord> {
  const result = await client.GET("/api/backtests/executions/{execution_id}", {
    signal,
    params: { path: { execution_id: executionId } },
  });
  if (!result.response.ok || !result.data) throw requestError(result, "Backtest execution");
  return result.data;
}
