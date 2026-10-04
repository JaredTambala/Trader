"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { datasetKey, loadMarketBars, loadMarketDatasets, type BarPoint, type BarsResponse, type MarketDataset } from "./client";
import { MarketChart } from "./chart";
import { ConsoleShell } from "../shell/console-shell";
import styles from "./market-data-workspace.module.css";

const REQUEST_TIMEOUT = 10_000;

type Range = { start: string; end: string };
type RequestState = "idle" | "loading" | "ready" | "error";

function formatInputDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return date.toISOString().slice(0, 16);
}

function inputToIso(value: string) {
  if (!value) return undefined;
  const date = new Date(`${value}:00Z`);
  return Number.isNaN(date.valueOf()) ? undefined : date.toISOString();
}

function formatUtc(value: string) {
  return new Date(value).toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function formatNumber(value: number | null | undefined) {
  return value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function errorMessage(error: unknown, resource: string) {
  if (error instanceof Error && error.name === "AbortError") return `${resource} request cancelled.`;
  if (error instanceof Error && error.message) return error.message;
  return `${resource} could not be loaded.`;
}

function sourceLabel(source: string | null | undefined) {
  return source || "Unspecified source";
}

function describeDataset(dataset: MarketDataset) {
  return `${dataset.symbol} · ${dataset.timeframe} · ${sourceLabel(dataset.source)} · ${dataset.asset_class}`;
}

function datasetRange(dataset: MarketDataset): Range {
  return { start: formatInputDate(dataset.first_ts), end: formatInputDate(dataset.last_ts) };
}

function useDeadline() {
  return useCallback((signal: AbortSignal) => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
    const relay = () => controller.abort();
    signal.addEventListener("abort", relay, { once: true });
    return {
      signal: controller.signal,
      clear: () => {
        window.clearTimeout(timer);
        signal.removeEventListener("abort", relay);
      },
    };
  }, []);
}

export function MarketDataWorkspace() {
  const deadline = useDeadline();
  const [datasets, setDatasets] = useState<MarketDataset[]>([]);
  const [datasetPage, setDatasetPage] = useState<{ has_more: boolean; offset: number; total: number; limit: number } | null>(null);
  const [datasetState, setDatasetState] = useState<RequestState>("loading");
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetRequest, setDatasetRequest] = useState({ offset: 0, append: false, nonce: 0 });
  const [selectedKey, setSelectedKey] = useState("");
  const selectedKeyRef = useRef("");
  const [draftRange, setDraftRange] = useState<Range>({ start: "", end: "" });
  const [appliedRange, setAppliedRange] = useState<Range>({ start: "", end: "" });
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [bars, setBars] = useState<BarsResponse | null>(null);
  const [barsState, setBarsState] = useState<RequestState>("idle");
  const [barsError, setBarsError] = useState<string | null>(null);
  const [barsOffset, setBarsOffset] = useState(0);
  const [barsRevision, setBarsRevision] = useState(0);

  useEffect(() => {
    const source = new AbortController();
    const timed = deadline(source.signal);
    async function requestDatasets() {
      setDatasetState("loading");
      setDatasetError(null);
      try {
        const response = await loadMarketDatasets(timed.signal, datasetRequest.offset);
        setDatasets((previous) => datasetRequest.append ? [...previous, ...response.items] : [...response.items]);
        setDatasetPage(response.page);
        if (!selectedKeyRef.current && response.items[0]) {
          const firstKey = datasetKey(response.items[0]);
          selectedKeyRef.current = firstKey;
          setSelectedKey(firstKey);
          const range = datasetRange(response.items[0]);
          setDraftRange(range);
          setAppliedRange(range);
        }
        setDatasetState("ready");
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDatasetState("error");
        setDatasetError(errorMessage(error, "Market datasets"));
      } finally {
        timed.clear();
      }
    }
    void requestDatasets();
    return () => {
      source.abort();
      timed.clear();
    };
  }, [deadline, datasetRequest]);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => datasetKey(dataset) === selectedKey) ?? null,
    [datasets, selectedKey],
  );

  useEffect(() => {
    if (!selectedDataset) return;
    const dataset = selectedDataset;
    const source = new AbortController();
    const timed = deadline(source.signal);
    async function requestBars() {
      setBarsState("loading");
      setBarsError(null);
      try {
        const response = await loadMarketBars(timed.signal, {
          asset_class: dataset.asset_class,
          symbol: dataset.symbol,
          timeframe: dataset.timeframe,
          source: dataset.source ?? undefined,
          start: inputToIso(appliedRange.start),
          end: inputToIso(appliedRange.end),
          offset: barsOffset,
        });
        setBars(response);
        setBarsState("ready");
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setBarsState("error");
        setBarsError(errorMessage(error, "Market bars"));
      } finally {
        timed.clear();
      }
    }
    void requestBars();
    return () => {
      source.abort();
      timed.clear();
    };
  }, [appliedRange, barsOffset, barsRevision, deadline, selectedDataset]);

  const selectDataset = (key: string) => {
    const dataset = datasets.find((candidate) => datasetKey(candidate) === key);
    if (!dataset) return;
    selectedKeyRef.current = key;
    setSelectedKey(key);
    const range = datasetRange(dataset);
    setDraftRange(range);
    setAppliedRange(range);
    setBarsOffset(0);
  };

  const applyRange = () => {
    if (draftRange.start && draftRange.end && draftRange.end < draftRange.start) {
      setRangeError("The UTC end must not precede the UTC start.");
      return;
    }
    setRangeError(null);
    setBarsOffset(0);
    setAppliedRange(draftRange);
  };

  const choosePreset = (days: number | null) => {
    setRangeError(null);
    if (days === null) {
      const empty = { start: "", end: "" };
      setDraftRange(empty);
      setAppliedRange(empty);
      setBarsOffset(0);
      return;
    }
    const anchor = selectedDataset?.last_ts ? new Date(selectedDataset.last_ts) : new Date();
    const start = new Date(anchor.valueOf() - days * 86_400_000);
    const nextRange = { start: formatInputDate(start.toISOString()), end: formatInputDate(anchor.toISOString()) };
    setDraftRange(nextRange);
    setAppliedRange(nextRange);
    setBarsOffset(0);
  };

  const refreshBars = () => setBarsRevision((revision) => revision + 1);
  const hasMoreDatasets = datasetPage?.has_more ?? false;
  const hasMoreBars = bars?.page.has_more ?? false;
  const sample = bars?.items.slice(0, 25) ?? [];
  const loading = datasetState === "loading" || barsState === "loading";

  return (
    <ConsoleShell>
    <div className={styles.shell}>
      <main className={styles.main}>
        <div className={styles.heading}>
          <div><p className={styles.eyebrow}>DATA WORKSPACE</p><h1>Market data</h1><p className={styles.subtitle}>Explore stocks and crypto in OHLCV format with a full candlestick and volume view.</p></div>
          <button className={styles.button} type="button" onClick={refreshBars} disabled={loading || !selectedDataset}>{barsState === "loading" ? "Loading…" : "Refresh"}<span aria-hidden="true">↻</span></button>
        </div>

        <section className={styles.controls} aria-labelledby="controls-heading">
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>QUERY</p><h2 id="controls-heading">Choose a data slice</h2></div><span className={styles.utc}>All times UTC</span></div>
          {datasetState === "loading" && <p role="status">Discovering available datasets…</p>}
          {datasetState === "error" && <div className={styles.errorBox} role="alert"><p>{datasetError}</p><button className={styles.secondaryButton} type="button" onClick={() => setDatasetRequest({ offset: 0, append: false, nonce: Date.now() })}>Retry datasets</button></div>}
          {datasetState === "ready" && datasets.length === 0 && <p className={styles.empty}>No market datasets are available in this database.</p>}
          {datasets.length > 0 && <>
            <label className={styles.field}><span>Dataset</span><select aria-label="Market dataset" value={selectedKey} onChange={(event) => selectDataset(event.target.value)}>{datasets.map((dataset) => <option value={datasetKey(dataset)} key={datasetKey(dataset)}>{describeDataset(dataset)}</option>)}</select></label>
            {selectedDataset && <div className={styles.datasetMeta}><span><strong>{selectedDataset.symbol}</strong> / {selectedDataset.timeframe}</span><span>{sourceLabel(selectedDataset.source)}</span><span>{selectedDataset.bar_count.toLocaleString("en-US")} bars available</span></div>}
            <div className={styles.rangeRow}>
              <label className={styles.field}><span>From (UTC)</span><input aria-label="From UTC" type="datetime-local" value={draftRange.start} onChange={(event) => setDraftRange((range) => ({ ...range, start: event.target.value }))} /></label>
              <label className={styles.field}><span>To (UTC)</span><input aria-label="To UTC" type="datetime-local" value={draftRange.end} onChange={(event) => setDraftRange((range) => ({ ...range, end: event.target.value }))} /></label>
              <button className={styles.secondaryButton} type="button" onClick={applyRange}>Apply range</button>
            </div>
            <div className={styles.presetRow} aria-label="Range presets"><span>Quick range</span><button type="button" onClick={() => choosePreset(null)}>All available</button><button type="button" onClick={() => choosePreset(1)}>1 day</button><button type="button" onClick={() => choosePreset(5)}>5 days</button><button type="button" onClick={() => choosePreset(30)}>30 days</button></div>
            {rangeError && <p className={styles.fieldError} role="alert">{rangeError}</p>}
            {hasMoreDatasets && <button className={styles.textButton} type="button" onClick={() => setDatasetRequest({ offset: datasets.length, append: true, nonce: Date.now() })} disabled={datasetState === "loading"}>Load more datasets</button>}
          </>}
        </section>

        <section className={styles.chartPanel} aria-labelledby="chart-heading">
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>PRICE + VOLUME</p><h2 id="chart-heading">{selectedDataset ? `${selectedDataset.symbol} · ${selectedDataset.timeframe}` : "Market chart"}</h2></div>{bars && <span className={styles.resultCount}>{bars.page.total.toLocaleString("en-US")} matching bars</span>}</div>
          {barsState === "loading" && <div className={styles.loadingChart} role="status">Loading OHLCV bars…</div>}
          {barsState === "error" && <div className={styles.errorBox} role="alert"><p>{barsError}</p><button className={styles.secondaryButton} type="button" onClick={refreshBars}>Retry bars</button></div>}
          {barsState === "ready" && bars?.items.length === 0 && <p className={styles.empty}>No bars match this symbol and UTC range. Choose a wider range or another dataset.</p>}
          {barsState === "ready" && bars && bars.items.length > 0 && <MarketChart bars={bars.items} />}
          {barsState === "ready" && bars && <div className={styles.pagination}><span>{bars.items.length === 0 ? "0" : `${bars.page.offset + 1}–${bars.page.offset + bars.items.length}`} of {bars.page.total.toLocaleString("en-US")} bars loaded</span><div><button type="button" className={styles.secondaryButton} disabled={bars.page.offset === 0} onClick={() => setBarsOffset(Math.max(0, bars.page.offset - bars.page.limit))}>Previous window</button><button type="button" className={styles.secondaryButton} disabled={!hasMoreBars} onClick={() => setBarsOffset(bars.page.offset + bars.page.limit)}>Next window</button></div></div>}
          <p className={styles.chartHint}>Drag the lower navigator or scroll over the plot to pan and zoom. Candles use producer OHLC values; no trading signal is inferred.</p>
        </section>

        {barsState === "ready" && bars && bars.items.length > 0 && <section className={styles.tablePanel} aria-labelledby="sample-heading">
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>SOURCE ROWS</p><h2 id="sample-heading">Loaded bar sample</h2></div><span className={styles.resultCount}>First {sample.length} rows in this window</span></div>
          <div className={styles.tableWrap}><table><caption className={styles.srOnly}>First loaded OHLCV rows for {selectedDataset?.symbol}</caption><thead><tr><th scope="col">Timestamp (UTC)</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th></tr></thead><tbody>{sample.map((bar: BarPoint) => <tr key={`${bar.ts}-${bar.symbol}`}><td>{formatUtc(bar.ts)}</td><td>{formatNumber(bar.open)}</td><td>{formatNumber(bar.high)}</td><td>{formatNumber(bar.low)}</td><td>{formatNumber(bar.close)}</td><td>{formatNumber(bar.volume)}</td></tr>)}</tbody></table></div>
        </section>}
        <p className={styles.status} role="status" aria-live="polite">{loading ? "Loading market data…" : barsState === "error" || datasetState === "error" ? "Market data needs attention. Retry the failed request." : selectedDataset ? `Showing ${selectedDataset.symbol} ${selectedDataset.timeframe} from the configured database.` : "Choose a dataset to begin."}</p>
      </main>
      <footer className={styles.footer}>Trader Console<span>Market data exploration</span></footer>
    </div>
    </ConsoleShell>
  );
}
