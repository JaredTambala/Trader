import { client } from "../connection/client";
import type { components } from "../../generated/api";

export type MarketDataset = components["schemas"]["MarketDataset"];
export type BarPoint = components["schemas"]["BarPoint"];
export type PageInfo = components["schemas"]["PageInfo"];
export type MarketDatasetsResponse = components["schemas"]["MarketDatasetsResponse"];
export type BarsResponse = components["schemas"]["BarsResponse"];
export type IndicatorSeriesPoint = components["schemas"]["IndicatorSeriesPoint"];
export type SignalMarker = components["schemas"]["SignalMarker"];

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

export function datasetKey(dataset: MarketDataset): string {
  return [dataset.asset_class, dataset.symbol, dataset.timeframe, dataset.source ?? ""].join("|");
}
