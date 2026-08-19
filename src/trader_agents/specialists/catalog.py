"""Register the closed action set available to one specialist authority.

Capability metadata is safe to expose as a declarative snapshot. Action
handlers remain code-owned runtime dependencies and cannot be supplied through
graph state, a model response, a checkpoint, or an MCP result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from trader_research.governance import CapabilityDefinition, get_decision_authority

from .policy import SpecialistActionHandler


@dataclass(frozen=True)
class RegisteredSpecialistAction:
    """Code-owned capability definition and its runtime action handler.

    Attributes:
        capability: Declarative action identity, authority, slots, and policy.
        handler: Injected behavior that parses typed input and performs the action.
    """

    capability: CapabilityDefinition
    handler: SpecialistActionHandler

    def __post_init__(self) -> None:
        """Reject an incomplete runtime registration."""
        if not callable(getattr(self.handler, "run", None)):
            raise ValueError("registered specialist action handler must define run")


class SpecialistActionCatalog:
    """Immutable action lookup boundary for one specialist authority."""

    def __init__(
        self,
        *,
        authority_key: str,
        actions: Sequence[RegisteredSpecialistAction],
        available_configuration_keys: Sequence[str] = (),
    ) -> None:
        """Validate action identity and artifact authority.

        Args:
            authority_key: Registered specialist decision-authority key.
            actions: Non-empty code-owned action registrations.
            available_configuration_keys: Names of runtime dependencies already
                injected into the registered handlers. Values and secrets never
                enter the catalog or graph state.

        Raises:
            ValueError: If authority, registrations, or output domains conflict.
        """
        authority = get_decision_authority(authority_key)
        if authority.key == "research_coordinator":
            raise ValueError("Research Coordinator cannot own specialist actions")
        normalized = tuple(actions)
        if not normalized:
            raise ValueError("specialist action catalog cannot be empty")
        configuration_keys = tuple(available_configuration_keys)
        if any(
            not isinstance(key, str) or not key.strip() for key in configuration_keys
        ):
            raise ValueError("specialist configuration keys must be non-empty")
        if len(configuration_keys) != len(set(configuration_keys)):
            raise ValueError("specialist configuration keys must be unique")
        by_identity: dict[tuple[str, str], RegisteredSpecialistAction] = {}
        for action in normalized:
            capability = action.capability
            identity = (capability.capability_id, capability.version)
            if identity in by_identity:
                raise ValueError(
                    "specialist action registrations must have unique identity"
                )
            if capability.domain_owner not in authority.artifact_domains:
                raise ValueError(
                    f"{authority.display_name} cannot register an action for the "
                    f"{capability.domain_owner} domain"
                )
            if not capability.idempotent:
                raise ValueError(
                    "specialist actions must be idempotent for bounded replay"
                )
            missing_configuration = sorted(
                set(capability.configuration_keys) - set(configuration_keys)
            )
            if missing_configuration:
                raise ValueError(
                    "specialist action requires unavailable configuration: "
                    + ", ".join(missing_configuration)
                )
            for output_slot in capability.output_slots:
                if output_slot.domain_owner not in authority.artifact_domains:
                    raise ValueError(
                        f"{authority.display_name} cannot register output "
                        f"{output_slot.artifact_type}"
                    )
            by_identity[identity] = action
        self._authority_key = authority.key
        self._actions = normalized
        self._by_identity = by_identity

    @property
    def authority_key(self) -> str:
        """Return the registered decision authority for every catalog action."""
        return self._authority_key

    @property
    def capabilities(self) -> tuple[CapabilityDefinition, ...]:
        """Return public action metadata in deterministic registration order."""
        return tuple(action.capability for action in self._actions)

    def require(
        self,
        action_id: str,
        version: str,
    ) -> RegisteredSpecialistAction:
        """Resolve one exact registered action identity.

        Args:
            action_id: Stable responsibility-based action identifier.
            version: Exact immutable action version.

        Returns:
            Matching code-owned registration.

        Raises:
            ValueError: If the requested identity is not registered.
        """
        try:
            return self._by_identity[(action_id, version)]
        except KeyError as exc:
            raise ValueError(
                f"specialist action is not registered: {action_id}:{version}"
            ) from exc
