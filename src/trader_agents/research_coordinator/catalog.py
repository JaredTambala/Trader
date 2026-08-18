"""Register the closed set of workflow templates available to coordination.

Template metadata is safe to expose in graph state. Runtime compiler and
eligibility callables remain code-owned dependencies and cannot be supplied by
an operator, model, checkpoint, or MCP response.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from trader_research.foundation import ResearchArtifactStore
from trader_research.governance import ExperimentProtocol, ResearchObjective

from trader_agents.orchestration import (
    WORKFLOW_TEMPLATE_ID,
    WORKFLOW_TEMPLATE_VERSION,
    CompiledResearchWorkflow,
    compile_supplied_implementation_workflow,
)

from .domain import WorkflowTemplateDescriptor


class WorkflowTemplateCompiler(Protocol):
    """Compile one objective and protocol through a registered template."""

    def __call__(
        self,
        *,
        objective: ResearchObjective,
        protocol: ExperimentProtocol,
        artifact_store: ResearchArtifactStore,
    ) -> CompiledResearchWorkflow:
        """Return a deterministic ready workflow or raise a validation error."""


class WorkflowTemplateEligibility(Protocol):
    """Determine whether a protocol shape belongs to one template."""

    def __call__(
        self,
        objective: ResearchObjective,
        protocol: ExperimentProtocol,
    ) -> bool:
        """Return whether the template is eligible without reading artifacts."""


@dataclass(frozen=True)
class RegisteredWorkflowTemplate:
    """Code-owned workflow-template metadata and runtime behavior.

    Attributes:
        descriptor: Public stable template identity and purpose.
        is_eligible: Pure protocol-shape predicate used during selection.
        compiler: Deterministic compiler invoked only after unique selection.
    """

    descriptor: WorkflowTemplateDescriptor
    is_eligible: WorkflowTemplateEligibility
    compiler: WorkflowTemplateCompiler

    def __post_init__(self) -> None:
        """Reject incomplete runtime registrations at catalog construction."""
        if not callable(self.is_eligible):
            raise ValueError("workflow template eligibility must be callable")
        if not callable(self.compiler):
            raise ValueError("workflow template compiler must be callable")


class WorkflowTemplateCatalog:
    """Immutable lookup boundary for code-registered workflow templates."""

    def __init__(self, templates: Sequence[RegisteredWorkflowTemplate]) -> None:
        """Validate and index a non-empty set of unique registrations.

        Args:
            templates: Code-owned registrations available to the coordinator.

        Raises:
            ValueError: If the catalog is empty or repeats template identity.
        """
        normalized = tuple(templates)
        if not normalized:
            raise ValueError("workflow template catalog cannot be empty")
        by_identity: dict[tuple[str, str], RegisteredWorkflowTemplate] = {}
        for template in normalized:
            identity = (
                template.descriptor.template_id,
                template.descriptor.version,
            )
            if identity in by_identity:
                raise ValueError(
                    "workflow template registrations must have unique identity"
                )
            by_identity[identity] = template
        self._templates = normalized
        self._by_identity = by_identity

    @property
    def descriptors(self) -> tuple[WorkflowTemplateDescriptor, ...]:
        """Return public metadata in deterministic registration order."""
        return tuple(template.descriptor for template in self._templates)

    def eligible_templates(
        self,
        *,
        objective: ResearchObjective,
        protocol: ExperimentProtocol,
    ) -> tuple[RegisteredWorkflowTemplate, ...]:
        """Return registrations whose pure eligibility predicates accept input.

        Args:
            objective: Validated research objective.
            protocol: Validated experiment protocol.

        Returns:
            Eligible registrations in deterministic catalog order.
        """
        return tuple(
            template
            for template in self._templates
            if template.is_eligible(objective, protocol)
        )

    def require(
        self,
        template_id: str,
        version: str,
    ) -> RegisteredWorkflowTemplate:
        """Resolve an exact registered template identity.

        Args:
            template_id: Stable registered template identifier.
            version: Exact immutable template version.

        Returns:
            Matching code-owned registration.

        Raises:
            ValueError: If the identity is not registered.
        """
        try:
            return self._by_identity[(template_id, version)]
        except KeyError as exc:
            raise ValueError(
                f"workflow template is not registered: {template_id}:{version}"
            ) from exc


def default_workflow_template_catalog() -> WorkflowTemplateCatalog:
    """Build the maintained catalog of executable research workflows.

    Returns:
        Catalog containing only code-reviewed template registrations.
    """
    return WorkflowTemplateCatalog(
        (
            RegisteredWorkflowTemplate(
                descriptor=WorkflowTemplateDescriptor(
                    template_id=WORKFLOW_TEMPLATE_ID,
                    version=WORKFLOW_TEMPLATE_VERSION,
                    description=(
                        "Validate supplied strategy and risk implementations, "
                        "execute the approved experiment protocol, and produce "
                        "bounded evidence and review artifacts."
                    ),
                ),
                is_eligible=_supports_supplied_implementation_workflow,
                compiler=compile_supplied_implementation_workflow,
            ),
        )
    )


def _supports_supplied_implementation_workflow(
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
) -> bool:
    del objective
    return not protocol.robustness_requirements or protocol.optimization is not None
