"""Register the closed action set for the Experiment Design specialist."""

from __future__ import annotations

from trader_mcp.constants import (
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    EXPERIMENTS_DOMAIN_OWNER,
    ResearchArtifactStore,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    ArtifactCardinality,
    ArtifactSlot,
    CapabilityDefinition,
    CapabilitySideEffect,
)

from trader_agents.specialists import (
    RegisteredSpecialistAction,
    SpecialistActionCatalog,
)
from trader_agents.tool_client import McpToolClient

from .actions import CreateExperimentProtocolProposalHandler
from .domain import EXPERIMENT_DESIGN_AUTHORITY
from .policy import (
    CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
    EXPERIMENT_DESIGN_ACTION_VERSION,
)


def build_experiment_design_catalog(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
) -> SpecialistActionCatalog:
    """Build the production Design catalog with injected MCP and store boundaries."""
    capability = CapabilityDefinition(
        capability_id=CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
        version=EXPERIMENT_DESIGN_ACTION_VERSION,
        description="Persist and verify one immutable experiment protocol proposal.",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool=RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
        side_effect=CapabilitySideEffect.LOCAL_MUTATING,
        input_slots=(
            _input_slot(
                "implementations",
                IMPLEMENTATION_VERSION,
                EXPERIMENTS_DOMAIN_OWNER,
                ArtifactCardinality.ONE_OR_MORE,
                required=True,
            ),
            _input_slot(
                "dataset_manifests",
                DATASET_MANIFEST,
                DATA_DOMAIN_OWNER,
                ArtifactCardinality.ONE_OR_MORE,
                required=True,
            ),
            _input_slot(
                "data_quality_reports",
                DATA_QUALITY_REPORT,
                DATA_DOMAIN_OWNER,
                ArtifactCardinality.ONE_OR_MORE,
                required=True,
            ),
            _input_slot(
                "optimization_objective_validation",
                IMPLEMENTATION_VALIDATION_REPORT,
                EXPERIMENTS_DOMAIN_OWNER,
                ArtifactCardinality.ZERO_OR_ONE,
                required=False,
            ),
        ),
        output_slots=(
            ArtifactSlot(
                slot_id="proposal",
                artifact_type=EXPERIMENT_PROTOCOL_PROPOSAL,
                domain_owner=EXPERIMENTS_DOMAIN_OWNER,
                cardinality=ArtifactCardinality.EXACTLY_ONE,
                required=True,
            ),
        ),
        configuration_keys=("mcp_tool_client", "research_artifact_store"),
        idempotent=True,
    )
    return SpecialistActionCatalog(
        authority_key=EXPERIMENT_DESIGN_AUTHORITY,
        actions=(
            RegisteredSpecialistAction(
                capability=capability,
                handler=CreateExperimentProtocolProposalHandler(
                    tool_client=tool_client,
                    artifact_store=artifact_store,
                ),
            ),
        ),
        available_configuration_keys=(
            "mcp_tool_client",
            "research_artifact_store",
        ),
    )


def _input_slot(
    slot_id: str,
    artifact_type: str,
    domain_owner: str,
    cardinality: ArtifactCardinality,
    *,
    required: bool,
) -> ArtifactSlot:
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=domain_owner,
        cardinality=cardinality,
        required=required,
    )
