import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BarsResponse, MarketDataset } from "../src/features/market-data/client";
import { MarketDataWorkspace } from "../src/features/market-data/market-data-workspace";
import { loadMarketBars, loadMarketDatasets } from "../src/features/market-data/client";

vi.mock("../src/features/market-data/chart", () => ({
  MarketChart: ({ bars }: { bars: unknown[] }) => <div data-testid="market-chart">chart ({bars.length} bars)</div>,
}));
vi.mock("../src/features/market-data/client", () => ({
  loadMarketDatasets: vi.fn(),
  loadMarketBars: vi.fn(),
  datasetKey: (dataset: MarketDataset) => [dataset.asset_class, dataset.symbol, dataset.timeframe, dataset.source ?? ""].join("|"),
}));

const dataset: MarketDataset = {
  asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca",
  first_ts: "2026-09-10T09:30:00Z", last_ts: "2026-09-10T16:00:00Z", bar_count: 2,
};
const bars: BarsResponse = {
  items: [
    { symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:30:00Z", open: 100, high: 102, low: 99, close: 101, volume: 500, source: "alpaca" },
    { symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:31:00Z", open: 101, high: 103, low: 100, close: 102, volume: 600, source: "alpaca" },
  ],
  page: { limit: 50000, offset: 0, total: 2, has_more: false },
};

beforeEach(() => {
  vi.mocked(loadMarketDatasets).mockReset().mockResolvedValue({ items: [dataset], page: { limit: 500, offset: 0, total: 1, has_more: false } });
  vi.mocked(loadMarketBars).mockReset().mockResolvedValue(bars);
});

describe("market data exploration workflow", () => {
  it("discovers a dataset, requests its UTC range, and exposes chart plus source rows", async () => {
    render(<MarketDataWorkspace />);
    expect(screen.getByRole("heading", { name: "Market data" })).toBeVisible();
    expect(screen.getByText(/stocks and crypto in OHLCV format/)).toBeVisible();
    expect(await screen.findByRole("heading", { name: "AAPL · 1Min" })).toBeVisible();
    expect(await screen.findByTestId("market-chart")).toHaveTextContent("2 bars");
    expect(screen.getByText("2026-09-10 09:30:00 UTC")).toBeVisible();
    expect(screen.getByText("500")).toBeVisible();
    expect(vi.mocked(loadMarketBars).mock.calls[0]?.[1]).toMatchObject({ asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca" });
  });

  it("shows a truthful empty result when the selected range has no rows", async () => {
    vi.mocked(loadMarketBars).mockResolvedValue({ items: [], page: { limit: 50000, offset: 0, total: 0, has_more: false } });
    render(<MarketDataWorkspace />);
    expect(await screen.findByText(/No bars match this symbol/)).toBeVisible();
    expect(screen.queryByTestId("market-chart")).not.toBeInTheDocument();
  });

  it("shows unavailable discovery evidence when the database has no datasets", async () => {
    vi.mocked(loadMarketDatasets).mockResolvedValue({
      items: [],
      page: { limit: 500, offset: 0, total: 0, has_more: false },
      discovery: {
        provider: "alpaca",
        catalogue_completeness: "unavailable",
        catalogue_freshness: "unknown",
        can_discover: false,
        can_load: false,
        load_capability: "unavailable",
        reason: "No stored dataset slices are available for this Console scope.",
      },
    });

    render(<MarketDataWorkspace />);

    expect(await screen.findByText("Catalogue: unavailable")).toBeVisible();
    expect(screen.getByText("Discovery: unavailable")).toBeVisible();
    expect(screen.getByText("Loading: unavailable")).toBeVisible();
    expect(screen.getByText("No stored dataset slices are available for this Console scope.")).toBeVisible();
  });

  it("keeps complete catalogue and load capability as separate visible states", async () => {
    vi.mocked(loadMarketDatasets).mockResolvedValue({
      items: [dataset],
      page: { limit: 500, offset: 0, total: 1, has_more: false },
      discovery: {
        provider: "alpaca",
        catalogue_completeness: "complete",
        catalogue_freshness: "fresh",
        can_discover: true,
        can_load: true,
        load_capability: "load_capable",
        reason: "Provider receipt covers the requested scope.",
      },
    });

    render(<MarketDataWorkspace />);

    expect(await screen.findByText("Catalogue: complete")).toBeVisible();
    expect(screen.getByText("Freshness: fresh")).toBeVisible();
    expect(screen.getByText("Discovery: available")).toBeVisible();
    expect(screen.getByText("Loading: capable")).toBeVisible();
    expect(screen.getByText("Provider receipt covers the requested scope.")).toBeVisible();
  });

  it("applies a range and retries a failed bars request", async () => {
    vi.mocked(loadMarketBars).mockRejectedValueOnce(new Error("Console database is unavailable")).mockResolvedValueOnce(bars);
    const user = userEvent.setup();
    render(<MarketDataWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Console database is unavailable");
    await user.click(screen.getByRole("button", { name: "Retry bars" }));
    expect(await screen.findByTestId("market-chart")).toBeVisible();
    const from = screen.getByLabelText("From UTC");
    await user.clear(from);
    await user.type(from, "2026-09-10T10:00");
    await user.click(screen.getByRole("button", { name: "Apply range" }));
    await waitFor(() => expect(vi.mocked(loadMarketBars).mock.calls.at(-1)?.[1]).toMatchObject({ start: "2026-09-10T10:00:00.000Z" }));
  });

  it("cancels discovery when the workspace unmounts", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(loadMarketDatasets).mockImplementation((_requestSignal) => {
      signal = _requestSignal;
      return new Promise<never>(() => {});
    });
    const view = render(<MarketDataWorkspace />);
    await waitFor(() => expect(loadMarketDatasets).toHaveBeenCalled());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
