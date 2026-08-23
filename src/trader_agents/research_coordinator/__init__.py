"""Expose bounded Research Coordinator contracts, policy, and graph wiring.

Callers can select one typed next action with ``coordinate_research`` or run the
same policy through a JSON-safe LangGraph adapter. Workflow execution remains in
``trader_agents.orchestration``; ``trader_agents.research_composition`` connects
these decisions to registered specialist and workflow execution boundaries.
"""

from .catalog import (
    RegisteredWorkflowTemplate,
    WorkflowTemplateCatalog,
    WorkflowTemplateCompiler,
    WorkflowTemplateEligibility,
    default_workflow_template_catalog,
)
from .domain import (
    CoordinationDecision,
    CoordinatorAction,
    WorkflowTemplateDescriptor,
)
from .graph import (
    CoordinatorGraphStatus,
    ResearchCoordinatorState,
    build_research_coordinator_graph,
    build_research_coordinator_initial_state,
)
from .policy import (
    ResearchCoordination,
    compile_coordination_decision,
    coordinate_research,
)

__all__ = [
    "CoordinationDecision",
    "CoordinatorAction",
    "CoordinatorGraphStatus",
    "RegisteredWorkflowTemplate",
    "ResearchCoordination",
    "ResearchCoordinatorState",
    "WorkflowTemplateCatalog",
    "WorkflowTemplateCompiler",
    "WorkflowTemplateDescriptor",
    "WorkflowTemplateEligibility",
    "build_research_coordinator_graph",
    "build_research_coordinator_initial_state",
    "compile_coordination_decision",
    "coordinate_research",
    "default_workflow_template_catalog",
]
