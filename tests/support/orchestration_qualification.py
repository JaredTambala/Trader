"""Bounded evidence helpers for controlled orchestration qualification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from trader.event_store import PostgresEventStore
from trader_agents.tool_client import McpToolClient
from trader_agents import (
    DataSpecialistRequest,
    ResearchCompositionRequest,
    build_data_specialist_task,
    build_experiment_design_task,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
)
from trader_research.foundation import parse_research_artifact_uri
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    ApprovalStatus,
    ArtifactReportRef,
    CostAssumption,
    DataRequirement,
    DatasetRole,
    ExperimentDesignRequest,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    InitialPortfolio,
    MaterialAssumption,
    OptimizationDirection,
    OptimizationProtocol,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    RobustnessRequirement,
    TunableDimension,
    TunableValueType,
    apply_experiment_protocol_approvals,
    artifact_report_ref,
)
from tests.support.realistic_optimization_fixture import (
    ASSET_CLASS,
    BACKTEST_ASSUMPTIONS,
    BASE_STRATEGY_PARAMETERS,
    OBJECTIVE_SOURCE,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE,
    SEARCH_LOOKBACKS,
    SEED,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE,
    SYMBOLS,
    TIMEFRAME,
    RealisticOptimizationFixture,
    FixtureRegion,
    SOURCE,
    postgres_region_content_sha256,
)
from tests.support.postgres_verification import (
    ORCHESTRATION_VERIFICATION_PROFILE,
    REPO_ROOT,
    VerificationConfigurationError,
    load_qualification_profile,
    load_test_settings,
    resolve_freeze_revision,
)


RetryDisposition = Literal[
    "accepted",
    "identical_retry",
    "rejected",
    "response_lost",
]
_IDENTITY_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_type",
        "artifact_uri",
        "content_hash",
        "dataset_id",
        "objective_id",
        "optimization_run_id",
        "plan_id",
        "proposal_id",
        "protocol_id",
        "run_id",
        "status",
        "uri",
        "workflow_id",
    }
)
_MAX_IDENTITY_ITEMS = 40
_MAX_IDENTITY_VALUE_LENGTH = 500
QUALIFICATION_COMPOSITION_ID = "controlled_orchestration_composition_v1"
RECOVERY_COMPOSITION_ID = "controlled_orchestration_recovery_v1"
QUALIFICATION_OPERATOR = "operator:controlled_qualification"
QUALIFICATION_COORDINATOR = "research_coordinator"


@dataclass(frozen=True)
class CallEvidence:
    """Credential-free identity of one public MCP call.

    Attributes:
        command: Registered MCP tool name.
        argument_digest: SHA-256 digest of canonical JSON arguments.
        result_identity: Bounded identifiers extracted from the public result.
        retry_disposition: Whether the call was accepted, rejected, or an
            explicitly verified identical retry.
    """

    command: str
    argument_digest: str
    result_identity: Mapping[str, Any]
    retry_disposition: RetryDisposition


@dataclass
class RecordingMcpToolClient:
    """Wrap an MCP client and retain only bounded, payload-free call evidence.

    Attributes:
        delegate: MCP client that performs the actual tool call.
        calls: Ordered bounded evidence collected in the current driver process.
    """

    delegate: McpToolClient
    calls: list[CallEvidence] = field(default_factory=list)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Call one tool and record no raw arguments, envelopes, or payloads.

        Args:
            tool_name: Registered MCP tool name.
            arguments: JSON-native public tool arguments.

        Returns:
            The delegate's MCP-style response unchanged.
        """
        digest = canonical_digest(arguments)
        try:
            result = await self.delegate.call_tool(tool_name, arguments)
        except Exception as exc:
            self.calls.append(
                CallEvidence(
                    command=_bounded_text(tool_name, field_name="command"),
                    argument_digest=digest,
                    result_identity={"error_type": type(exc).__name__},
                    retry_disposition="rejected",
                )
            )
            raise
        self.calls.append(
            CallEvidence(
                command=_bounded_text(tool_name, field_name="command"),
                argument_digest=digest,
                result_identity=extract_result_identity(result),
                retry_disposition=(
                    "rejected" if bool(result.get("isError")) else "accepted"
                ),
            )
        )
        return result


def ensure_fixture_region(
    event_store: PostgresEventStore,
    region: FixtureRegion,
) -> None:
    """Insert an exact fixture region once or revalidate its retained bytes.

    Args:
        event_store: Disposable controlled Postgres event store.
        region: Exact deterministic fixture region to ensure.

    Raises:
        AssertionError: If a retained region is partial or content-drifted.
    """
    row = event_store.connection().execute(
        "SELECT count(*) FROM stock_bar_events WHERE symbol = ANY(%s) "
        "AND timeframe = %s AND ts >= %s AND ts <= %s AND source = %s",
        [list(SYMBOLS), TIMEFRAME, region.start, region.end, SOURCE],
    ).fetchone()
    observed = int(row[0]) if row is not None else 0
    expected = region.bar_count * len(SYMBOLS)
    if observed == 0:
        for payload in region.rows():
            event_store.record_event("stock_bar_events", payload)
        return
    if observed != expected:
        raise AssertionError(
            f"retained fixture region {region.name!r} contains {observed} of {expected} rows"
        )
    if postgres_region_content_sha256(event_store, region) != region.content_sha256:
        raise AssertionError(f"retained fixture region {region.name!r} content drift")


async def prepare_qualification_request(
    *,
    tool_client: McpToolClient,
    fixture: RealisticOptimizationFixture,
    include_optimization: bool = True,
    composition_id: str = QUALIFICATION_COMPOSITION_ID,
) -> ResearchCompositionRequest:
    """Prepare explicit Data/design work over the realistic Postgres fixture.

    Setup registers supplied implementations and creates the exact snapshots needed
    to construct immutable later tasks. All product artifacts are created through
    public MCP tools; fixture bar insertion remains test setup rather than agent work.

    Args:
        tool_client: Public MCP transport bound to the disposable Postgres runtime.
        fixture: Exact multi-symbol selection and sealed-holdout regions.
        include_optimization: Whether to include the four-trial selection, sealed
            holdout, Evaluation, and Adversarial branch. Recovery runs disable it
            so only their declared backtest mutation gate is needed.
        composition_id: Stable operational identity for this qualification thread.

    Returns:
        Immutable composition request containing explicit Data tasks followed by
        one Experiment Design task.
    """
    if not isinstance(include_optimization, bool):
        raise ValueError("include_optimization must be a boolean")
    normalized_composition_id = _bounded_text(
        composition_id,
        field_name="composition_id",
    )
    strategy_ref = await _register_strategy(tool_client)
    risk_ref = await _register_risk(tool_client)
    selection_requirement = _requirement(fixture.selection.start, fixture.selection.end)
    selection_refs = await _create_snapshot(
        tool_client,
        selection_requirement,
        requested_by=normalized_composition_id,
    )
    objective_validation_ref = None
    holdout_requirement = None
    holdout_refs = None
    if include_optimization:
        objective_validation_ref = await _register_optimization_objective(tool_client)
        holdout_requirement = _requirement(fixture.holdout.start, fixture.holdout.end)
        holdout_refs = await _create_snapshot(
            tool_client,
            holdout_requirement,
            requested_by=normalized_composition_id,
        )
    objective_id = (
        "objective_controlled_orchestration_v1"
        if include_optimization
        else f"objective_{normalized_composition_id}"
    )
    if include_optimization:
        success_criterion = (
            "Produce baseline, selection, holdout, Evaluation, and "
            "Adversarial evidence."
        )
    elif normalized_composition_id == RECOVERY_COMPOSITION_ID:
        success_criterion = (
            "Produce canonical baseline evidence after a bounded restart."
        )
    else:
        success_criterion = (
            "Produce canonical baseline evidence within declared scale bounds."
        )
    objective = ResearchObjective(
        objective_id=objective_id,
        statement="Evaluate the supplied multi-asset implementation deterministically.",
        success_criteria=(success_criterion,),
        supplied_artifact_refs=(strategy_ref, risk_ref),
        requested_by=QUALIFICATION_OPERATOR,
        actor=QUALIFICATION_OPERATOR,
        status=ResearchObjectiveStatus.APPROVED,
    )
    datasets = (
        ProtocolDataset(
            requirement_id="selection" if include_optimization else "baseline",
            role=DatasetRole.SELECTION if include_optimization else DatasetRole.BASELINE,
            requirement=selection_requirement,
            dataset_manifest_ref=selection_refs[0],
            data_quality_report_ref=selection_refs[1],
        ),
    )
    if holdout_requirement is not None and holdout_refs is not None:
        datasets = (
            *datasets,
            ProtocolDataset(
                requirement_id="holdout",
                role=DatasetRole.HOLDOUT,
                requirement=holdout_requirement,
                dataset_manifest_ref=holdout_refs[0],
                data_quality_report_ref=holdout_refs[1],
                sealed=True,
            ),
        )
    optimization = None
    robustness: tuple[RobustnessRequirement, ...] = ()
    if objective_validation_ref is not None:
        optimization = OptimizationProtocol(
            objective_validation_ref=objective_validation_ref.uri,
            direction=OptimizationDirection.MAXIMIZE,
            trial_budget=4,
            seed=SEED,
            dimensions=(
                TunableDimension(
                    dimension_id="lookback_bars",
                    target_path="/strategy/parameters/lookback_bars",
                    value_type=TunableValueType.CATEGORICAL,
                    choices=SEARCH_LOOKBACKS,
                ),
            ),
        )
        robustness = (
            RobustnessRequirement(
                requirement_id="seed_sensitivity",
                attack_type="seed_sensitivity",
                claim="Selection must not depend on one random seed.",
            ),
            RobustnessRequirement(
                requirement_id="multiple_testing",
                attack_type="multiple_testing",
                claim="Review must account for the declared trial count.",
            ),
        )
    design = ExperimentDesignRequest(
        strategy=ProtocolStrategy(
            implementation_ref=strategy_ref,
            parameters=BASE_STRATEGY_PARAMETERS,
            tunable_fields=(
                ("/strategy/parameters/lookback_bars",)
                if include_optimization
                else ()
            ),
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=risk_ref,
                parameters=RISK_PARAMETERS,
            ),
        ),
        datasets=datasets,
        costs=_cost_assumptions(),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        optimization=optimization,
        deterministic_seed=SEED,
        max_runs=16,
        log_cycle_details=False,
        runtime_limits={"fixture": "controlled_orchestration_v1", "bounded": True},
        optimizer_profile="builtin_grid",
        robustness_requirements=robustness,
        evaluation_questions=(
            "Does sealed-holdout evidence support the selected implementation?",
        ),
        falsification_criteria=(
            "Block on invalid canonical evidence or incomplete required review.",
        ),
        material_assumptions=(
            MaterialAssumption(
                assumption_id="bounded_fixture_and_costs",
                category="qualification_scope",
                statement="Use the deterministic fixture and explicit cost model.",
                value={"fixture": "realistic_multi_asset_v1", "costs": True},
            ),
        ),
        requested_approver=QUALIFICATION_OPERATOR,
    )
    data_tasks = [
        build_data_specialist_task(
            request=DataSpecialistRequest(data_requirement=selection_requirement),
            objective=objective,
            requested_by=normalized_composition_id,
            actor=QUALIFICATION_COORDINATOR,
            permit_local_mutation=True,
        )
    ]
    if holdout_requirement is not None:
        data_tasks.append(
            build_data_specialist_task(
                request=DataSpecialistRequest(data_requirement=holdout_requirement),
                objective=objective,
                requested_by=normalized_composition_id,
                actor=QUALIFICATION_COORDINATOR,
                permit_local_mutation=True,
            )
        )
    tasks = (
        *data_tasks,
        build_experiment_design_task(
            request=design,
            objective=objective,
            requested_by=normalized_composition_id,
            actor=QUALIFICATION_COORDINATOR,
            permit_local_mutation=True,
        ),
    )
    return ResearchCompositionRequest(
        composition_id=normalized_composition_id,
        objective=objective,
        specialist_tasks=tasks,
        requested_by=QUALIFICATION_OPERATOR,
        actor=QUALIFICATION_COORDINATOR,
    )


def approve_qualification_proposal(
    proposal: ExperimentProtocolProposal,
) -> ExperimentProtocol:
    """Apply explicit operator approval without changing proposed design fields.

    Args:
        proposal: Canonical immutable proposal loaded from the artifact store.

    Returns:
        Separate approved protocol containing explicit operator decisions.
    """
    decisions = tuple(
        replace(
            approval,
            status=ApprovalStatus.APPROVED,
            decided_by=QUALIFICATION_OPERATOR,
            rationale="Approved for the bounded controlled qualification fixture.",
        )
        for approval in proposal.protocol.approvals
    )
    return apply_experiment_protocol_approvals(proposal, decisions)


def run_resume_worker(
    payload: Mapping[str, Any],
    *,
    timeout_seconds: int = 900,
) -> Mapping[str, Any]:
    """Run one composition stage in a separate Python and MCP process.

    Args:
        payload: Strict JSON-native worker request.
        timeout_seconds: Positive hard subprocess timeout.

    Returns:
        Parsed bounded stage result and call-evidence summaries.

    Raises:
        ValueError: If the timeout is not positive.
        RuntimeError: If the fresh driver fails or returns non-mapping JSON.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    result = subprocess.run(
        [sys.executable, "-m", "tests.support.orchestration_resume_worker"],
        cwd=REPO_ROOT,
        env=dict(os.environ),
        input=json.dumps(payload, sort_keys=True),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "fresh orchestration driver failed\n"
            f"stdout: {result.stdout[-4000:]}\n"
            f"stderr: {result.stderr[-8000:]}"
        )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, Mapping):
        raise RuntimeError("fresh orchestration driver returned non-mapping JSON")
    return parsed


async def _register_strategy(tool_client: McpToolClient) -> ArtifactReportRef:
    registered = await _call_tool(
        tool_client,
        RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
        {
            "name": "controlled-trailing-return-transition",
            "version": "1",
            "source_code": STRATEGY_SOURCE,
            "factory_name": "build_strategy",
            "class_name": "TrailingReturnTransitionStrategy",
            "parameter_schema": STRATEGY_PARAMETER_SCHEMA,
            "authoring_origin": "handwritten_test_fixture",
            "capabilities": ["multi_asset", "long_flat", "event_store_bars"],
        },
    )
    implementation = _artifact_ref(
        registered,
        "implementation_version",
        IMPLEMENTATION_VERSION,
    )
    await _call_tool(
        tool_client,
        RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
        {
            "implementation_version_id": implementation.artifact_id,
            "fixture_parameters": BASE_STRATEGY_PARAMETERS,
        },
    )
    return implementation


async def _register_risk(tool_client: McpToolClient) -> ArtifactReportRef:
    registered = await _call_tool(
        tool_client,
        RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
        {
            "name": "controlled-entry-quantity-limit",
            "version": "1",
            "source_code": RISK_SOURCE,
            "factory_name": "build_risk_manager",
            "class_name": "EntryQuantityLimitRiskManager",
            "parameter_schema": RISK_PARAMETER_SCHEMA,
            "authoring_origin": "handwritten_test_fixture",
            "capabilities": ["entry_quantity_limit", "risk_reducing_exit"],
        },
    )
    implementation = _artifact_ref(
        registered,
        "implementation_version",
        IMPLEMENTATION_VERSION,
    )
    await _call_tool(
        tool_client,
        RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
        {
            "implementation_version_id": implementation.artifact_id,
            "fixture_parameters": RISK_PARAMETERS,
        },
    )
    return implementation


async def _register_optimization_objective(
    tool_client: McpToolClient,
) -> ArtifactReportRef:
    registered = await _call_tool(
        tool_client,
        RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
        {
            "name": "controlled-risk-adjusted-return",
            "version": "1",
            "source_code": OBJECTIVE_SOURCE,
            "factory_name": "objective",
            "authoring_origin": "handwritten_test_fixture",
        },
    )
    implementation = _artifact_ref(
        registered,
        "implementation_version",
        IMPLEMENTATION_VERSION,
    )
    validated = await _call_tool(
        tool_client,
        RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
        {"implementation_version_id": implementation.artifact_id},
    )
    return _artifact_ref(
        validated,
        "implementation_validation_report",
        IMPLEMENTATION_VALIDATION_REPORT,
    )


async def _create_snapshot(
    tool_client: McpToolClient,
    requirement: DataRequirement,
    *,
    requested_by: str,
) -> tuple[ArtifactReportRef, ArtifactReportRef]:
    payload = await _call_tool(
        tool_client,
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
        {
            **requirement.to_dict(),
            "requested_by": requested_by,
            "actor": "Data Agent",
        },
    )
    return (
        _artifact_ref(payload, "dataset_manifest", DATASET_MANIFEST),
        _artifact_ref(payload, "data_quality_report", DATA_QUALITY_REPORT),
    )


async def _call_tool(
    tool_client: McpToolClient,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    result = await tool_client.call_tool(tool_name, arguments)
    structured = result.get("structuredContent")
    if not isinstance(structured, Mapping):
        raise AssertionError(f"{tool_name} returned no structured content")
    if bool(result.get("isError")) or structured.get("ok") is not True:
        raise AssertionError(f"{tool_name} failed: {structured.get('errors')}")
    if structured.get("command") != tool_name:
        raise AssertionError(f"{tool_name} returned mismatched command identity")
    return structured


def _artifact_ref(
    envelope: Mapping[str, Any],
    key: str,
    artifact_type: str,
) -> ArtifactReportRef:
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise AssertionError("MCP envelope contains no artifact mapping")
    artifact = artifacts.get(key)
    if not isinstance(artifact, Mapping):
        raise AssertionError(f"MCP envelope contains no artifact {key!r}")
    uri = str(artifact.get("uri") or "")
    parsed_type, artifact_id = parse_research_artifact_uri(uri)
    if parsed_type != artifact_type or artifact.get("artifact_type") != artifact_type:
        raise AssertionError(f"MCP artifact {key!r} has unexpected type")
    return artifact_report_ref(artifact_type, artifact_id)


def _requirement(start: datetime, end: datetime) -> DataRequirement:
    return DataRequirement(
        symbols=SYMBOLS,
        asset_class=ASSET_CLASS,
        timeframe=TIMEFRAME,
        start=start.isoformat(),
        end=end.isoformat(),
    )


def _cost_assumptions() -> tuple[CostAssumption, ...]:
    fees = BACKTEST_ASSUMPTIONS["fees"]
    slippage = BACKTEST_ASSUMPTIONS["slippage"]
    if not isinstance(fees, Mapping) or not isinstance(slippage, Mapping):
        raise AssertionError("realistic fixture costs must be mappings")
    return (
        CostAssumption(
            name="fees.fixed_per_order",
            value=float(fees["fixed_per_order"]),
            unit="currency_per_order",
        ),
        CostAssumption(
            name="fees.bps",
            value=float(fees["bps"]),
            unit="bps",
        ),
        CostAssumption(
            name="fees.minimum_fee",
            value=float(fees["minimum_fee"]),
            unit="currency_per_order",
        ),
        CostAssumption(
            name="slippage.bps",
            value=float(slippage["bps"]),
            unit="bps",
        ),
    )


def canonical_digest(value: Mapping[str, Any]) -> str:
    """Return the stable SHA-256 digest of a JSON-native mapping.

    Args:
        value: Mapping to serialize canonically.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_result_identity(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Extract a bounded result identity without retaining the MCP response.

    Args:
        result: Public MCP-style result mapping.

    Returns:
        A JSON-native summary containing only error state and recognized identity
        fields. Values are bounded before persistence.
    """
    identity: dict[str, Any] = {"is_error": bool(result.get("isError"))}
    structured = result.get("structuredContent")
    if isinstance(structured, Mapping):
        _collect_identity(structured, identity, path="result")
    return identity


def persist_call_evidence(
    *,
    phase: str,
    composition_id: str,
    calls: list[CallEvidence],
) -> None:
    """Persist ordered bounded call evidence in the disposable control schema.

    Args:
        phase: Responsibility-named controlled evidence phase.
        composition_id: Stable qualification composition identity.
        calls: Ordered evidence produced by one driver stage.

    Raises:
        VerificationConfigurationError: If the active profile is not the controlled
            orchestration profile or values exceed their evidence bounds.
    """
    profile = load_qualification_profile()
    if profile.name != ORCHESTRATION_VERIFICATION_PROFILE:
        raise VerificationConfigurationError(
            "orchestration call evidence requires the controlled orchestration profile"
        )
    if phase not in profile.phases:
        raise VerificationConfigurationError(
            f"phase must be one of {sorted(profile.phases)}"
        )
    bounded_composition_id = _bounded_text(
        composition_id,
        field_name="composition_id",
    )
    if len(calls) > 500:
        raise VerificationConfigurationError(
            "one qualification driver stage may record at most 500 tool calls"
        )
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_TEST settings are required")
    freeze_revision = resolve_freeze_revision(profile)
    with psycopg.connect(settings.conninfo(), autocommit=True) as connection:
        current_sequence = connection.execute(
            "SELECT COALESCE(max(sequence), 0) FROM "
            "verification_control.orchestration_call_ledger "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = %s AND composition_id = %s",
            [profile.name, freeze_revision, phase, bounded_composition_id],
        ).fetchone()
        sequence = int(current_sequence[0]) if current_sequence is not None else 0
        for call in calls:
            sequence += 1
            disposition = call.retry_disposition
            if disposition == "accepted":
                lost_match = connection.execute(
                    "SELECT 1 FROM verification_control.orchestration_call_ledger "
                    "WHERE qualification_profile = %s AND freeze_revision = %s "
                    "AND phase = %s AND composition_id = %s AND command = %s "
                    "AND argument_digest = %s AND result_identity = %s "
                    "AND retry_disposition = 'response_lost' LIMIT 1",
                    [
                        profile.name,
                        freeze_revision,
                        phase,
                        bounded_composition_id,
                        call.command,
                        call.argument_digest,
                        Jsonb(dict(call.result_identity)),
                    ],
                ).fetchone()
                if lost_match is not None:
                    disposition = "identical_retry"
            connection.execute(
                "INSERT INTO verification_control.orchestration_call_ledger ("
                "qualification_profile, freeze_revision, phase, composition_id, "
                "sequence, command, argument_digest, result_identity, retry_disposition"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    profile.name,
                    freeze_revision,
                    phase,
                    bounded_composition_id,
                    sequence,
                    _bounded_text(call.command, field_name="command"),
                    call.argument_digest,
                    Jsonb(dict(call.result_identity)),
                    disposition,
                ],
            )


def clear_call_evidence(*, phase: str, composition_id: str) -> None:
    """Clear one exact call-ledger slice before a controlled phase rerun.

    Args:
        phase: Responsibility-named controlled evidence phase.
        composition_id: Exact qualification composition identity.

    Raises:
        VerificationConfigurationError: If the profile, phase, composition ID or
            product-test database settings are invalid.
    """
    profile = load_qualification_profile()
    if profile.name != ORCHESTRATION_VERIFICATION_PROFILE:
        raise VerificationConfigurationError(
            "orchestration call evidence requires its qualification profile"
        )
    if phase not in profile.phases:
        raise VerificationConfigurationError(
            f"phase must be one of {sorted(profile.phases)}"
        )
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_TEST settings are required")
    with psycopg.connect(settings.conninfo(), autocommit=True) as connection:
        connection.execute(
            "DELETE FROM verification_control.orchestration_call_ledger "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = %s AND composition_id = %s",
            [
                profile.name,
                resolve_freeze_revision(profile),
                phase,
                _bounded_text(composition_id, field_name="composition_id"),
            ],
        )


def persist_scale_result(
    *,
    profile_name: str,
    task_count: int,
    transition_count: int,
    tool_call_count: int,
    checkpoint_bytes: int,
    artifact_count: int,
    database_bytes: int,
    wall_seconds: float,
    payload: Mapping[str, Any],
) -> None:
    """Persist one local bounded-scale measurement without claiming an SLA.

    Args:
        profile_name: Responsibility-named measurement profile.
        task_count: Explicit specialist tasks exercised.
        transition_count: Composition transitions observed.
        tool_call_count: Public MCP calls recorded by the bounded ledger.
        checkpoint_bytes: Current isolated checkpoint relation bytes.
        artifact_count: Current canonical research artifact count.
        database_bytes: Current disposable database size.
        wall_seconds: Local elapsed wall time.
        payload: Bounded identifiers and structural observations only.

    Raises:
        VerificationConfigurationError: If the active profile or a measurement is
            invalid.
    """
    profile = load_qualification_profile()
    if profile.name != ORCHESTRATION_VERIFICATION_PROFILE:
        raise VerificationConfigurationError(
            "orchestration scale evidence requires its qualification profile"
        )
    normalized_profile_name = _bounded_text(
        profile_name,
        field_name="profile_name",
    )
    counts = {
        "task_count": task_count,
        "transition_count": transition_count,
        "tool_call_count": tool_call_count,
        "checkpoint_bytes": checkpoint_bytes,
        "artifact_count": artifact_count,
        "database_bytes": database_bytes,
    }
    invalid_count = any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts.values()
    )
    if invalid_count:
        raise VerificationConfigurationError(
            "orchestration scale counts must be non-negative integers"
        )
    if isinstance(wall_seconds, bool) or wall_seconds < 0:
        raise VerificationConfigurationError(
            "orchestration scale wall_seconds must be non-negative"
        )
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_TEST settings are required")
    freeze_revision = resolve_freeze_revision(profile)
    with psycopg.connect(settings.conninfo(), autocommit=True) as connection:
        connection.execute(
            "INSERT INTO verification_control.orchestration_scale_results ("
            "qualification_profile, freeze_revision, phase, profile, status, "
            "task_count, transition_count, tool_call_count, checkpoint_bytes, "
            "artifact_count, database_bytes, wall_seconds, payload"
            ") VALUES (%s, %s, 'ORCHESTRATION_SCALE', %s, 'passed', %s, %s, %s, "
            "%s, %s, %s, %s, %s) ON CONFLICT (qualification_profile, "
            "freeze_revision, phase, profile) DO UPDATE SET status = 'passed', "
            "task_count = EXCLUDED.task_count, "
            "transition_count = EXCLUDED.transition_count, "
            "tool_call_count = EXCLUDED.tool_call_count, "
            "checkpoint_bytes = EXCLUDED.checkpoint_bytes, "
            "artifact_count = EXCLUDED.artifact_count, "
            "database_bytes = EXCLUDED.database_bytes, "
            "wall_seconds = EXCLUDED.wall_seconds, payload = EXCLUDED.payload, "
            "recorded_at = now()",
            [
                profile.name,
                freeze_revision,
                normalized_profile_name,
                task_count,
                transition_count,
                tool_call_count,
                checkpoint_bytes,
                artifact_count,
                database_bytes,
                float(wall_seconds),
                Jsonb(dict(payload)),
            ],
        )


def _collect_identity(
    value: Mapping[str, Any],
    identity: dict[str, Any],
    *,
    path: str,
) -> None:
    for key in sorted(value):
        if len(identity) >= _MAX_IDENTITY_ITEMS:
            return
        item = value[key]
        item_path = f"{path}.{key}"
        if key in _IDENTITY_KEYS and isinstance(item, (str, int, float, bool)):
            identity[item_path] = _bounded_identity_value(item)
        elif isinstance(item, Mapping):
            _collect_identity(item, identity, path=item_path)
        elif isinstance(item, list):
            for index, nested in enumerate(item[:20]):
                if len(identity) >= _MAX_IDENTITY_ITEMS:
                    return
                if isinstance(nested, Mapping):
                    _collect_identity(
                        nested,
                        identity,
                        path=f"{item_path}[{index}]",
                    )


def _bounded_identity_value(value: str | int | float | bool) -> str | int | float | bool:
    if isinstance(value, str):
        return value[:_MAX_IDENTITY_VALUE_LENGTH]
    return value


def _bounded_text(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise VerificationConfigurationError(f"{field_name} must not be empty")
    if len(normalized) > 200:
        raise VerificationConfigurationError(
            f"{field_name} must be at most 200 characters"
        )
    return normalized
