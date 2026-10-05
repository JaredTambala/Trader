import { client } from "../connection/client";
import type { components } from "../../generated/api";

export type MarketDataset = components["schemas"]["MarketDataset"];
export type MarketDataDiscovery = components["schemas"]["MarketDataDiscovery"];
export type BarPoint = components["schemas"]["BarPoint"];
export type PageInfo = components["schemas"]["PageInfo"];
export type MarketDatasetsResponse = components["schemas"]["MarketDatasetsResponse"];
export type MarketDataEvidenceResponse = components["schemas"]["MarketDataEvidenceResponse"];
export type BarsResponse = components["schemas"]["BarsResponse"];
export type IndicatorSeriesPoint = components["schemas"]["IndicatorSeriesPoint"];
export type SignalMarker = components["schemas"]["SignalMarker"];
export type SavedDataScope = components["schemas"]["SavedDataScope"];
export type SavedDataScopeCreate = components["schemas"]["SavedDataScopeCreate"];
export type DataScopeComparisonRequest = components["schemas"]["DataScopeComparisonRequest"];
export type DataScopeComparisonResponse = components["schemas"]["DataScopeComparisonResponse"];

export const MARKET_DATA_BARS_PAGE_SIZE = 50_000;

export class MarketDataRequestError extends Error {
  readonly status?: number;
  readonly code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "MarketDataRequestError";
    this.status = status;
    this.code = code;
  }
}

async function requireResponse<T>(
  result: { data?: T; error?: unknown; response: Response },
  resource: string,
): Promise<T> {
  if (result.response.ok && result.data) return result.data;
  const detail = result.error && typeof result.error === "object" ? result.error as { code?: unknown; message?: unknown } : undefined;
  const message = typeof detail?.message === "string" ? detail.message : `${resource} could not be loaded.`;
  const code = typeof detail?.code === "string" ? detail.code : undefined;
  throw new MarketDataRequestError(message, result.response.status, code);
}

export async function loadMarketDatasets(signal: AbortSignal, offset = 0): Promise<MarketDatasetsResponse> {
  const result = await client.GET("/api/market-data/datasets", {
    params: { query: { limit: 500, offset } },
    signal,
  });
  return requireResponse(result, "Market datasets");
}

export async function loadMarketDataEvidence(
  signal: AbortSignal,
  query: {
    asset_class: "stock" | "crypto";
    symbols: string[];
    timeframe: string;
    interval?: string;
    bar_type?: string;
    provider?: string;
    source_policy?: string;
    start: string;
    end: string;
  },
): Promise<MarketDataEvidenceResponse> {
  const result = await client.GET("/api/market-data/evidence", {
    params: {
      query: {
        asset_class: query.asset_class,
        symbols: query.symbols.join(","),
        timeframe: query.timeframe,
        ...(query.interval ? { interval: query.interval } : {}),
        ...(query.bar_type ? { bar_type: query.bar_type } : {}),
        ...(query.provider ? { provider: query.provider } : {}),
        ...(query.source_policy ? { source_policy: query.source_policy } : {}),
        start: query.start,
        end: query.end,
      },
    },
    signal,
  });
  return requireResponse(result, "Market data evidence");
}

export type BarsQuery = {
  asset_class: "stock" | "crypto";
  symbol: string;
  timeframe: string;
  source?: string;
  start?: string;
  end?: string;
  offset?: number;
};

export async function loadMarketBars(signal: AbortSignal, query: BarsQuery): Promise<BarsResponse> {
  const result = await client.GET("/api/market-data/bars", {
    params: {
      query: {
        asset_class: query.asset_class,
        symbol: query.symbol,
        timeframe: query.timeframe,
        ...(query.source ? { source: query.source } : {}),
        ...(query.start ? { start: query.start } : {}),
        ...(query.end ? { end: query.end } : {}),
        limit: MARKET_DATA_BARS_PAGE_SIZE,
        offset: query.offset ?? 0,
      },
    },
    signal,
  });
  return requireResponse(result, "Market bars");
}

export async function loadSavedDataScopes(signal: AbortSignal, offset = 0): Promise<components["schemas"]["SavedDataScopesResponse"]> {
  const result = await client.GET("/api/data-scopes", {
    params: { query: { limit: 100, offset } },
    signal,
  });
  return requireResponse(result, "Saved data scopes");
}

export async function loadSavedDataScope(signal: AbortSignal, savedScopeId: string): Promise<SavedDataScope> {
  const result = await client.GET("/api/data-scopes/{saved_scope_id}", {
    params: { path: { saved_scope_id: savedScopeId } },
    signal,
  });
  return requireResponse(result, "Saved data scope");
}

export async function saveDataScope(signal: AbortSignal, body: SavedDataScopeCreate): Promise<SavedDataScope> {
  const result = await client.POST("/api/data-scopes", { body, signal });
  return requireResponse(result, "Saved data scope");
}

export async function revalidateSavedDataScope(signal: AbortSignal, savedScopeId: string): Promise<SavedDataScope> {
  const result = await client.POST("/api/data-scopes/{saved_scope_id}/revalidate", {
    params: { path: { saved_scope_id: savedScopeId } },
    signal,
  });
  return requireResponse(result, "Saved data scope evidence");
}

export async function compareSavedDataScopes(
  signal: AbortSignal,
  body: DataScopeComparisonRequest,
): Promise<DataScopeComparisonResponse> {
  const result = await client.POST("/api/data-scope-comparisons", { body, signal });
  return requireResponse(result, "Data scope comparison");
}

export function datasetKey(dataset: MarketDataset): string {
  return [dataset.asset_class, dataset.symbol, dataset.timeframe, dataset.source ?? ""].join("|");
}
