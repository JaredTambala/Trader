"""Route bounded specialist tasks through code-owned graph registrations.

Route metadata is safe to expose to the Research Coordinator. Runtime runners,
MCP clients, stores, checkpointers, and configuration remain injected code
dependencies and never enter a coordination decision or checkpoint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from trader_research.governance import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ArtifactReportRef,
    get_decision_authority,
)

from .domain import SpecialistResult, SpecialistTask


class SpecialistTaskRunner(Protocol):
    """Execute one exact task through an already configured specialist graph."""

    async def run(self, task: SpecialistTask) -> SpecialistResult:
        """Return the bounded terminal result for the supplied task."""


@dataclass(frozen=True)
class AcceptedSpecialistResult:
    """Checkpoint-safe receipt for one validated completed specialist task.

    Attributes:
        task_id: Exact specialist task that completed.
        authority_key: Decision authority that produced the result.
        task_digest: Digest of the original caller-built task.
        route_version: Code-owned route version used for execution.
        result_digest: Digest of the complete validated terminal result.
        artifact_refs: Canonical output refs resolved during validation.
        output_bindings: Task output slots mapped to canonical artifact URIs.
    """

    task_id: str
    authority_key: str
    task_digest: str
    route_version: str
    result_digest: str
    artifact_refs: tuple[ArtifactReportRef, ...]
    output_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate receipt identity and exact output-reference coverage."""
        for value, label in (
            (self.task_id, "accepted specialist task_id"),
            (self.authority_key, "accepted specialist authority"),
            (self.task_digest, "accepted specialist task digest"),
            (self.route_version, "accepted specialist route version"),
            (self.result_digest, "accepted specialist result digest"),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        get_decision_authority(self.authority_key)
        uris = tuple(reference.uri for reference in self.artifact_refs)
        if len(uris) != len(set(uris)):
            raise ValueError("accepted specialist artifact refs must be unique")
        normalized_bindings = {
            str(slot_id): tuple(str(uri) for uri in bound_uris)
            for slot_id, bound_uris in self.output_bindings.items()
        }
        if any(not slot_id.strip() for slot_id in normalized_bindings):
            raise ValueError("accepted specialist output slots must be non-empty")
        bound_uris = tuple(
            uri for values in normalized_bindings.values() for uri in values
        )
        if len(bound_uris) != len(set(bound_uris)):
            raise ValueError("accepted specialist refs cannot bind more than once")
        if set(bound_uris) != set(uris):
            raise ValueError(
                "accepted specialist bindings must cover every artifact ref"
            )
        object.__setattr__(self, "output_bindings", normalized_bindings)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded accepted-result receipt for checkpointing."""
        return {
            "task_id": self.task_id,
            "authority_key": self.authority_key,
            "task_digest": self.task_digest,
            "route_version": self.route_version,
            "result_digest": self.result_digest,
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "output_bindings": {
                slot_id: list(uris)
                for slot_id, uris in self.output_bindings.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AcceptedSpecialistResult:
        """Parse a strict accepted-result receipt from checkpoint data.

        Args:
            payload: Mapping containing only bounded receipt fields.

        Returns:
            Validated accepted specialist result.

        Raises:
            ValueError: If unknown fields, refs, or bindings are invalid.
        """
        allowed = {
            "task_id",
            "authority_key",
            "task_digest",
            "route_version",
            "result_digest",
            "artifact_refs",
            "output_bindings",
        }
        unknown = sorted(set(payload).difference(allowed))
        if unknown:
            raise ValueError(
                "accepted specialist result contains unknown fields: "
                + ", ".join(unknown)
            )
        raw_refs = payload.get("artifact_refs") or ()
        if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, (str, bytes)):
            raise ValueError("accepted specialist artifact_refs must be a sequence")
        if any(not isinstance(item, Mapping) for item in raw_refs):
            raise ValueError("accepted specialist artifact_refs must be mappings")
        raw_bindings = payload.get("output_bindings") or {}
        if not isinstance(raw_bindings, Mapping):
            raise ValueError("accepted specialist output_bindings must be a mapping")
        bindings: dict[str, tuple[str, ...]] = {}
        for slot_id, value in raw_bindings.items():
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                raise ValueError(
                    "accepted specialist output binding values must be sequences"
                )
            bindings[str(slot_id)] = tuple(str(item) for item in value)
        return cls(
            task_id=str(payload.get("task_id") or ""),
            authority_key=str(payload.get("authority_key") or ""),
            task_digest=str(payload.get("task_digest") or ""),
            route_version=str(payload.get("route_version") or ""),
            result_digest=str(payload.get("result_digest") or ""),
            artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in raw_refs
                if isinstance(item, Mapping)
            ),
            output_bindings=bindings,
        )


@dataclass(frozen=True)
class SpecialistRouteDescriptor:
    """Public identity and output scope of one specialist graph route.

    Attributes:
        authority_key: Registered specialist decision authority.
        version: Immutable version of the graph assembly and routing contract.
        supported_output_types: Artifact types the route can produce.
    """

    authority_key: str
    version: str
    supported_output_types: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate authority, route version, and declared output coverage."""
        authority = get_decision_authority(self.authority_key)
        if authority.key == "research_coordinator":
            raise ValueError("Research Coordinator cannot be a specialist route")
        if not self.version.strip():
            raise ValueError("specialist route version is required")
        if not self.supported_output_types:
            raise ValueError("specialist route requires supported output types")
        if any(not item.strip() for item in self.supported_output_types):
            raise ValueError("specialist route output types must be non-empty")
        if len(self.supported_output_types) != len(set(self.supported_output_types)):
            raise ValueError("specialist route output types must be unique")
        unknown_types = sorted(
            set(self.supported_output_types).difference(
                DOMAIN_OWNER_BY_ARTIFACT_TYPE
            )
        )
        if unknown_types:
            raise ValueError(
                "specialist route declares unsupported artifact types: "
                + ", ".join(unknown_types)
            )
        foreign_types = sorted(
            artifact_type
            for artifact_type in self.supported_output_types
            if DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type]
            not in authority.artifact_domains
        )
        if foreign_types:
            raise ValueError(
                f"{authority.display_name} cannot route artifact types owned by "
                "another domain: "
                + ", ".join(foreign_types)
            )

    def to_dict(self) -> dict[str, object]:
        """Serialize public route metadata without its runtime runner."""
        return {
            "authority_key": self.authority_key,
            "version": self.version,
            "supported_output_types": list(self.supported_output_types),
        }


@dataclass(frozen=True)
class RegisteredSpecialistRoute:
    """Code-owned specialist route metadata and injected runtime runner.

    Attributes:
        descriptor: Stable public route identity and output coverage.
        runner: Configured graph runner retained outside public state.
    """

    descriptor: SpecialistRouteDescriptor
    runner: SpecialistTaskRunner

    def __post_init__(self) -> None:
        """Reject registrations without an asynchronous runner boundary."""
        if not callable(getattr(self.runner, "run", None)):
            raise ValueError("registered specialist route runner must define run")


class SpecialistRouteError(ValueError):
    """Base error for safe specialist route-selection failures."""


class SpecialistRouteUnavailableError(SpecialistRouteError):
    """Raised when no runtime route exists for a registered authority."""

    def __init__(self, authority_key: str) -> None:
        """Capture the unavailable authority for a typed prerequisite."""
        super().__init__(
            f"specialist route is unavailable for authority: {authority_key}"
        )
        self.authority_key = authority_key


class SpecialistRouteAmbiguityError(SpecialistRouteError):
    """Raised when more than one route accepts the same specialist task."""


class SpecialistRouteUnsupportedTaskError(SpecialistRouteError):
    """Raised when an authority route cannot produce the requested outputs."""


class SpecialistRouteCatalog:
    """Immutable lookup boundary for code-registered specialist graphs."""

    def __init__(self, routes: Sequence[RegisteredSpecialistRoute]) -> None:
        """Index route registrations without choosing a preferred version.

        Multiple versions for one authority are permitted so selection can fail
        explicitly as ambiguous until an old registration is removed. Exact
        duplicate identities are rejected at construction.

        Args:
            routes: Code-owned specialist graph registrations.

        Raises:
            ValueError: If an exact authority/version identity is duplicated.
        """
        normalized = tuple(routes)
        identities = [
            (route.descriptor.authority_key, route.descriptor.version)
            for route in normalized
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("specialist route identities must be unique")
        self._routes = normalized
        self._by_identity = {
            (route.descriptor.authority_key, route.descriptor.version): route
            for route in normalized
        }

    @property
    def descriptors(self) -> tuple[SpecialistRouteDescriptor, ...]:
        """Return public route metadata in deterministic registration order."""
        return tuple(route.descriptor for route in self._routes)

    def select(self, task: SpecialistTask) -> RegisteredSpecialistRoute:
        """Select the sole registered route able to satisfy an exact task.

        Args:
            task: Caller-built specialist task whose authority and output types
                must be supported by exactly one registration.

        Returns:
            The unique matching code-owned route.

        Raises:
            SpecialistRouteUnavailableError: If the authority has no route.
            SpecialistRouteUnsupportedTaskError: If registered routes cannot
                produce every requested output type.
            SpecialistRouteAmbiguityError: If multiple versions accept the task.
        """
        authority_routes = tuple(
            route
            for route in self._routes
            if route.descriptor.authority_key == task.authority_key
        )
        if not authority_routes:
            raise SpecialistRouteUnavailableError(task.authority_key)
        requested_types = {slot.artifact_type for slot in task.requested_outputs}
        matching = tuple(
            route
            for route in authority_routes
            if requested_types.issubset(route.descriptor.supported_output_types)
        )
        if not matching:
            raise SpecialistRouteUnsupportedTaskError(
                "registered specialist routes do not support requested outputs: "
                + ", ".join(sorted(requested_types))
            )
        if len(matching) > 1:
            versions = ", ".join(route.descriptor.version for route in matching)
            raise SpecialistRouteAmbiguityError(
                f"multiple specialist routes accept {task.task_id}: {versions}"
            )
        return matching[0]

    def require(
        self,
        *,
        authority_key: str,
        version: str,
        task: SpecialistTask,
    ) -> RegisteredSpecialistRoute:
        """Resolve and revalidate an exact route pinned by a decision.

        Args:
            authority_key: Authority recorded in the coordination decision.
            version: Route version recorded in the coordination decision.
            task: Exact original task to validate against route coverage.

        Returns:
            Matching code-owned route.

        Raises:
            SpecialistRouteUnavailableError: If the pinned route is unavailable.
            SpecialistRouteUnsupportedTaskError: If its authority or outputs no
                longer accept the task.
        """
        try:
            route = self._by_identity[(authority_key, version)]
        except KeyError as exc:
            raise SpecialistRouteUnavailableError(authority_key) from exc
        if task.authority_key != authority_key:
            raise SpecialistRouteUnsupportedTaskError(
                "specialist task authority does not match the selected route"
            )
        requested_types = {slot.artifact_type for slot in task.requested_outputs}
        if not requested_types.issubset(route.descriptor.supported_output_types):
            raise SpecialistRouteUnsupportedTaskError(
                "specialist task outputs no longer match the selected route"
            )
        return route
