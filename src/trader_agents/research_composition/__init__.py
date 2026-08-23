"""Public boundaries for resumable specialist-to-workflow composition."""

from .catalog import build_research_composition_catalog
from .domain import (
    MAX_COMPOSITION_SPECIALIST_TASKS,
    MAX_COMPOSITION_TRANSITIONS,
    ResearchCompositionRequest,
    ResearchCompositionState,
    ResearchCompositionStatus,
    build_research_composition_initial_state,
    protocol_design_digest,
    protocol_digest,
    research_composition_digest,
    research_composition_public_state,
    research_composition_thread_config,
)
from .graph import build_research_composition_graph
from .runner import ResearchCompositionConflictError, run_research_composition
from .validation import (
    accept_specialist_result,
    resolve_accepted_protocol_proposal,
    summarize_specialist_result,
    validate_protocol_consumes_specialist_outputs,
    validate_protocol_matches_proposal,
)

__all__ = [
    "MAX_COMPOSITION_SPECIALIST_TASKS",
    "MAX_COMPOSITION_TRANSITIONS",
    "ResearchCompositionConflictError",
    "ResearchCompositionRequest",
    "ResearchCompositionState",
    "ResearchCompositionStatus",
    "accept_specialist_result",
    "build_research_composition_catalog",
    "build_research_composition_graph",
    "build_research_composition_initial_state",
    "protocol_design_digest",
    "protocol_digest",
    "research_composition_digest",
    "research_composition_public_state",
    "research_composition_thread_config",
    "resolve_accepted_protocol_proposal",
    "run_research_composition",
    "summarize_specialist_result",
    "validate_protocol_consumes_specialist_outputs",
    "validate_protocol_matches_proposal",
]
