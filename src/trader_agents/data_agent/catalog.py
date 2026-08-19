"""Register the closed, responsibility-named actions of the Data specialist."""

from __future__ import annotations

from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
)
from trader_research.foundation import DATA_DOMAIN_OWNER, ResearchArtifactStore
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
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

from .actions import (
    CaptureMarketDataEvidenceHandler,
    EnsureMarketDataAvailableHandler,
    ValidateMarketDataScopeHandler,
)
from .domain import ALLOW_SAMPLE_DATA_LOADING_GATE, DATA_SPECIALIST_AUTHORITY
from .policy import (
    CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
    DATA_SPECIALIST_ACTION_VERSION,
    ENSURE_MARKET_DATA_AVAILABLE_ACTION,
    VALIDATE_MARKET_DATA_SCOPE_ACTION,
)


def build_data_specialist_catalog(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
) -> SpecialistActionCatalog:
    """Build the production Data action catalog with injected dependencies.

    Args:
        tool_client: MCP boundary used by all registered Data handlers.
        artifact_store: Canonical store used to verify snapshot references.

    Returns:
        Immutable action catalog scoped to the Data decision authority.
    """
    return SpecialistActionCatalog(
        authority_key=DATA_SPECIALIST_AUTHORITY,
        actions=(
            RegisteredSpecialistAction(
                capability=CapabilityDefinition(
                    capability_id=VALIDATE_MARKET_DATA_SCOPE_ACTION,
                    version=DATA_SPECIALIST_ACTION_VERSION,
                    description=(
                        "Validate exact market-data symbols and provider context."
                    ),
                    domain_owner=DATA_DOMAIN_OWNER,
                    producer_tool=DATA_DISCOVER_SYMBOLS_TOOL,
                    side_effect=CapabilitySideEffect.READ_ONLY,
                    input_slots=(),
                    output_slots=(),
                    configuration_keys=("mcp_tool_client",),
                    idempotent=True,
                ),
                handler=ValidateMarketDataScopeHandler(tool_client),
            ),
            RegisteredSpecialistAction(
                capability=CapabilityDefinition(
                    capability_id=ENSURE_MARKET_DATA_AVAILABLE_ACTION,
                    version=DATA_SPECIALIST_ACTION_VERSION,
                    description=("Load approved checked-in sample data idempotently."),
                    domain_owner=DATA_DOMAIN_OWNER,
                    producer_tool=DATA_ENSURE_LOADED_TOOL,
                    side_effect=CapabilitySideEffect.LOCAL_MUTATING,
                    input_slots=(),
                    output_slots=(),
                    policy_gates=(ALLOW_SAMPLE_DATA_LOADING_GATE,),
                    configuration_keys=("mcp_tool_client",),
                    idempotent=True,
                ),
                handler=EnsureMarketDataAvailableHandler(tool_client),
            ),
            RegisteredSpecialistAction(
                capability=CapabilityDefinition(
                    capability_id=CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
                    version=DATA_SPECIALIST_ACTION_VERSION,
                    description=(
                        "Persist and verify matching canonical Data evidence."
                    ),
                    domain_owner=DATA_DOMAIN_OWNER,
                    producer_tool=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
                    side_effect=CapabilitySideEffect.LOCAL_MUTATING,
                    input_slots=(),
                    output_slots=(
                        _output_slot("manifest", DATASET_MANIFEST),
                        _output_slot("quality", DATA_QUALITY_REPORT),
                    ),
                    configuration_keys=(
                        "mcp_tool_client",
                        "research_artifact_store",
                    ),
                    idempotent=True,
                ),
                handler=CaptureMarketDataEvidenceHandler(
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


def _output_slot(slot_id: str, artifact_type: str) -> ArtifactSlot:
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=DATA_DOMAIN_OWNER,
        cardinality=ArtifactCardinality.EXACTLY_ONE,
        required=True,
    )
