export interface paths {
    "/api/backtests/catalogue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Backtest Catalogue
         * @description Return the allowlisted strategy and risk profiles.
         */
        get: operations["backtest_catalogue_api_backtests_catalogue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Backtest Definitions
         * @description List latest immutable revisions in the configured scope.
         */
        get: operations["list_backtest_definitions_api_backtests_definitions_get"];
        put?: never;
        /**
         * Create Backtest Definition
         * @description Preflight and persist the first immutable revision for a definition.
         */
        post: operations["create_backtest_definition_api_backtests_definitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/definitions/{definition_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Backtest Definition
         * @description Return the latest immutable revision for one definition identity.
         */
        get: operations["get_backtest_definition_api_backtests_definitions__definition_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/definitions/{definition_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Backtest Definition Revision
         * @description Preflight and append one immutable revision to an existing definition.
         */
        post: operations["create_backtest_definition_revision_api_backtests_definitions__definition_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/executions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Backtest Executions
         * @description List durable commands in the configured scope.
         */
        get: operations["list_backtest_executions_api_backtests_executions_get"];
        put?: never;
        /**
         * Submit Backtest Execution
         * @description Submit one idempotent queued command for an immutable definition.
         */
        post: operations["submit_backtest_execution_api_backtests_executions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/executions/{execution_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Backtest Execution
         * @description Return durable status for one execution command.
         */
        get: operations["get_backtest_execution_api_backtests_executions__execution_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/backtests/preflight": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Backtest Preflight
         * @description Normalize and validate a draft without persisting or queueing it.
         */
        post: operations["backtest_preflight_api_backtests_preflight_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Context
         * @description Return configured scope, not verified broker identity or trading health.
         */
        get: operations["get_context"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-scopes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Saved Data Scopes
         * @description List saved scopes without changing their evidence state.
         */
        get: operations["list_saved_data_scopes_api_data_scopes_get"];
        put?: never;
        /**
         * Create Saved Data Scope
         * @description Persist one exact scope and matching manifest/quality references.
         */
        post: operations["create_saved_data_scope_api_data_scopes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-scopes/{saved_scope_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Saved Data Scope
         * @description Reopen one saved scope with its persisted evidence qualification.
         */
        get: operations["get_saved_data_scope_api_data_scopes__saved_scope_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-scopes/{saved_scope_id}/revalidate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revalidate Saved Data Scope
         * @description Re-read exact producer evidence and persist active/stale/unavailable state.
         */
        post: operations["revalidate_saved_data_scope_api_data_scopes__saved_scope_id__revalidate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/experiments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Experiments
         * @description Discover experiment groups from published backtest runs.
         */
        get: operations["experiments_api_experiments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/experiments/{experiment_id}/comparison-views": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Comparison Views
         * @description List saved definitions for one experiment and configured scope.
         */
        get: operations["list_comparison_views_api_experiments__experiment_id__comparison_views_get"];
        put?: never;
        /**
         * Create Comparison View
         * @description Persist a new user-authored comparison definition.
         */
        post: operations["create_comparison_view_api_experiments__experiment_id__comparison_views_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/experiments/{experiment_id}/comparison-views/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Comparison View
         * @description Evaluate a draft against current evidence without saving it.
         */
        post: operations["preview_comparison_view_api_experiments__experiment_id__comparison_views_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/experiments/{experiment_id}/comparison-views/{view_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Comparison View
         * @description Load one definition and reevaluate its selected evidence now.
         */
        get: operations["get_comparison_view_api_experiments__experiment_id__comparison_views__view_id__get"];
        /**
         * Replace Comparison View
         * @description Replace a definition only when its revision is still current.
         */
        put: operations["replace_comparison_view_api_experiments__experiment_id__comparison_views__view_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/experiments/{experiment_id}/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Experiment Runs
         * @description List runs and comparison eligibility within one experiment.
         */
        get: operations["experiment_runs_api_experiments__experiment_id__runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-data/bars": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Market Data Bars
         * @description Return bounded OHLCV observations ordered from earliest to latest.
         */
        get: operations["market_data_bars_api_market_data_bars_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-data/datasets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Market Datasets
         * @description List available symbol/timeframe/source market-data slices.
         */
        get: operations["market_datasets_api_market_data_datasets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-data/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Market Data Evidence
         * @description Return qualified Data evidence for one exact bounded scope.
         */
        get: operations["market_data_evidence_api_market_data_evidence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/paper/commands": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Paper Operator Commands
         * @description Return bounded command audit history for the authorized operator.
         */
        get: operations["list_paper_operator_commands_api_paper_commands_get"];
        put?: never;
        /**
         * Submit Paper Operator Command
         * @description Validate and queue one human-authorized paper-runtime command.
         */
        post: operations["submit_paper_operator_command_api_paper_commands_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/paper/commands/{command_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Paper Operator Command
         * @description Return one durable command receipt for operator polling.
         */
        get: operations["get_paper_operator_command_api_paper_commands__command_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/paper/runtime": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Paper Runtime
         * @description Return read-only paper operational evidence with explicit qualifiers.
         */
        get: operations["paper_runtime_api_paper_runtime_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Run Detail
         * @description Return a backtest run and its published evidence sections.
         */
        get: operations["run_detail_api_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/runs/{run_id}/next-decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Next Research Decisions
         * @description List the latest decision revision for each decision stream on a run.
         */
        get: operations["list_next_research_decisions_api_runs__run_id__next_decisions_get"];
        put?: never;
        /**
         * Record Next Research Decision
         * @description Record one human-owned reject, refine, or continue decision.
         */
        post: operations["record_next_research_decision_api_runs__run_id__next_decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/runs/{run_id}/next-decisions/{decision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Next Research Decision
         * @description Read the latest or one exact immutable decision revision.
         */
        get: operations["get_next_research_decision_api_runs__run_id__next_decisions__decision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/runs/{run_id}/risk-decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Risk Decisions
         * @description Return a bounded, filterable manager decision trace for one run.
         */
        get: operations["risk_decisions_api_runs__run_id__risk_decisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Liveness
         * @description Translate the service's process-liveness contract to HTTP.
         */
        get: operations["liveness_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Readiness
         * @description Translate the service's database readiness to HTTP.
         */
        get: operations["readiness_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ApiError
         * @description Stable error envelope for resource failures.
         */
        ApiError: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /**
         * BacktestAssumptions
         * @description Bounded execution and missing-data assumptions for preflight.
         */
        BacktestAssumptions: {
            /**
             * Allow Latest Prior Bar
             * @default true
             */
            allow_latest_prior_bar: boolean;
            /**
             * Allow Price Carry Forward
             * @default true
             */
            allow_price_carry_forward: boolean;
            /**
             * Fee Bps
             * @default 0
             */
            fee_bps: number;
            /**
             * Fee Fixed Per Order
             * @default 0
             */
            fee_fixed_per_order: number;
            /**
             * Fee Minimum
             * @default 0
             */
            fee_minimum: number;
            /**
             * Fill Model
             * @default full_fill
             * @enum {string}
             */
            fill_model: "full_fill" | "next_bar";
            /**
             * Latency Ms
             * @default 0
             */
            latency_ms: number;
            /**
             * Slippage Bps
             * @default 0
             */
            slippage_bps: number;
        };
        /**
         * BacktestCatalogueResponse
         * @description Versioned allowlisted strategy and risk catalogue.
         */
        BacktestCatalogueResponse: {
            /** Catalogue Version */
            catalogue_version: string;
            /** Risk Profiles */
            risk_profiles: components["schemas"]["CatalogueProfile"][];
            /** Strategy Profiles */
            strategy_profiles: components["schemas"]["CatalogueProfile"][];
        };
        /**
         * BacktestCoverageCheck
         * @description Read-only data coverage evidence returned by preflight.
         */
        BacktestCoverageCheck: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /** Available */
            available: boolean;
            /**
             * Bar Count
             * @default 0
             */
            bar_count: number;
            /** First Ts */
            first_ts?: string | null;
            /** Last Ts */
            last_ts?: string | null;
            /**
             * Requested End
             * Format: date-time
             */
            requested_end: string;
            /**
             * Required Start
             * Format: date-time
             */
            required_start: string;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
            /** Warmup Bars */
            warmup_bars: number;
            /** Warmup Satisfied */
            warmup_satisfied: boolean;
        };
        /**
         * BacktestDataScopeHandoff
         * @description Exact saved Data evidence handed into backtest authoring.
         *
         *     The handoff repeats the immutable scope identity and evidence references so
         *     a preflight can detect a stale client or a changed selection.  The server
         *     resolves ``saved_scope_id`` and never widens the selection to a new
         *     catalogue or aggregate coverage query.
         */
        BacktestDataScopeHandoff: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /**
             * End
             * Format: date-time
             */
            end: string;
            /** Evidence Reason */
            evidence_reason?: string | null;
            evidence_status: components["schemas"]["DataScopeEvidenceStatus"];
            /** Fingerprint */
            fingerprint: string;
            /** Interval */
            interval: string;
            /** Manifest Artifact Id */
            manifest_artifact_id: string;
            /** Quality Artifact Id */
            quality_artifact_id: string;
            /**
             * Saved Scope Id
             * Format: uuid
             */
            saved_scope_id: string;
            source_policy: components["schemas"]["DataScopeSourcePolicy"];
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
            /** Universe */
            universe?: string | null;
        };
        /**
         * BacktestDefinition
         * @description Normalized, content-addressed input to one future backtest execution.
         */
        BacktestDefinition: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            assumptions?: components["schemas"]["BacktestAssumptions"];
            /**
             * Benchmark Id
             * @default buy_hold
             * @enum {string}
             */
            benchmark_id: "buy_hold" | "none";
            data_scope: components["schemas"]["BacktestDataScopeHandoff"];
            /** Display Name */
            display_name: string;
            /**
             * End
             * Format: date-time
             */
            end: string;
            /** Initial Cash */
            initial_cash: number;
            /**
             * Initial Positions
             * @default []
             */
            initial_positions: components["schemas"]["InitialPositionInput"][];
            resource_limits?: components["schemas"]["BacktestResourceLimits"];
            /** Risk Catalogue Version */
            risk_catalogue_version: string;
            risk_implementation_lineage: components["schemas"]["ImplementationLineage"];
            /** Risk Parameters */
            risk_parameters?: {
                [key: string]: unknown;
            };
            /** Risk Profile Id */
            risk_profile_id: string;
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Strategy Catalogue Version */
            strategy_catalogue_version: string;
            strategy_implementation_lineage: components["schemas"]["ImplementationLineage"];
            /** Strategy Parameters */
            strategy_parameters?: {
                [key: string]: unknown;
            };
            /** Strategy Profile Id */
            strategy_profile_id: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
        };
        /**
         * BacktestDefinitionRevision
         * @description Immutable Console-owned definition revision returned after persistence.
         */
        BacktestDefinitionRevision: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            definition: components["schemas"]["BacktestDefinition"];
            /** Definition Id */
            definition_id: string;
            /**
             * Definition Version
             * @default 1
             * @constant
             */
            definition_version: 1;
            /** Fingerprint */
            fingerprint: string;
            /** Revision */
            revision: number;
            /** Scope Id */
            scope_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * BacktestDefinitionsResponse
         * @description Bounded page of the latest immutable revision for each definition.
         */
        BacktestDefinitionsResponse: {
            /** Items */
            items: components["schemas"]["BacktestDefinitionRevision"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * BacktestExecutionRecord
         * @description Durable execution command state linked to one immutable definition.
         */
        BacktestExecutionRecord: {
            /** Attempt */
            attempt: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Definition Fingerprint */
            definition_fingerprint: string;
            /** Definition Id */
            definition_id: string;
            /** Definition Revision */
            definition_revision: number;
            /** Execution Id */
            execution_id: string;
            /** Finished At */
            finished_at?: string | null;
            /** Heartbeat At */
            heartbeat_at?: string | null;
            /** Idempotency Key */
            idempotency_key: string;
            /** Last Decision At */
            last_decision_at?: string | null;
            /** Lease Expires At */
            lease_expires_at?: string | null;
            /** Processed Cycles */
            processed_cycles: number;
            /** Run Id */
            run_id?: string | null;
            /** Scope Id */
            scope_id: string;
            /** Started At */
            started_at?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "completed" | "partial" | "failed" | "reconciliation_required";
            /** Terminal Error Code */
            terminal_error_code?: string | null;
            /** Terminal Error Message */
            terminal_error_message?: string | null;
            /** Total Cycles */
            total_cycles?: number | null;
            /**
             * Warning Summary
             * @default []
             */
            warning_summary: string[];
            /** Worker Id */
            worker_id?: string | null;
        };
        /**
         * BacktestExecutionSubmit
         * @description Idempotent request to enqueue one persisted definition revision.
         */
        BacktestExecutionSubmit: {
            /**
             * Definition Id
             * Format: uuid
             */
            definition_id: string;
            /** Idempotency Key */
            idempotency_key: string;
        };
        /**
         * BacktestExecutionsResponse
         * @description Bounded page of durable execution command records.
         */
        BacktestExecutionsResponse: {
            /** Items */
            items: components["schemas"]["BacktestExecutionRecord"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * BacktestPreflightRequest
         * @description User-authored draft validated before persistence or execution.
         */
        BacktestPreflightRequest: {
            /** Asset Class */
            asset_class: string;
            assumptions?: components["schemas"]["BacktestAssumptions"];
            /**
             * Benchmark Id
             * @default buy_hold
             * @enum {string}
             */
            benchmark_id: "buy_hold" | "none";
            data_scope: components["schemas"]["BacktestDataScopeHandoff"];
            /**
             * Display Name
             * @default Untitled backtest
             */
            display_name: string;
            /**
             * End
             * Format: date-time
             */
            end: string;
            /**
             * Initial Cash
             * @default 100000
             */
            initial_cash: number;
            /**
             * Initial Positions
             * @default []
             */
            initial_positions: components["schemas"]["InitialPositionInput"][];
            resource_limits?: components["schemas"]["BacktestResourceLimits"];
            /** Risk Catalogue Version */
            risk_catalogue_version?: string | null;
            risk_implementation_lineage?: components["schemas"]["ImplementationLineage"] | null;
            /** Risk Parameters */
            risk_parameters?: {
                [key: string]: unknown;
            };
            /**
             * Risk Profile Id
             * @default noop
             */
            risk_profile_id: string;
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Strategy Catalogue Version */
            strategy_catalogue_version?: string | null;
            strategy_implementation_lineage?: components["schemas"]["ImplementationLineage"] | null;
            /** Strategy Parameters */
            strategy_parameters?: {
                [key: string]: unknown;
            };
            /** Strategy Profile Id */
            strategy_profile_id: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
        };
        /**
         * BacktestPreflightResponse
         * @description Normalized preflight result with no producer or command side effects.
         */
        BacktestPreflightResponse: {
            /** Catalogue Version */
            catalogue_version: string;
            /**
             * Coverage
             * @default []
             */
            coverage: components["schemas"]["BacktestCoverageCheck"][];
            /** Definition Fingerprint */
            definition_fingerprint?: string | null;
            /**
             * Issues
             * @default []
             */
            issues: components["schemas"]["PreflightIssue"][];
            normalized_definition?: components["schemas"]["BacktestDefinition"] | null;
            /** Valid */
            valid: boolean;
        };
        /**
         * BacktestResourceLimits
         * @description Explicit bounded resources accepted by a backtest definition.
         */
        BacktestResourceLimits: {
            /**
             * Max Bars
             * @default 5000000
             */
            max_bars: number;
            /**
             * Max Cycles
             * @default 1000000
             */
            max_cycles: number;
            /**
             * Timeout Seconds
             * @default 3600
             */
            timeout_seconds: number;
        };
        /**
         * BarPoint
         * @description One producer-owned OHLCV observation.
         */
        BarPoint: {
            /** Close */
            close?: number | null;
            /** High */
            high?: number | null;
            /** Ingested At */
            ingested_at?: string | null;
            /** Low */
            low?: number | null;
            /** Open */
            open?: number | null;
            /** Source */
            source?: string | null;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
            /** Trade Count */
            trade_count?: number | null;
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
            /** Volume */
            volume?: number | null;
            /** Vwap */
            vwap?: number | null;
        };
        /**
         * BarsResponse
         * @description A page of OHLCV observations.
         */
        BarsResponse: {
            /** Items */
            items: components["schemas"]["BarPoint"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * BoundedNextExperimentContract
         * @description Bounded successor experiment attached to a refine or continue decision.
         */
        BoundedNextExperimentContract: {
            /** Assumptions */
            assumptions?: {
                [key: string]: unknown;
            };
            data_ref: components["schemas"]["NextDecisionArtifactReference"];
            /**
             * Evaluation End
             * Format: date-time
             */
            evaluation_end: string;
            /**
             * Evaluation Start
             * Format: date-time
             */
            evaluation_start: string;
            /** Implementation Refs */
            implementation_refs: components["schemas"]["NextDecisionArtifactReference"][];
            /** Max Runs */
            max_runs: number;
            /** Question */
            question: string;
            /** Success Criteria */
            success_criteria: string[];
        };
        /**
         * BrokerAccountBinding
         * @description Evidence level for the scope's configured brokerage binding.
         * @enum {string}
         */
        BrokerAccountBinding: "configured" | "not_applicable";
        /**
         * CatalogueParameter
         * @description Public typed parameter metadata for one allowlisted profile.
         */
        CatalogueParameter: {
            /** Default */
            default?: unknown;
            /** Description */
            description?: string | null;
            /** Maximum */
            maximum?: number | null;
            /** Minimum */
            minimum?: number | null;
            /** Name */
            name: string;
            /**
             * Required
             * @default false
             */
            required: boolean;
            /**
             * Type
             * @enum {string}
             */
            type: "integer" | "number" | "boolean" | "string";
        };
        /**
         * CatalogueProfile
         * @description One discoverable strategy or risk profile.
         */
        CatalogueProfile: {
            /** Description */
            description: string;
            /**
             * Evidence Requirements
             * @default []
             */
            evidence_requirements: string[];
            /**
             * Kind
             * @enum {string}
             */
            kind: "strategy" | "risk";
            /**
             * Lookback Bars
             * @default 0
             */
            lookback_bars: number;
            /**
             * Manager Ids
             * @default []
             */
            manager_ids: string[];
            /** Name */
            name: string;
            /**
             * Parameters
             * @default []
             */
            parameters: components["schemas"]["CatalogueParameter"][];
            /** Profile Id */
            profile_id: string;
            /**
             * Reason Codes
             * @default []
             */
            reason_codes: string[];
            /**
             * Supported Asset Classes
             * @default []
             */
            supported_asset_classes: string[];
            /**
             * Supported Timeframes
             * @default []
             */
            supported_timeframes: string[];
            /** Version */
            version: string;
        };
        /**
         * ComparisonEvaluation
         * @description Live admission result, independent of the saved definition's revision.
         */
        ComparisonEvaluation: {
            /** Eligible Run Ids */
            eligible_run_ids: string[];
            /** Runs */
            runs: components["schemas"]["ComparisonRunEligibility"][];
            /**
             * State
             * @enum {string}
             */
            state: "empty" | "unavailable" | "one_run" | "ready";
        };
        /**
         * ComparisonRunEligibility
         * @description Current eligibility of one selected ID; excluded IDs retain their reason.
         */
        ComparisonRunEligibility: {
            /** Eligible */
            eligible: boolean;
            /** Exclusion Reason */
            exclusion_reason?: string | null;
            /** Run Id */
            run_id: string;
            /** Scope Fingerprint */
            scope_fingerprint?: string | null;
        };
        /**
         * ComparisonViewDefinition
         * @description User intent only; unknown keys and duplicate selections are rejected.
         */
        ComparisonViewDefinition: {
            /**
             * Metric Keys
             * @default [
             *       "strategy_total_return"
             *     ]
             */
            metric_keys: ("strategy_total_return" | "benchmark_total_return" | "strategy_max_drawdown" | "benchmark_max_drawdown" | "strategy_sharpe" | "strategy_trade_count" | "warnings_count")[];
            /** Name */
            name: string;
            /** Reference Run Id */
            reference_run_id?: string | null;
            /**
             * Run Ids
             * @default []
             */
            run_ids: string[];
            /**
             * Series Keys
             * @default [
             *       "strategy_normalized"
             *     ]
             */
            series_keys: ("strategy_normalized" | "benchmark_normalized" | "strategy_drawdown" | "benchmark_drawdown")[];
        };
        /**
         * ComparisonViewDetail
         * @description Saved intent and its freshly evaluated exclusions.
         */
        ComparisonViewDetail: {
            evaluation: components["schemas"]["ComparisonEvaluation"];
            view: components["schemas"]["SavedComparisonView"];
        };
        /**
         * ComparisonViewUpdate
         * @description Complete replacement guarded against lost edits.
         */
        ComparisonViewUpdate: {
            /** Expected Revision */
            expected_revision: number;
            /**
             * Metric Keys
             * @default [
             *       "strategy_total_return"
             *     ]
             */
            metric_keys: ("strategy_total_return" | "benchmark_total_return" | "strategy_max_drawdown" | "benchmark_max_drawdown" | "strategy_sharpe" | "strategy_trade_count" | "warnings_count")[];
            /** Name */
            name: string;
            /** Reference Run Id */
            reference_run_id?: string | null;
            /**
             * Run Ids
             * @default []
             */
            run_ids: string[];
            /**
             * Series Keys
             * @default [
             *       "strategy_normalized"
             *     ]
             */
            series_keys: ("strategy_normalized" | "benchmark_normalized" | "strategy_drawdown" | "benchmark_drawdown")[];
        };
        /**
         * ComparisonViewsResponse
         * @description A bounded page of definitions without live evidence queries per item.
         */
        ComparisonViewsResponse: {
            /** Items */
            items: components["schemas"]["SavedComparisonView"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * ConsoleEnvironment
         * @description Execution environment represented by one isolated Console scope.
         * @enum {string}
         */
        ConsoleEnvironment: "paper" | "backtest" | "synthetic_demo";
        /**
         * ConsoleScope
         * @description Safe public description of one server-configured API scope.
         *
         *     The database URL and brokerage provider reference are deliberately absent.
         *     One API process serves one scope backed by one isolated database.
         */
        ConsoleScope: {
            broker_account_binding: components["schemas"]["BrokerAccountBinding"];
            /** Broker Account Display Label */
            broker_account_display_label?: string | null;
            /**
             * Data Source Kind
             * @default postgresql
             * @constant
             */
            data_source_kind: "postgresql";
            /** Display Name */
            display_name: string;
            environment: components["schemas"]["ConsoleEnvironment"];
            /**
             * Isolation Kind
             * @default isolated_database
             * @constant
             */
            isolation_kind: "isolated_database";
            /**
             * Presentation Timezone
             * @default UTC
             */
            presentation_timezone: string;
            /** Scope Id */
            scope_id: string;
        };
        /**
         * DataEvidenceArtifact
         * @description Bounded public reference and payload projection for one Data artifact.
         */
        DataEvidenceArtifact: {
            /** Artifact Id */
            artifact_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Schema Version */
            schema_version: string;
            /** Source Hash */
            source_hash?: string | null;
            /** Status */
            status?: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Uri */
            uri: string;
        };
        /**
         * DataEvidenceScope
         * @description Exact bounded scope used to resolve Data-owned evidence.
         */
        DataEvidenceScope: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /** Bar Type */
            bar_type: string;
            /**
             * End
             * Format: date-time
             */
            end: string;
            /** Interval */
            interval: string;
            /** Provider */
            provider?: string | null;
            /** Source Policy */
            source_policy?: string | null;
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
        };
        /**
         * DataScopeEvidenceStatus
         * @description Current qualification state of the referenced Data evidence.
         * @enum {string}
         */
        DataScopeEvidenceStatus: "active" | "stale" | "unavailable";
        /**
         * DataScopePageInfo
         * @description Pagination evidence for saved scope collections.
         */
        DataScopePageInfo: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /**
         * DataScopeSourcePolicy
         * @description Provider and source policy frozen into a saved data scope.
         */
        DataScopeSourcePolicy: {
            /**
             * Allow Fallback
             * @default false
             */
            allow_fallback: boolean;
            /** Provider */
            provider: string;
            /** Source */
            source?: string | null;
        };
        /**
         * ExperimentRunSummary
         * @description A backtest run and its current comparison eligibility.
         */
        ExperimentRunSummary: {
            /** Asset Class */
            asset_class?: string | null;
            /** Benchmark Id */
            benchmark_id?: string | null;
            /**
             * Comparison Eligible
             * @default false
             */
            comparison_eligible: boolean;
            /** Comparison Exclusion Reason */
            comparison_exclusion_reason?: string | null;
            /**
             * Comparison Projection Available
             * @default false
             */
            comparison_projection_available: boolean;
            /** Created At */
            created_at?: string | null;
            /** Data Scope Id */
            data_scope_id?: string | null;
            /** End Ts */
            end_ts?: string | null;
            /** Experiment Id */
            experiment_id: string;
            /** Experiment Run Id */
            experiment_run_id: string;
            /** Finished At */
            finished_at?: string | null;
            /** Mode */
            mode?: string | null;
            /** Run Id */
            run_id: string;
            /** Scope Fingerprint */
            scope_fingerprint?: string | null;
            /** Session Id */
            session_id?: string | null;
            /** Start Ts */
            start_ts?: string | null;
            /** Status */
            status: string;
            /** Strategy Id */
            strategy_id?: string | null;
            /** Strategy Name */
            strategy_name?: string | null;
            /** Strategy Version */
            strategy_version?: string | null;
            /**
             * Symbols
             * @default []
             */
            symbols: string[];
            /** Timeframe */
            timeframe?: string | null;
            /** Variant Fingerprint */
            variant_fingerprint?: string | null;
            /** Variant Strategy Id */
            variant_strategy_id?: string | null;
            /** Variant Strategy Version */
            variant_strategy_version?: string | null;
        };
        /**
         * ExperimentRunsResponse
         * @description A page of runs belonging to one experiment.
         */
        ExperimentRunsResponse: {
            /** Items */
            items: components["schemas"]["ExperimentRunSummary"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * ExperimentSummary
         * @description An experiment grouping discovered from its published run projections.
         */
        ExperimentSummary: {
            /** Experiment Id */
            experiment_id: string;
            /** Latest Created At */
            latest_created_at?: string | null;
            /**
             * Metadata Available
             * @default false
             */
            metadata_available: boolean;
            /** Run Count */
            run_count: number;
            /**
             * Statuses
             * @default []
             */
            statuses: string[];
        };
        /**
         * ExperimentsResponse
         * @description A page of experiment groups.
         */
        ExperimentsResponse: {
            /** Items */
            items: components["schemas"]["ExperimentSummary"][];
            page: components["schemas"]["PageInfo"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * ImplementationLineage
         * @description Exact admitted implementation and specification lineage for authoring.
         */
        ImplementationLineage: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "exact_reuse" | "adaptation" | "new_authorship";
            /**
             * Implementation Kind
             * @enum {string}
             */
            implementation_kind: "strategy" | "risk_manager";
            /** Implementation Name */
            implementation_name: string;
            /** Implementation Validation Id */
            implementation_validation_id: string;
            /** Implementation Version */
            implementation_version: string;
            /** Implementation Version Id */
            implementation_version_id: string;
            /** Profile Id */
            profile_id: string;
            /** Source Hash */
            source_hash: string;
            /** Specification Id */
            specification_id: string;
            validation_report: components["schemas"]["ImplementationValidationReport"];
        };
        /**
         * ImplementationValidationReport
         * @description Immutable admission evidence for one executable implementation.
         */
        ImplementationValidationReport: {
            /**
             * Blockers
             * @default []
             */
            blockers: string[];
            /**
             * Implementation Kind
             * @enum {string}
             */
            implementation_kind: "strategy" | "risk_manager";
            /** Implementation Version Id */
            implementation_version_id: string;
            /** Source Hash */
            source_hash: string;
            /**
             * Status
             * @enum {string}
             */
            status: "passed" | "blocked";
            /** Valid */
            valid: boolean;
            /** Validation Id */
            validation_id: string;
            /**
             * Warnings
             * @default []
             */
            warnings: string[];
        };
        /**
         * IndicatorSeriesPoint
         * @description One persisted indicator observation with producer-owned display semantics.
         */
        IndicatorSeriesPoint: {
            /**
             * Bar Ts
             * Format: date-time
             */
            bar_ts: string;
            /** Cycle Id */
            cycle_id?: string | null;
            /** Data Scope Id */
            data_scope_id?: string | null;
            /** Indicator Name */
            indicator_name: string;
            /** Pane */
            pane: string;
            /** Parameters Fingerprint */
            parameters_fingerprint?: string | null;
            /** Run Id */
            run_id: string;
            /** Scale Group */
            scale_group: string;
            /** Series Id */
            series_id: string;
            /** Series Kind */
            series_kind: string;
            /** Series Label */
            series_label: string;
            /** Session Id */
            session_id?: string | null;
            /** Signal Event Id */
            signal_event_id?: string | null;
            /** Signal Name */
            signal_name?: string | null;
            /** Strategy Id */
            strategy_id?: string | null;
            /** Strategy Version */
            strategy_version?: string | null;
            /** Symbol */
            symbol: string;
            /** Unit */
            unit: string;
            /** Value */
            value?: number | null;
            /** Variant Fingerprint */
            variant_fingerprint?: string | null;
        };
        /**
         * InitialPositionInput
         * @description Optional initial position included in a typed backtest definition.
         */
        InitialPositionInput: {
            /** Avg Price */
            avg_price?: number | null;
            /** Qty */
            qty: number;
            /** Symbol */
            symbol: string;
        };
        /**
         * LivenessResponse
         * @description Process-liveness response that makes no database or trading claim.
         */
        LivenessResponse: {
            /**
             * Service
             * @default trader-console-api
             * @constant
             */
            service: "trader-console-api";
            /**
             * Status
             * @default alive
             * @constant
             */
            status: "alive";
        };
        /**
         * MarketDataDiscovery
         * @description Explicit catalogue and provider-load capability for the dataset view.
         *
         *     A Console read model can prove which stored slices are visible, but that
         *     evidence is separate from a provider catalogue and from permission to run a
         *     bounded load. Keeping the states together in a typed object prevents the UI
         *     from treating one visible symbol as a complete provider universe.
         */
        MarketDataDiscovery: {
            /** Can Discover */
            can_discover: boolean;
            /** Can Load */
            can_load: boolean;
            /**
             * Catalogue Completeness
             * @enum {string}
             */
            catalogue_completeness: "complete" | "partial" | "stale" | "unavailable";
            /**
             * Catalogue Freshness
             * @enum {string}
             */
            catalogue_freshness: "fresh" | "stale" | "unknown";
            /**
             * Load Capability
             * @enum {string}
             */
            load_capability: "load_capable" | "discover_only" | "unavailable";
            /** Provider */
            provider: string;
            /** Reason */
            reason?: string | null;
        };
        /**
         * MarketDataEvidenceResponse
         * @description Qualified Data manifest and quality evidence for one exact scope.
         */
        MarketDataEvidenceResponse: {
            /** Coverage */
            coverage?: {
                [key: string]: unknown;
            };
            /** Evidence Reason */
            evidence_reason: string;
            /**
             * Findings
             * @default []
             */
            findings: string[];
            manifest?: components["schemas"]["DataEvidenceArtifact"] | null;
            /**
             * Provenance
             * @default []
             */
            provenance: string[];
            /** Provider */
            provider?: string | null;
            quality?: components["schemas"]["DataEvidenceArtifact"] | null;
            scope: components["schemas"]["DataEvidenceScope"];
            /** Source Policy */
            source_policy?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "complete" | "partial" | "stale" | "warning" | "unavailable" | "empty";
            /**
             * Warnings
             * @default []
             */
            warnings: string[];
        };
        /**
         * MarketDataset
         * @description One available symbol/timeframe/source data slice.
         */
        MarketDataset: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /** Bar Count */
            bar_count: number;
            /** First Ts */
            first_ts?: string | null;
            /** Last Ts */
            last_ts?: string | null;
            /** Source */
            source?: string | null;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
        };
        /**
         * MarketDatasetsResponse
         * @description Available market-data slices with bounded pagination.
         */
        MarketDatasetsResponse: {
            discovery?: components["schemas"]["MarketDataDiscovery"];
            /** Items */
            items: components["schemas"]["MarketDataset"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * NextDecisionArtifactReference
         * @description Exact canonical artifact identity cited by a human next decision.
         */
        NextDecisionArtifactReference: {
            /** Artifact Id */
            artifact_id: string;
            /** Artifact Type */
            artifact_type: string;
            /** Domain Owner */
            domain_owner: string;
            /** Metadata */
            metadata?: {
                [key: string]: unknown;
            };
            /** Uri */
            uri: string;
        };
        /**
         * NextResearchDecisionRecord
         * @description Stored human next-decision revision returned by Console.
         */
        NextResearchDecisionRecord: {
            /** Artifact Id */
            artifact_id: string;
            /**
             * Artifact Type
             * @constant
             */
            artifact_type: "research_next_decision";
            /** Assumptions */
            assumptions: {
                [key: string]: unknown;
            };
            data_ref: components["schemas"]["NextDecisionArtifactReference"];
            /**
             * Decided At
             * Format: date-time
             */
            decided_at: string;
            /** Decision Digest */
            decision_digest: string;
            /** Decision Id */
            decision_id: string;
            /** Implementation Refs */
            implementation_refs: components["schemas"]["NextDecisionArtifactReference"][];
            /** Limitations */
            limitations: string[];
            next_experiment?: components["schemas"]["BoundedNextExperimentContract"] | null;
            /** Operator */
            operator: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "reject" | "refine" | "continue";
            /** Rationale */
            rationale: string;
            /** Review Refs */
            review_refs: components["schemas"]["NextDecisionArtifactReference"][];
            /** Revision */
            revision: number;
            source_run_ref: components["schemas"]["NextDecisionArtifactReference"];
            /** Supersedes Artifact Id */
            supersedes_artifact_id?: string | null;
        };
        /**
         * NextResearchDecisionRequest
         * @description Human command for recording one immutable next-decision revision.
         */
        NextResearchDecisionRequest: {
            /** Assumptions */
            assumptions?: {
                [key: string]: unknown;
            };
            data_ref: components["schemas"]["NextDecisionArtifactReference"];
            /** Decision Id */
            decision_id: string;
            /** Implementation Refs */
            implementation_refs: components["schemas"]["NextDecisionArtifactReference"][];
            /** Limitations */
            limitations: string[];
            next_experiment?: components["schemas"]["BoundedNextExperimentContract"] | null;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "reject" | "refine" | "continue";
            /** Rationale */
            rationale: string;
            /** Review Refs */
            review_refs: components["schemas"]["NextDecisionArtifactReference"][];
            /**
             * Revision
             * @default 1
             */
            revision: number;
            source_run_ref: components["schemas"]["NextDecisionArtifactReference"];
            /** Supersedes Artifact Id */
            supersedes_artifact_id?: string | null;
        };
        /**
         * NextResearchDecisionsResponse
         * @description Bounded next-decision history for one reviewed run.
         */
        NextResearchDecisionsResponse: {
            /** Items */
            items: components["schemas"]["NextResearchDecisionRecord"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * PageInfo
         * @description Bounded pagination evidence returned with collection resources.
         */
        PageInfo: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /**
         * PaperDataFreshness
         * @description Aggregate market-data freshness with explicit missing/stale states.
         */
        PaperDataFreshness: {
            /**
             * Checked At
             * Format: date-time
             */
            checked_at: string;
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["PaperFreshnessItem"][];
            /**
             * Missing Count
             * @default 0
             */
            missing_count: number;
            /**
             * Stale Count
             * @default 0
             */
            stale_count: number;
            /**
             * Status
             * @enum {string}
             */
            status: "available" | "partial" | "stale" | "unavailable" | "out_of_scope";
        };
        /**
         * PaperFill
         * @description One persisted fill evidence row.
         */
        PaperFill: {
            /** Client Order Id */
            client_order_id?: string | null;
            /** Fee Amount */
            fee_amount?: number | null;
            /** Fill Price */
            fill_price?: number | null;
            /** Fill Qty */
            fill_qty?: number | null;
            /** Fill Ts */
            fill_ts?: string | null;
            /** Slippage Amount */
            slippage_amount?: number | null;
        };
        /**
         * PaperFills
         * @description Bounded fills projection with partial-history qualification.
         */
        PaperFills: {
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["PaperFill"][];
        };
        /**
         * PaperFreshnessItem
         * @description Freshness evidence for one observed market-data stream.
         */
        PaperFreshnessItem: {
            /** Age Seconds */
            age_seconds?: number | null;
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /** Latest Ts */
            latest_ts?: string | null;
            /** Stale */
            stale: boolean;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
        };
        /**
         * PaperHaltState
         * @description Operator halt state, or an explicit unavailable qualification.
         */
        PaperHaltState: {
            evidence: components["schemas"]["RuntimeEvidence"];
            /** Halted */
            halted?: boolean | null;
            /** Reason */
            reason?: string | null;
            /** Updated At */
            updated_at?: string | null;
        };
        /**
         * PaperIncident
         * @description Actionable issue derived from published runtime evidence.
         */
        PaperIncident: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Observed At */
            observed_at?: string | null;
            /**
             * Severity
             * @enum {string}
             */
            severity: "warning" | "error";
        };
        /**
         * PaperOpenOrder
         * @description One latest non-terminal local order lifecycle state.
         */
        PaperOpenOrder: {
            /** Broker Order Id */
            broker_order_id?: string | null;
            /** Client Order Id */
            client_order_id: string;
            /** Created At */
            created_at?: string | null;
            /** Order Type */
            order_type?: string | null;
            /** Qty */
            qty?: number | null;
            /** Rejection Reason */
            rejection_reason?: string | null;
            /** Side */
            side?: string | null;
            /** Status */
            status: string;
            /** Symbol */
            symbol?: string | null;
        };
        /**
         * PaperOperatorCommandRecord
         * @description Durable audit receipt for one authorized paper-runtime command.
         */
        PaperOperatorCommandRecord: {
            /** Accepted At */
            accepted_at?: string | null;
            /** Admission Id */
            admission_id: string;
            /**
             * Command
             * @enum {string}
             */
            command: "start" | "pause" | "stop" | "set_halt" | "clear_halt" | "reconcile";
            /** Command Id */
            command_id: string;
            /** Completed At */
            completed_at?: string | null;
            /** Idempotency Key */
            idempotency_key: string;
            /** Outcome Code */
            outcome_code?: string | null;
            /** Outcome Message */
            outcome_message?: string | null;
            /** Reason */
            reason?: string | null;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Requested By */
            requested_by: string;
            /** Scope Id */
            scope_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "requested" | "accepted" | "completed" | "rejected" | "ambiguous" | "failed";
        };
        /**
         * PaperOperatorCommandRequest
         * @description Human-requested paper-runtime command.
         *
         *     The admission identity is always supplied by the caller and checked against
         *     the server-owned paper scope before a command is persisted. Scope identity,
         *     broker configuration, and command outcome remain server-owned.
         */
        PaperOperatorCommandRequest: {
            /** Admission Id */
            admission_id: string;
            /**
             * Command
             * @enum {string}
             */
            command: "start" | "pause" | "stop" | "set_halt" | "clear_halt" | "reconcile";
            /** Idempotency Key */
            idempotency_key: string;
            /** Reason */
            reason?: string | null;
        };
        /**
         * PaperOperatorCommandsResponse
         * @description Bounded command-audit history for one paper scope.
         */
        PaperOperatorCommandsResponse: {
            /** Items */
            items: components["schemas"]["PaperOperatorCommandRecord"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * PaperOrders
         * @description Bounded open-order evidence and its freshness qualifier.
         */
        PaperOrders: {
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["PaperOpenOrder"][];
            /**
             * Stale Count
             * @default 0
             */
            stale_count: number;
        };
        /**
         * PaperPortfolio
         * @description Cash and position snapshot read from published runtime evidence.
         */
        PaperPortfolio: {
            /** Asof Ts */
            asof_ts?: string | null;
            /** Cash */
            cash?: number | null;
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Positions
             * @default []
             */
            positions: components["schemas"]["PaperPosition"][];
        };
        /**
         * PaperPosition
         * @description One broker-backed position snapshot.
         */
        PaperPosition: {
            /** Asof Ts */
            asof_ts?: string | null;
            /** Avg Price */
            avg_price?: number | null;
            /** Qty */
            qty: number;
            /** Symbol */
            symbol: string;
        };
        /**
         * PaperReconciliation
         * @description Broker reconciliation state without inventing an attempt record.
         */
        PaperReconciliation: {
            /**
             * Attempts
             * @default []
             */
            attempts: components["schemas"]["PaperReconciliationAttempt"][];
            evidence: components["schemas"]["RuntimeEvidence"];
            /** Last Attempt At */
            last_attempt_at?: string | null;
            /** Message */
            message?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "reconciled" | "required" | "failed" | "unavailable";
        };
        /**
         * PaperReconciliationAttempt
         * @description One bounded reconciliation attempt when a producer publishes it.
         */
        PaperReconciliationAttempt: {
            /** Attempt Id */
            attempt_id: string;
            /** Attempted At */
            attempted_at?: string | null;
            /** Message */
            message?: string | null;
            /** Status */
            status: string;
        };
        /**
         * PaperRiskOutcomes
         * @description Risk outcome counts for the latest paper runtime.
         */
        PaperRiskOutcomes: {
            /**
             * Approved Count
             * @default 0
             */
            approved_count: number;
            /**
             * Blocked Count
             * @default 0
             */
            blocked_count: number;
            /**
             * Evaluated Count
             * @default 0
             */
            evaluated_count: number;
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Rejected Count
             * @default 0
             */
            rejected_count: number;
            /**
             * Transformed Count
             * @default 0
             */
            transformed_count: number;
        };
        /**
         * PaperRuntimeHealth
         * @description Derived health classification with reasons and evidence freshness.
         */
        PaperRuntimeHealth: {
            /**
             * Checked At
             * Format: date-time
             */
            checked_at: string;
            evidence: components["schemas"]["RuntimeEvidence"];
            /**
             * Reasons
             * @default []
             */
            reasons: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "healthy" | "degraded" | "unhealthy" | "unavailable";
        };
        /**
         * PaperRuntimeOperations
         * @description Read-only paper operations projection for the Console workspace.
         */
        PaperRuntimeOperations: {
            broker_account_binding: components["schemas"]["BrokerAccountBinding"];
            /** Broker Account Display Label */
            broker_account_display_label?: string | null;
            /**
             * Broker Identity Verified
             * @default false
             */
            broker_identity_verified: boolean;
            data_freshness: components["schemas"]["PaperDataFreshness"];
            fills: components["schemas"]["PaperFills"];
            /**
             * Generated At
             * Format: date-time
             */
            generated_at: string;
            halt: components["schemas"]["PaperHaltState"];
            health: components["schemas"]["PaperRuntimeHealth"];
            /**
             * Incidents
             * @default []
             */
            incidents: components["schemas"]["PaperIncident"][];
            open_orders: components["schemas"]["PaperOrders"];
            portfolio: components["schemas"]["PaperPortfolio"];
            reconciliation: components["schemas"]["PaperReconciliation"];
            risk: components["schemas"]["PaperRiskOutcomes"];
            /** Scope Id */
            scope_id: string;
            session: components["schemas"]["PaperRuntimeSession"];
        };
        /**
         * PaperRuntimeSession
         * @description Latest paper session identity and lifecycle evidence.
         */
        PaperRuntimeSession: {
            /** Error Message */
            error_message?: string | null;
            evidence: components["schemas"]["RuntimeEvidence"];
            /** Finished At */
            finished_at?: string | null;
            /** Mode */
            mode?: string | null;
            /** Session Id */
            session_id?: string | null;
            /** Started At */
            started_at?: string | null;
            /** Status */
            status?: string | null;
            /** Strategy Id */
            strategy_id?: string | null;
            /**
             * Symbols
             * @default []
             */
            symbols: string[];
            /** Timeframe */
            timeframe?: string | null;
        };
        /**
         * PreflightIssue
         * @description Actionable field-level preflight failure or warning.
         */
        PreflightIssue: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Path */
            path: string;
            /**
             * Severity
             * @enum {string}
             */
            severity: "error" | "warning";
        };
        /**
         * ReadinessResponse
         * @description Database readiness without trading-health or IAM claims.
         */
        ReadinessResponse: {
            /** Contract Version */
            contract_version?: number | null;
            /**
             * Issues
             * @default []
             */
            issues: string[];
            /** Scope Id */
            scope_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "unavailable";
        };
        /**
         * ResourceRecord
         * @description Typed identity plus producer fields for a run-detail projection.
         */
        ResourceRecord: {
            /** Experiment Id */
            experiment_id?: string | null;
            /** Experiment Run Id */
            experiment_run_id?: string | null;
            /** Run Id */
            run_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /**
         * ReviewEvidence
         * @description One producer-owned review artifact or an explicit missing-state receipt.
         *
         *     The Console presents producer claims and limitations; it never calculates a
         *     statistical verdict or promotes optimisation output to independent evidence.
         */
        ReviewEvidence: {
            /** Artifact Id */
            artifact_id?: string | null;
            /** Artifact Type */
            artifact_type?: string | null;
            /**
             * Blockers
             * @default []
             */
            blockers: string[];
            /** Claim Scope */
            claim_scope?: {
                [key: string]: unknown;
            };
            /**
             * Data Roles
             * @default []
             */
            data_roles: ({
                [key: string]: unknown;
            } | string)[];
            /** Domain Owner */
            domain_owner?: string | null;
            /**
             * Evidence Kind
             * @enum {string}
             */
            evidence_kind: "evaluation" | "multiple_testing" | "adversarial";
            /**
             * Independent Confirmation
             * @default false
             */
            independent_confirmation: boolean;
            /**
             * Limitations
             * @default []
             */
            limitations: string[];
            /** Origin Kind */
            origin_kind?: ("independent_review" | "optimization" | "diagnostic") | null;
            /** Producer Tool */
            producer_tool?: string | null;
            /** Reason */
            reason: string;
            /** Schema Version */
            schema_version?: string | null;
            /** Source Hash */
            source_hash?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "available" | "missing" | "incompatible" | "blocked";
        };
        /**
         * RiskCompositionEntry
         * @description One ordered manager in the producer-published risk composition.
         */
        RiskCompositionEntry: {
            /** Catalogue Version */
            catalogue_version: string;
            /** Composition Fingerprint */
            composition_fingerprint: string;
            /** Manager Id */
            manager_id: string;
            /** Manager Position */
            manager_position: number;
            /** Manager Type */
            manager_type: string;
            /** Parameters */
            parameters?: {
                [key: string]: unknown;
            };
            /** Run Id */
            run_id: string;
            /** Session Id */
            session_id?: string | null;
        };
        /**
         * RiskDecision
         * @description One ordered per-manager risk decision with transformation evidence.
         */
        RiskDecision: {
            /** After Order */
            after_order?: {
                [key: string]: unknown;
            } | null;
            /** After Qty */
            after_qty?: number | null;
            /** Before Order */
            before_order?: {
                [key: string]: unknown;
            };
            /** Before Qty */
            before_qty?: number | null;
            /** Client Order Id */
            client_order_id?: string | null;
            /** Composition Fingerprint */
            composition_fingerprint: string;
            /** Cycle Id */
            cycle_id: string;
            /**
             * Decision Ts
             * Format: date-time
             */
            decision_ts: string;
            /** Manager Id */
            manager_id: string;
            /** Manager Position */
            manager_position: number;
            /** Manager Type */
            manager_type: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "approved" | "transformed" | "rejected";
            /** Reason Code */
            reason_code: string;
            /** Risk Decision Id */
            risk_decision_id: string;
            /** Run Id */
            run_id: string;
            /** Session Id */
            session_id?: string | null;
        };
        /**
         * RiskDecisionsResponse
         * @description A bounded, filterable page of manager decisions for one run.
         */
        RiskDecisionsResponse: {
            /** Items */
            items: components["schemas"]["RiskDecision"][];
            page: components["schemas"]["PageInfo"];
        };
        /**
         * RiskSummary
         * @description Bounded risk evidence counts for one run.
         */
        RiskSummary: {
            /** Approved Count */
            approved_count: number;
            /** Blocked Count */
            blocked_count: number;
            /** Composition Fingerprint */
            composition_fingerprint?: string | null;
            /** Evaluated Count */
            evaluated_count: number;
            /** Rejected Count */
            rejected_count: number;
            /**
             * Risk Evidence Status
             * @enum {string}
             */
            risk_evidence_status: "recorded" | "unavailable";
            /** Run Id */
            run_id: string;
            /** Transformed Count */
            transformed_count: number;
        };
        /**
         * RunDetail
         * @description Published evidence for one backtest run, grouped by projection.
         */
        RunDetail: {
            assumptions?: components["schemas"]["ResourceRecord"] | null;
            /**
             * Comparison Curves
             * @default []
             */
            comparison_curves: components["schemas"]["ResourceRecord"][];
            comparison_summary?: components["schemas"]["ResourceRecord"] | null;
            /**
             * Equity Curve
             * @default []
             */
            equity_curve: components["schemas"]["ResourceRecord"][];
            evidence_coverage?: components["schemas"]["ResourceRecord"] | null;
            exposure?: components["schemas"]["ResourceRecord"] | null;
            /**
             * Fills
             * @default []
             */
            fills: {
                [key: string]: unknown;
            }[];
            /**
             * Indicator Series
             * @default []
             */
            indicator_series: components["schemas"]["IndicatorSeriesPoint"][];
            /**
             * Orders
             * @default []
             */
            orders: {
                [key: string]: unknown;
            }[];
            performance?: components["schemas"]["ResourceRecord"] | null;
            /**
             * Positions
             * @default []
             */
            positions: components["schemas"]["ResourceRecord"][];
            /**
             * Provenance
             * @default []
             */
            provenance: components["schemas"]["ResourceRecord"][];
            /**
             * Review Evidence
             * @default []
             */
            review_evidence: components["schemas"]["ReviewEvidence"][];
            /**
             * Risk Composition
             * @default []
             */
            risk_composition: components["schemas"]["RiskCompositionEntry"][];
            /**
             * Risk Decisions
             * @default []
             */
            risk_decisions: components["schemas"]["RiskDecision"][];
            risk_summary?: components["schemas"]["RiskSummary"] | null;
            run: components["schemas"]["ExperimentRunSummary"];
            scope?: components["schemas"]["ResourceRecord"] | null;
            /**
             * Signal Markers
             * @default []
             */
            signal_markers: components["schemas"]["SignalMarker"][];
            /**
             * Signals
             * @default []
             */
            signals: {
                [key: string]: unknown;
            }[];
            /**
             * Trades
             * @default []
             */
            trades: components["schemas"]["ResourceRecord"][];
            /**
             * Warnings
             * @default []
             */
            warnings: components["schemas"]["ResourceRecord"][];
        };
        /**
         * RuntimeEvidence
         * @description Evidence qualifier attached to every paper-runtime read model.
         */
        RuntimeEvidence: {
            /** Observed At */
            observed_at?: string | null;
            /** Reason */
            reason?: string | null;
            /** Source */
            source: string;
            /**
             * Status
             * @enum {string}
             */
            status: "available" | "partial" | "stale" | "unavailable" | "out_of_scope";
        };
        /**
         * SavedComparisonView
         * @description Durable definition with server-owned identity and revision.
         */
        SavedComparisonView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            definition: components["schemas"]["ComparisonViewDefinition"];
            /**
             * Definition Version
             * @default 1
             * @constant
             */
            definition_version: 1;
            /** Experiment Id */
            experiment_id: string;
            /** Revision */
            revision: number;
            /** Scope Id */
            scope_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * View Id
             * Format: uuid
             */
            view_id: string;
        };
        /**
         * SavedDataScope
         * @description Immutable scope identity plus revalidated evidence state.
         */
        SavedDataScope: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by: string;
            /**
             * End
             * Format: date-time
             */
            end: string;
            /** Evidence Reason */
            evidence_reason?: string | null;
            evidence_status: components["schemas"]["DataScopeEvidenceStatus"];
            /** Fingerprint */
            fingerprint: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Interval */
            interval: string;
            /** Manifest Artifact Id */
            manifest_artifact_id: string;
            /** Name */
            name: string;
            /** Quality Artifact Id */
            quality_artifact_id: string;
            /** Research Role */
            research_role: string;
            /**
             * Revision
             * @default 1
             * @constant
             */
            revision: 1;
            /**
             * Saved Scope Id
             * Format: uuid
             */
            saved_scope_id: string;
            /** Scope Id */
            scope_id: string;
            source_policy: components["schemas"]["DataScopeSourcePolicy"];
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
            /** Universe */
            universe?: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * SavedDataScopeCreate
         * @description Request to persist one exact Data evidence handoff.
         */
        SavedDataScopeCreate: {
            /**
             * Asset Class
             * @enum {string}
             */
            asset_class: "stock" | "crypto";
            /** Created By */
            created_by: string;
            /**
             * End
             * Format: date-time
             */
            end: string;
            /** Evidence Reason */
            evidence_reason?: string | null;
            /** @default active */
            evidence_status: components["schemas"]["DataScopeEvidenceStatus"];
            /** Idempotency Key */
            idempotency_key: string;
            /** Interval */
            interval: string;
            /** Manifest Artifact Id */
            manifest_artifact_id: string;
            /** Name */
            name: string;
            /** Quality Artifact Id */
            quality_artifact_id: string;
            /** Research Role */
            research_role: string;
            source_policy: components["schemas"]["DataScopeSourcePolicy"];
            /**
             * Start
             * Format: date-time
             */
            start: string;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
            /** Universe */
            universe?: string | null;
        };
        /**
         * SavedDataScopesResponse
         * @description Bounded page of saved exact data scopes.
         */
        SavedDataScopesResponse: {
            /** Items */
            items: components["schemas"]["SavedDataScope"][];
            page: components["schemas"]["DataScopePageInfo"];
        };
        /**
         * SignalMarker
         * @description One signal event bound to its decision-cycle timestamp.
         */
        SignalMarker: {
            /** Cycle Id */
            cycle_id?: string | null;
            /** Event Ts */
            event_ts?: string | null;
            /** Generated At */
            generated_at?: string | null;
            /** Mapper Id */
            mapper_id?: string | null;
            /** Run Id */
            run_id: string;
            /** Session Id */
            session_id?: string | null;
            /** Signal Event Id */
            signal_event_id: string;
            /** Signal Name */
            signal_name: string;
            /** Signal Value */
            signal_value?: number | null;
            /** Symbol */
            symbol: string;
            /** Target Qty */
            target_qty?: number | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    backtest_catalogue_api_backtests_catalogue_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestCatalogueResponse"];
                };
            };
        };
    };
    list_backtest_definitions_api_backtests_definitions_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestDefinitionsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    create_backtest_definition_api_backtests_definitions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BacktestPreflightRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestDefinitionRevision"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestPreflightResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_backtest_definition_api_backtests_definitions__definition_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                definition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestDefinitionRevision"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    create_backtest_definition_revision_api_backtests_definitions__definition_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                definition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BacktestPreflightRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestDefinitionRevision"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestPreflightResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    list_backtest_executions_api_backtests_executions_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestExecutionsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    submit_backtest_execution_api_backtests_executions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BacktestExecutionSubmit"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestExecutionRecord"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_backtest_execution_api_backtests_executions__execution_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestExecutionRecord"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    backtest_preflight_api_backtests_preflight_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BacktestPreflightRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BacktestPreflightResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_context: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConsoleScope"];
                };
            };
        };
    };
    list_saved_data_scopes_api_data_scopes_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDataScopesResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    create_saved_data_scope_api_data_scopes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SavedDataScopeCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDataScope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_saved_data_scope_api_data_scopes__saved_scope_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                saved_scope_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDataScope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    revalidate_saved_data_scope_api_data_scopes__saved_scope_id__revalidate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                saved_scope_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDataScope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    experiments_api_experiments_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExperimentsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    list_comparison_views_api_experiments__experiment_id__comparison_views_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                experiment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonViewsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    create_comparison_view_api_experiments__experiment_id__comparison_views_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                experiment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonViewDefinition"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonViewDetail"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    preview_comparison_view_api_experiments__experiment_id__comparison_views_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                experiment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonViewDefinition"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonEvaluation"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_comparison_view_api_experiments__experiment_id__comparison_views__view_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                experiment_id: string;
                view_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonViewDetail"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    replace_comparison_view_api_experiments__experiment_id__comparison_views__view_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                experiment_id: string;
                view_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonViewUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonViewDetail"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    experiment_runs_api_experiments__experiment_id__runs_get: {
        parameters: {
            query?: {
                compatible_with_run_id?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                experiment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExperimentRunsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    market_data_bars_api_market_data_bars_get: {
        parameters: {
            query: {
                symbol: string;
                asset_class?: "stock" | "crypto";
                timeframe?: string;
                source?: string | null;
                start?: string | null;
                end?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BarsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    market_datasets_api_market_data_datasets_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketDatasetsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    market_data_evidence_api_market_data_evidence_get: {
        parameters: {
            query: {
                symbols: string;
                asset_class?: "stock" | "crypto";
                timeframe?: string;
                interval?: string | null;
                bar_type?: string;
                provider?: string | null;
                source_policy?: string | null;
                start?: string | null;
                end?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketDataEvidenceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    list_paper_operator_commands_api_paper_commands_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaperOperatorCommandsResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    submit_paper_operator_command_api_paper_commands_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PaperOperatorCommandRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaperOperatorCommandRecord"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_paper_operator_command_api_paper_commands__command_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                command_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaperOperatorCommandRecord"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    paper_runtime_api_paper_runtime_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaperRuntimeOperations"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    run_detail_api_runs__run_id__get: {
        parameters: {
            query?: {
                section_limit?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    list_next_research_decisions_api_runs__run_id__next_decisions_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NextResearchDecisionsResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    record_next_research_decision_api_runs__run_id__next_decisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NextResearchDecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NextResearchDecisionRecord"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    get_next_research_decision_api_runs__run_id__next_decisions__decision_id__get: {
        parameters: {
            query?: {
                revision?: number | null;
            };
            header?: never;
            path: {
                run_id: string;
                decision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NextResearchDecisionRecord"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    risk_decisions_api_runs__run_id__risk_decisions_get: {
        parameters: {
            query?: {
                manager_id?: string | null;
                outcome?: ("approved" | "transformed" | "rejected") | null;
                cycle_id?: string | null;
                client_order_id?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RiskDecisionsResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    liveness_health_live_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LivenessResponse"];
                };
            };
        };
    };
    readiness_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadinessResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadinessResponse"];
                };
            };
        };
    };
}
