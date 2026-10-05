import type { NextConfig } from "next";

const origin = new URL(process.env.TRADER_CONSOLE_API_ORIGIN ?? "http://127.0.0.1:8001");
if (!['http:', 'https:'].includes(origin.protocol) || origin.username || origin.password ||
    origin.pathname !== '/' || origin.search || origin.hash) {
  throw new Error('TRADER_CONSOLE_API_ORIGIN must be an HTTP(S) origin without credentials or a path');
}

const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [
      "/api/context",
      "/api/market-data/datasets",
      "/api/market-data/bars",
      "/api/market-data/evidence",
      "/api/data-scopes",
      "/api/data-scopes/:saved_scope_id",
      "/api/data-scopes/:saved_scope_id/revalidate",
      "/api/experiments",
      "/api/experiments/:experiment_id/runs",
      "/api/experiments/:experiment_id/comparison-views",
      "/api/experiments/:experiment_id/comparison-views/:view_id",
      "/api/experiments/:experiment_id/comparison-views/preview",
      "/api/backtests/catalogue",
      "/api/backtests/preflight",
      "/api/backtests/definitions",
      "/api/backtests/definitions/:definition_id",
      "/api/backtests/definitions/:definition_id/revisions",
      "/api/backtests/executions",
      "/api/backtests/executions/:execution_id",
      "/api/paper/runtime",
      "/api/paper/commands",
      "/api/paper/commands/:command_id",
      "/api/runs/:run_id",
      "/api/runs/:run_id/risk-decisions",
      "/health/live",
      "/health/ready",
    ].map((path) => ({
      source: path,
      destination: `${origin.origin}${path}`,
    }));
  },
};
export default config;
