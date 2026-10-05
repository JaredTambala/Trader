"""Public value contracts for the Trader Console API."""

from __future__ import annotations

from enum import StrEnum
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .data_scope_contracts import BacktestDataScopeHandoff

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MARKET_DATA_BARS_PER_PAGE = 50_000


class ConsoleEnvironment(StrEnum):
    """Execution environment represented by one isolated Console scope."""

    PAPER = "paper"
    BACKTEST = "backtest"
    SYNTHETIC_DEMO = "synthetic_demo"


class BrokerAccountBinding(StrEnum):
    """Evidence level for the scope's configured brokerage binding."""

    CONFIGURED = "configured"
    NOT_APPLICABLE = "not_applicable"


class TraderPrincipal(BaseModel):
    """Authenticated Trader-platform identity supplied by a future gateway.

    This is deliberately separate from brokerage-account identity and does not
    imply a Trader-owned user table.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1, max_length=200)


PaperOperatorCommandName = Literal[
    "start",
    "pause",
    "stop",
    "set_halt",
    "clear_halt",
    "reconcile",
]
PaperOperatorCommandStatus = Literal[
    "requested",
    "accepted",
    "completed",
    "rejected",
    "ambiguous",
    "failed",
]


class PaperOperatorCommandRequest(BaseModel):
    """Human-requested paper-runtime command.

    The admission identity is always supplied by the caller and checked against
    the server-owned paper scope before a command is persisted. Scope identity,
    broker configuration, and command outcome remain server-owned.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: PaperOperatorCommandName
    admission_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)


class PaperOperatorCommandRecord(BaseModel):
    """Durable audit receipt for one authorized paper-runtime command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str
    scope_id: str
    command: PaperOperatorCommandName
    admission_id: str
    idempotency_key: str
    requested_by: str
    status: PaperOperatorCommandStatus
    reason: str | None = None
    outcome_code: str | None = None
    outcome_message: str | None = None
    requested_at: datetime
    accepted_at: datetime | None = None
    completed_at: datetime | None = None


class PaperOperatorCommandsResponse(BaseModel):
    """Bounded command-audit history for one paper scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[PaperOperatorCommandRecord, ...]
    page: PageInfo


class ConsoleScope(BaseModel):
    """Safe public description of one server-configured API scope.

    The database URL and brokerage provider reference are deliberately absent.
    One API process serves one scope backed by one isolated database.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    environment: ConsoleEnvironment
    data_source_kind: Literal["postgresql"] = "postgresql"
    isolation_kind: Literal["isolated_database"] = "isolated_database"
    broker_account_display_label: str | None = Field(default=None, max_length=200)
    broker_account_binding: BrokerAccountBinding
    presentation_timezone: str = "UTC"

    @field_validator("presentation_timezone")
    @classmethod
    def validate_presentation_timezone(cls, value: str) -> str:
        """Require an IANA timezone without retaining a mutable timezone object."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("presentation_timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_broker_account_binding(self) -> ConsoleScope:
        """Keep paper brokerage bindings distinct from non-broker scopes."""
        if (
            self.environment is ConsoleEnvironment.PAPER
            and self.broker_account_binding is not BrokerAccountBinding.CONFIGURED
        ):
            raise ValueError("paper scopes require a configured broker-account binding")
        if (
            self.environment is not ConsoleEnvironment.PAPER
            and self.broker_account_binding is not BrokerAccountBinding.NOT_APPLICABLE
        ):
            raise ValueError(
                "backtest and synthetic-demo scopes do not have a broker-account binding"
            )
        return self


class LivenessResponse(BaseModel):
    """Process-liveness response that makes no database or trading claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["alive"] = "alive"
    service: Literal["trader-console-api"] = "trader-console-api"


class ReadinessResponse(BaseModel):
    """Database readiness without trading-health or IAM claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "unavailable"]
    scope_id: str
    contract_version: int | None = None
    issues: tuple[str, ...] = ()


class ApiError(BaseModel):
    """Stable error envelope for resource failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class CatalogueParameter(BaseModel):
    """Public typed parameter metadata for one allowlisted profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    type: Literal["integer", "number", "boolean", "string"]
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    description: str | None = None


class CatalogueProfile(BaseModel):
    """One discoverable strategy or risk profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["strategy", "risk"]
    profile_id: str
    version: str
    name: str
    description: str
    parameters: tuple[CatalogueParameter, ...] = ()
    supported_asset_classes: tuple[str, ...] = ()
    supported_timeframes: tuple[str, ...] = ()
    lookback_bars: int = 0
    evidence_requirements: tuple[str, ...] = ()
    manager_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


class ImplementationValidationReport(BaseModel):
    """Immutable admission evidence for one executable implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str = Field(min_length=1, max_length=200)
    implementation_version_id: str = Field(min_length=1, max_length=200)
    implementation_kind: Literal["strategy", "risk_manager"]
    source_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    status: Literal["passed", "blocked"]
    valid: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> ImplementationValidationReport:
        """Keep status and validity aligned with the research report."""
        if self.valid is not (self.status == "passed"):
            raise ValueError("validation report valid must match status")
        return self


class ImplementationLineage(BaseModel):
    """Exact admitted implementation and specification lineage for authoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=100)
    implementation_version_id: str = Field(min_length=1, max_length=200)
    implementation_kind: Literal["strategy", "risk_manager"]
    implementation_name: str = Field(min_length=1, max_length=200)
    implementation_version: str = Field(min_length=1, max_length=100)
    source_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    implementation_validation_id: str = Field(min_length=1, max_length=200)
    specification_id: str = Field(min_length=1, max_length=200)
    decision: Literal["exact_reuse", "adaptation", "new_authorship"]
    validation_report: ImplementationValidationReport

    @model_validator(mode="after")
    def validate_report_lineage(self) -> ImplementationLineage:
        """Reject any payload whose nested report is for a different source."""
        report = self.validation_report
        if report.validation_id != self.implementation_validation_id:
            raise ValueError("implementation validation ID does not match validation report")
        if report.implementation_version_id != self.implementation_version_id:
            raise ValueError("implementation version ID does not match validation report")
        if report.implementation_kind != self.implementation_kind:
            raise ValueError("implementation kind does not match validation report")
        if report.source_hash != self.source_hash:
            raise ValueError("implementation source hash does not match validation report")
        return self


class BacktestCatalogueResponse(BaseModel):
    """Versioned allowlisted strategy and risk catalogue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_version: str
    strategy_profiles: tuple[CatalogueProfile, ...]
    risk_profiles: tuple[CatalogueProfile, ...]


class InitialPositionInput(BaseModel):
    """Optional initial position included in a typed backtest definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=32)
    qty: float
    avg_price: float | None = Field(default=None, ge=0)


class BacktestAssumptions(BaseModel):
    """Bounded execution and missing-data assumptions for preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_model: Literal["full_fill", "next_bar"] = "full_fill"
    latency_ms: int = Field(default=0, ge=0, le=60_000)
    fee_fixed_per_order: float = Field(default=0.0, ge=0, le=1_000_000)
    fee_bps: float = Field(default=0.0, ge=0, le=10_000)
    fee_minimum: float = Field(default=0.0, ge=0, le=1_000_000)
    slippage_bps: float = Field(default=0.0, ge=0, le=10_000)
    allow_latest_prior_bar: bool = True
    allow_price_carry_forward: bool = True


class BacktestResourceLimits(BaseModel):
    """Explicit bounded resources accepted by a backtest definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_cycles: int = Field(default=1_000_000, ge=1, le=10_000_000)
    max_bars: int = Field(default=5_000_000, ge=1, le=50_000_000)
    timeout_seconds: int = Field(default=3_600, ge=1, le=86_400)


class BacktestDefinition(BaseModel):
    """Normalized, content-addressed input to one future backtest execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1, max_length=120)
    strategy_profile_id: str = Field(min_length=1, max_length=100)
    strategy_catalogue_version: str = Field(min_length=1, max_length=50)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    strategy_implementation_lineage: ImplementationLineage
    risk_profile_id: str = Field(min_length=1, max_length=100)
    risk_catalogue_version: str = Field(min_length=1, max_length=50)
    risk_parameters: dict[str, Any] = Field(default_factory=dict)
    risk_implementation_lineage: ImplementationLineage
    asset_class: Literal["stock", "crypto"]
    symbols: tuple[str, ...] = Field(min_length=1, max_length=50)
    timeframe: str = Field(min_length=1, max_length=32)
    start: datetime
    end: datetime
    initial_cash: float = Field(ge=0, le=1_000_000_000_000)
    initial_positions: tuple[InitialPositionInput, ...] = ()
    assumptions: BacktestAssumptions = Field(default_factory=BacktestAssumptions)
    benchmark_id: Literal["buy_hold", "none"] = "buy_hold"
    resource_limits: BacktestResourceLimits = Field(default_factory=BacktestResourceLimits)
    data_scope: BacktestDataScopeHandoff


class BacktestDefinitionRevision(BaseModel):
    """Immutable Console-owned definition revision returned after persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition_id: str
    scope_id: str
    definition_version: Literal[1] = 1
    revision: int = Field(ge=1)
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    definition: BacktestDefinition
    created_at: datetime
    updated_at: datetime


class BacktestDefinitionsResponse(BaseModel):
    """Bounded page of the latest immutable revision for each definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[BacktestDefinitionRevision, ...]
    page: PageInfo


class BacktestExecutionSubmit(BaseModel):
    """Idempotent request to enqueue one persisted definition revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=200)


class BacktestExecutionRecord(BaseModel):
    """Durable execution command state linked to one immutable definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_id: str
    scope_id: str
    definition_id: str
    definition_revision: int = Field(ge=1)
    definition_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    status: Literal[
        "queued", "running", "completed", "partial", "failed", "reconciliation_required"
    ]
    attempt: int = Field(ge=0)
    worker_id: str | None = None
    run_id: str | None = None
    processed_cycles: int = Field(ge=0)
    total_cycles: int | None = Field(default=None, ge=0)
    last_decision_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    warning_summary: tuple[str, ...] = ()
    terminal_error_code: str | None = None
    terminal_error_message: str | None = None


class BacktestExecutionsResponse(BaseModel):
    """Bounded page of durable execution command records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[BacktestExecutionRecord, ...]
    page: PageInfo


class PreflightIssue(BaseModel):
    """Actionable field-level preflight failure or warning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["error", "warning"]
    code: str
    path: str
    message: str


class BacktestCoverageCheck(BaseModel):
    """Read-only data coverage evidence returned by preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    asset_class: Literal["stock", "crypto"]
    timeframe: str
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    bar_count: int = 0
    required_start: datetime
    requested_end: datetime
    warmup_bars: int
    available: bool
    warmup_satisfied: bool


class BacktestPreflightRequest(BaseModel):
    """User-authored draft validated before persistence or execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(default="Untitled backtest", min_length=1, max_length=120)
    strategy_profile_id: str = Field(min_length=1, max_length=100)
    strategy_catalogue_version: str | None = Field(default=None, max_length=50)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    strategy_implementation_lineage: ImplementationLineage | None = None
    risk_profile_id: str = Field(default="noop", min_length=1, max_length=100)
    risk_catalogue_version: str | None = Field(default=None, max_length=50)
    risk_parameters: dict[str, Any] = Field(default_factory=dict)
    risk_implementation_lineage: ImplementationLineage | None = None
    asset_class: str
    symbols: tuple[str, ...] = Field(min_length=1, max_length=50)
    timeframe: str
    start: datetime
    end: datetime
    initial_cash: float = Field(default=100_000.0, ge=0, le=1_000_000_000_000)
    initial_positions: tuple[InitialPositionInput, ...] = ()
    assumptions: BacktestAssumptions = Field(default_factory=BacktestAssumptions)
    benchmark_id: Literal["buy_hold", "none"] = "buy_hold"
    resource_limits: BacktestResourceLimits = Field(default_factory=BacktestResourceLimits)
    data_scope: BacktestDataScopeHandoff


class BacktestPreflightResponse(BaseModel):
    """Normalized preflight result with no producer or command side effects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    catalogue_version: str
    definition_fingerprint: str | None = None
    normalized_definition: BacktestDefinition | None = None
    coverage: tuple[BacktestCoverageCheck, ...] = ()
    issues: tuple[PreflightIssue, ...] = ()


class PageInfo(BaseModel):
    """Bounded pagination evidence returned with collection resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(ge=1, le=MAX_MARKET_DATA_BARS_PER_PAGE)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    has_more: bool


class BarPoint(BaseModel):
    """One producer-owned OHLCV observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    timeframe: str
    ts: datetime
    ingested_at: datetime | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    trade_count: int | None = None
    vwap: float | None = None
    source: str | None = None


class BarsResponse(BaseModel):
    """A page of OHLCV observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[BarPoint, ...]
    page: PageInfo


class MarketDataset(BaseModel):
    """One available symbol/timeframe/source data slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_class: Literal["stock", "crypto"]
    symbol: str
    timeframe: str
    source: str | None = None
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    bar_count: int


class MarketDataDiscovery(BaseModel):
    """Explicit catalogue and provider-load capability for the dataset view.

    A Console read model can prove which stored slices are visible, but that
    evidence is separate from a provider catalogue and from permission to run a
    bounded load. Keeping the states together in a typed object prevents the UI
    from treating one visible symbol as a complete provider universe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    catalogue_completeness: Literal["complete", "partial", "stale", "unavailable"]
    catalogue_freshness: Literal["fresh", "stale", "unknown"]
    can_discover: bool
    can_load: bool
    load_capability: Literal["load_capable", "discover_only", "unavailable"]
    reason: str | None = None


class MarketDatasetsResponse(BaseModel):
    """Available market-data slices with bounded pagination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[MarketDataset, ...]
    page: PageInfo
    discovery: MarketDataDiscovery = Field(
        default_factory=lambda: MarketDataDiscovery(
            provider="unknown",
            catalogue_completeness="unavailable",
            catalogue_freshness="unknown",
            can_discover=False,
            can_load=False,
            load_capability="unavailable",
            reason="No discovery evidence was supplied.",
        )
    )


class DataEvidenceScope(BaseModel):
    """Exact bounded scope used to resolve Data-owned evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_class: Literal["stock", "crypto"]
    symbols: tuple[str, ...]
    timeframe: str
    interval: str
    bar_type: str
    start: datetime
    end: datetime
    provider: str | None = None
    source_policy: str | None = None


class DataEvidenceArtifact(BaseModel):
    """Bounded public reference and payload projection for one Data artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    uri: str
    status: str | None = None
    schema_version: str
    source_hash: str | None = None
    created_at: datetime
    updated_at: datetime
    payload: dict[str, Any]


class MarketDataEvidenceResponse(BaseModel):
    """Qualified Data manifest and quality evidence for one exact scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: DataEvidenceScope
    state: Literal["complete", "partial", "stale", "warning", "unavailable", "empty"]
    evidence_reason: str
    manifest: DataEvidenceArtifact | None = None
    quality: DataEvidenceArtifact | None = None
    provider: str | None = None
    source_policy: str | None = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    findings: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


class ExperimentSummary(BaseModel):
    """An experiment grouping discovered from its published run projections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str
    run_count: int
    latest_created_at: datetime | None = None
    statuses: tuple[str, ...] = ()
    metadata_available: bool = False


class ExperimentsResponse(BaseModel):
    """A page of experiment groups."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ExperimentSummary, ...]
    page: PageInfo


class ExperimentRunSummary(BaseModel):
    """A backtest run and its current comparison eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_run_id: str
    experiment_id: str
    run_id: str
    session_id: str | None = None
    status: str
    mode: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    strategy_version: str | None = None
    symbols: tuple[str, ...] = ()
    asset_class: str | None = None
    timeframe: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    scope_fingerprint: str | None = None
    data_scope_id: str | None = None
    benchmark_id: str | None = None
    variant_fingerprint: str | None = None
    variant_strategy_id: str | None = None
    variant_strategy_version: str | None = None
    comparison_projection_available: bool = False
    comparison_eligible: bool = False
    comparison_exclusion_reason: str | None = None


class ExperimentRunsResponse(BaseModel):
    """A page of runs belonging to one experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ExperimentRunSummary, ...]
    page: PageInfo


class ResourceRecord(BaseModel):
    """Typed identity plus producer fields for a run-detail projection."""

    model_config = ConfigDict(extra="allow", frozen=True)

    experiment_run_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None


class IndicatorSeriesPoint(BaseModel):
    """One persisted indicator observation with producer-owned display semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    session_id: str | None = None
    cycle_id: str | None = None
    symbol: str
    indicator_name: str
    series_id: str
    series_label: str
    pane: str
    scale_group: str
    unit: str
    series_kind: str
    value: float | None = None
    bar_ts: datetime
    signal_name: str | None = None
    signal_event_id: str | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    variant_fingerprint: str | None = None
    parameters_fingerprint: str | None = None
    data_scope_id: str | None = None


class SignalMarker(BaseModel):
    """One signal event bound to its decision-cycle timestamp."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_event_id: str
    run_id: str
    session_id: str | None = None
    cycle_id: str | None = None
    symbol: str
    signal_name: str
    signal_value: float | None = None
    target_qty: float | None = None
    event_ts: datetime | None = None
    generated_at: datetime | None = None
    mapper_id: str | None = None


class RiskCompositionEntry(BaseModel):
    """One ordered manager in the producer-published risk composition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    session_id: str | None = None
    catalogue_version: str
    composition_fingerprint: str
    manager_position: int
    manager_id: str
    manager_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RiskSummary(BaseModel):
    """Bounded risk evidence counts for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    composition_fingerprint: str | None = None
    risk_evidence_status: Literal["recorded", "unavailable"]
    evaluated_count: int
    approved_count: int
    transformed_count: int
    rejected_count: int
    blocked_count: int


class RiskDecision(BaseModel):
    """One ordered per-manager risk decision with transformation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_decision_id: str
    composition_fingerprint: str
    run_id: str
    session_id: str | None = None
    cycle_id: str
    client_order_id: str | None = None
    decision_ts: datetime
    manager_id: str
    manager_type: str
    manager_position: int
    outcome: Literal["approved", "transformed", "rejected"]
    reason_code: str
    before_qty: float | None = None
    after_qty: float | None = None
    before_order: dict[str, Any] = Field(default_factory=dict)
    after_order: dict[str, Any] | None = None


class RiskDecisionsResponse(BaseModel):
    """A bounded, filterable page of manager decisions for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[RiskDecision, ...]
    page: PageInfo


class ReviewEvidence(BaseModel):
    """One producer-owned review artifact or an explicit missing-state receipt.

    The Console presents producer claims and limitations; it never calculates a
    statistical verdict or promotes optimisation output to independent evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_kind: Literal["evaluation", "multiple_testing", "adversarial"]
    artifact_type: str | None = None
    artifact_id: str | None = None
    status: Literal["available", "missing", "incompatible", "blocked"]
    reason: str
    domain_owner: str | None = None
    producer_tool: str | None = None
    schema_version: str | None = None
    source_hash: str | None = None
    claim_scope: dict[str, Any] = Field(default_factory=dict)
    data_roles: tuple[dict[str, Any] | str, ...] = ()
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    independent_confirmation: bool = False
    origin_kind: Literal["independent_review", "optimization", "diagnostic"] | None = None


class RunDetail(BaseModel):
    """Published evidence for one backtest run, grouped by projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run: ExperimentRunSummary
    performance: ResourceRecord | None = None
    comparison_summary: ResourceRecord | None = None
    exposure: ResourceRecord | None = None
    scope: ResourceRecord | None = None
    assumptions: ResourceRecord | None = None
    evidence_coverage: ResourceRecord | None = None
    equity_curve: tuple[ResourceRecord, ...] = ()
    comparison_curves: tuple[ResourceRecord, ...] = ()
    trades: tuple[ResourceRecord, ...] = ()
    positions: tuple[ResourceRecord, ...] = ()
    warnings: tuple[ResourceRecord, ...] = ()
    provenance: tuple[ResourceRecord, ...] = ()
    indicator_series: tuple[IndicatorSeriesPoint, ...] = ()
    signal_markers: tuple[SignalMarker, ...] = ()
    risk_composition: tuple[RiskCompositionEntry, ...] = ()
    risk_summary: RiskSummary | None = None
    risk_decisions: tuple[RiskDecision, ...] = ()
    review_evidence: tuple[ReviewEvidence, ...] = ()
    signals: tuple[dict[str, Any], ...] = ()
    orders: tuple[dict[str, Any], ...] = ()
    fills: tuple[dict[str, Any], ...] = ()


RuntimeEvidenceStatus = Literal["available", "partial", "stale", "unavailable", "out_of_scope"]


class RuntimeEvidence(BaseModel):
    """Evidence qualifier attached to every paper-runtime read model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RuntimeEvidenceStatus
    source: str
    observed_at: datetime | None = None
    reason: str | None = None


class PaperRuntimeSession(BaseModel):
    """Latest paper session identity and lifecycle evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str | None = None
    strategy_id: str | None = None
    status: str | None = None
    mode: str | None = None
    symbols: tuple[str, ...] = ()
    timeframe: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    evidence: RuntimeEvidence


class PaperRuntimeHealth(BaseModel):
    """Derived health classification with reasons and evidence freshness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["healthy", "degraded", "unhealthy", "unavailable"]
    reasons: tuple[str, ...] = ()
    checked_at: datetime
    evidence: RuntimeEvidence


class PaperFreshnessItem(BaseModel):
    """Freshness evidence for one observed market-data stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_class: Literal["stock", "crypto"]
    symbol: str
    timeframe: str
    latest_ts: datetime | None = None
    age_seconds: float | None = None
    stale: bool


class PaperDataFreshness(BaseModel):
    """Aggregate market-data freshness with explicit missing/stale states."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RuntimeEvidenceStatus
    items: tuple[PaperFreshnessItem, ...] = ()
    stale_count: int = 0
    missing_count: int = 0
    checked_at: datetime
    evidence: RuntimeEvidence


class PaperPosition(BaseModel):
    """One broker-backed position snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    qty: float
    avg_price: float | None = None
    asof_ts: datetime | None = None


class PaperPortfolio(BaseModel):
    """Cash and position snapshot read from published runtime evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cash: float | None = None
    asof_ts: datetime | None = None
    positions: tuple[PaperPosition, ...] = ()
    evidence: RuntimeEvidence


class PaperOpenOrder(BaseModel):
    """One latest non-terminal local order lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_order_id: str
    broker_order_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    qty: float | None = None
    order_type: str | None = None
    status: str
    created_at: datetime | None = None
    rejection_reason: str | None = None


class PaperOrders(BaseModel):
    """Bounded open-order evidence and its freshness qualifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[PaperOpenOrder, ...] = ()
    stale_count: int = 0
    evidence: RuntimeEvidence


class PaperFill(BaseModel):
    """One persisted fill evidence row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_order_id: str | None = None
    fill_ts: datetime | None = None
    fill_qty: float | None = None
    fill_price: float | None = None
    fee_amount: float | None = None
    slippage_amount: float | None = None


class PaperFills(BaseModel):
    """Bounded fills projection with partial-history qualification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[PaperFill, ...] = ()
    evidence: RuntimeEvidence


class PaperRiskOutcomes(BaseModel):
    """Risk outcome counts for the latest paper runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluated_count: int = 0
    approved_count: int = 0
    transformed_count: int = 0
    rejected_count: int = 0
    blocked_count: int = 0
    evidence: RuntimeEvidence


class PaperReconciliation(BaseModel):
    """Broker reconciliation state without inventing an attempt record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["reconciled", "required", "failed", "unavailable"]
    attempts: tuple["PaperReconciliationAttempt", ...] = ()
    last_attempt_at: datetime | None = None
    message: str | None = None
    evidence: RuntimeEvidence


class PaperReconciliationAttempt(BaseModel):
    """One bounded reconciliation attempt when a producer publishes it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    attempted_at: datetime | None = None
    status: str
    message: str | None = None


class PaperHaltState(BaseModel):
    """Operator halt state, or an explicit unavailable qualification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    halted: bool | None = None
    reason: str | None = None
    updated_at: datetime | None = None
    evidence: RuntimeEvidence


class PaperIncident(BaseModel):
    """Actionable issue derived from published runtime evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Literal["warning", "error"]
    message: str
    observed_at: datetime | None = None


class PaperRuntimeOperations(BaseModel):
    """Read-only paper operations projection for the Console workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str
    generated_at: datetime
    broker_account_binding: BrokerAccountBinding
    broker_account_display_label: str | None = None
    broker_identity_verified: bool = False
    session: PaperRuntimeSession
    health: PaperRuntimeHealth
    data_freshness: PaperDataFreshness
    portfolio: PaperPortfolio
    open_orders: PaperOrders
    fills: PaperFills
    risk: PaperRiskOutcomes
    reconciliation: PaperReconciliation
    halt: PaperHaltState
    incidents: tuple[PaperIncident, ...] = ()
